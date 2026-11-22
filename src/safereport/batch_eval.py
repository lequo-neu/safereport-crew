"""What the two stage batch saves on the Texas week (task B4, issue #5).

The same crew (`build_graph`) plans the Texas week twice, offline:

* **two stages**, as the app runs: stage 1 codes every report without a model, and only the
  unclear, severe or borderline reports take a model branch;
* **every report through stage 2**: the same graph, with the thresholds that decide who takes a
  branch set so that every report does. Only the copy of the settings that the fan out reads is
  changed; the router keeps its own settings, so it picks models exactly as it does in the app.

Each run is approved as it is. The calls are counted from the router's usage log; the decisions
are the approved list. What is measured: the model calls the graph makes, the reports that take
a branch, and the decisions. What is estimated: the tokens (about four characters a token, on
the offline prompts and replies) and the dollar cost (those tokens at the prices in
config/models.toml, for the model the router chose).

Run it with `python -I scripts/eval_batch_savings.py` (add `--no-dense` for BM25 only). It
writes eval/results/batch_savings.json. No model is called and nothing is paid.
"""

from __future__ import annotations

from collections import Counter
import dataclasses
from datetime import date
import json
import math
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from safereport.backends import estimate_tokens
from safereport.config import PROJECT_ROOT
from safereport.graph import Services, build_graph, run_config


RESULTS_DIR = PROJECT_ROOT / "eval" / "results"
# The README's command for the Texas week (17 to 23 November 2025), with its 40 inspector days.
REQUEST = "Plan this week's inspections in Texas with 40 inspector days."
# The README's and the proposal's estimate of the calls for one Texas week with no first stage.
README_ESTIMATE = 85
# What the two approved lists are compared on, report by report.
COMPARED = ("decision", "category_one", "priority", "standard")
# The task whose system prompt a live provider adds to each step (providers.SYSTEM).
TASK_OF_STEP = {"decide": "planner", "code": "intake", "retrieve": "standards_terms", "write": "writer"}

LIMITATIONS = [
    "Offline: every model answers from the same deterministic rules, so the decisions that change are the ones the offline branch changes. A live model reads the facts differently and can change other decisions.",
    "The tokens are estimated at about four characters a token on the offline prompts and replies. A live reply is longer, and GPT 5 nano also spends reasoning tokens: in the measured live terms experiment it averaged about 2,300 output tokens a call (eval/results/live_terms_gpt_nano.json), far above the offline estimate.",
    "The second estimate adds each step's system prompt (providers.SYSTEM) to the input tokens, as a live provider would send it; it still leaves out reasoning tokens and longer replies.",
    "The dollar cost uses the prices in config/models.toml for the model the router chose in lowest cost mode; a cached live call costs nothing, which the estimate ignores.",
    "One week in one state (31 reports). The share of reports that take a branch depends on the week, so the saving on other weeks or nationwide is not measured here.",
    "The time of each run is not compared: offline replies take no time, so it says nothing about the time a live branch takes.",
]


def everything_through_stage2(services: Services) -> Services:
    """The same services, but the fan out sends every report to a model branch.

    The fan out sends a report when its intake confidence is below `min_confidence` or its
    retrieval margin below `min_retrieval_margin` (a Category 1 report only for the first). With
    both thresholds at infinity every report qualifies. The router keeps its own settings, so
    the model a step gets, and its price, are as in the app.
    """
    router_settings = services.settings.router.model_copy(
        update={"min_confidence": math.inf, "min_retrieval_margin": math.inf}
    )
    settings = services.settings.model_copy(update={"router": router_settings})
    return dataclasses.replace(services, settings=settings)


def _price(services: Services) -> dict[str, Any]:
    return {m.name: m for m in services.settings.models}


def run_week(services: Services, request: str = REQUEST) -> dict[str, Any]:
    """Plan and approve the week once; the calls it made and the list it approved."""
    log = services.router.log
    before = len(log.rows())
    graph = build_graph(services, InMemorySaver())
    config = run_config()
    out = graph.invoke({"request": request}, config)
    if "__interrupt__" not in out or "rows" not in out["__interrupt__"][0].value:
        raise RuntimeError(f"the request did not reach the approval of a weekly list: {request!r}")
    state = graph.get_state(config).values
    rows = out["__interrupt__"][0].value["rows"]
    graph.invoke(Command(resume={"action": "approve", "by": "batch savings evaluation"}), config)
    # Every call the run added, the Planner's included (it is logged before the run has an id).
    calls = log.rows()[before:]
    models = _price(services)
    for call in calls:
        system = estimate_tokens(_system_prompt(call["step"]))
        call["input_tokens_with_system"] = call["input_tokens"] + system
        spec = models.get(call["model"])
        call["cost_with_system"] = (
            spec.cost(call["input_tokens_with_system"], call["output_tokens"])
            if spec and not call["error"]
            else 0.0
        )
    return {"stage2": sorted(state.get("stage2", {})), "rows": rows, "calls": calls}


def _system_prompt(step: str) -> str:
    from safereport.providers import SYSTEM

    return SYSTEM.get(TASK_OF_STEP.get(step, ""), "")


def _summary(run: dict[str, Any]) -> dict[str, Any]:
    calls = run["calls"]
    ok = [c for c in calls if not c["error"]]
    unpriced = sum(c["cost"] is None for c in ok)
    return {
        "reports": len(run["rows"]),
        "reports_through_stage2": len(run["stage2"]),
        "measured": {
            "model_calls": len(ok),
            "failed_calls": len(calls) - len(ok),
            "calls_by_agent": dict(Counter(c["node"] for c in ok)),
            "calls_by_step": dict(Counter(c["step"] for c in ok)),
            "calls_by_model": dict(Counter(c["model"] for c in ok)),
            "inspections": sum(r["decision"] == "inspection" for r in run["rows"]),
            "rri_letters": sum(r["decision"] == "rri_letter" for r in run["rows"]),
        },
        "estimated": {
            "offline_log": {
                "input_tokens": sum(c["input_tokens"] for c in ok),
                "output_tokens": sum(c["output_tokens"] for c in ok),
                "cost_usd": round(sum(c["cost"] or 0.0 for c in ok), 6),
                "calls_without_a_price": unpriced,
            },
            "with_system_prompts": {
                "input_tokens": sum(c["input_tokens_with_system"] for c in ok),
                "output_tokens": sum(c["output_tokens"] for c in ok),
                "cost_usd": round(sum(c["cost_with_system"] or 0.0 for c in ok), 6),
            },
        },
    }


def _saving(two: float, full: float) -> dict[str, Any]:
    saved = full - two
    return {
        "two_stages": round(two, 6),
        "every_report": round(full, 6),
        "saved": round(saved, 6),
        "saved_share": round(saved / full, 3) if full else 0.0,
    }


def _changes(two: dict[str, Any], full: dict[str, Any]) -> dict[str, Any]:
    """Report by report, what differs between the two approved lists."""
    a = {r["report_id"]: r for r in two["rows"]}
    b = {r["report_id"]: r for r in full["rows"]}
    if set(a) != set(b):
        raise RuntimeError("the two runs planned different reports")

    def differ(field: str) -> list[dict[str, Any]]:
        return [
            {"report_id": rid, "two_stages": a[rid][field], "every_report": b[rid][field]}
            for rid in sorted(a)
            if a[rid][field] != b[rid][field]
        ]

    return {
        "decisions": differ("decision"),
        "category_one": differ("category_one"),
        "cited_standard": differ("standard"),
        "priority": differ("priority"),
    }


def _list(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The approved list, report by report, with the fields the comparison looks at."""
    return {
        r["report_id"]: {k: r[k] for k in COMPARED} for r in sorted(run["rows"], key=lambda r: r["report_id"])
    }


def compare(services: Services, request: str = REQUEST) -> dict[str, Any]:
    """Run both workflows on the same services and compare them."""
    two = run_week(services, request)
    full = run_week(everything_through_stage2(services), request)
    if len(full["stage2"]) != len(full["rows"]):
        raise RuntimeError("the counterfactual did not send every report through stage 2")
    s2, sf = _summary(two), _summary(full)
    changes = _changes(two, full)
    week = getattr(services, "week", (date.min, date.min))
    return {
        "task": "B4, issue #5",
        "question": "What does sending only some reports to the model branches save, and what does it change?",
        "week": {
            "state": "Texas",
            "start": week[0].isoformat(),
            "end": week[1].isoformat(),
            "request": request,
        },
        "two_stages": s2,
        "every_report_through_stage2": sf,
        "saving": {
            "measured_model_calls": _saving(s2["measured"]["model_calls"], sf["measured"]["model_calls"]),
            "estimated_cost_usd_offline_log": _saving(
                s2["estimated"]["offline_log"]["cost_usd"], sf["estimated"]["offline_log"]["cost_usd"]
            ),
            "estimated_cost_usd_with_system_prompts": _saving(
                s2["estimated"]["with_system_prompts"]["cost_usd"],
                sf["estimated"]["with_system_prompts"]["cost_usd"],
            ),
            "estimated_input_tokens_with_system_prompts": _saving(
                s2["estimated"]["with_system_prompts"]["input_tokens"],
                sf["estimated"]["with_system_prompts"]["input_tokens"],
            ),
            "estimated_output_tokens": _saving(
                s2["estimated"]["offline_log"]["output_tokens"],
                sf["estimated"]["offline_log"]["output_tokens"],
            ),
        },
        "changes": {
            "decisions_changed": len(changes["decisions"]),
            "category_one_changed": len(changes["category_one"]),
            "cited_standard_changed": len(changes["cited_standard"]),
            "priority_changed": len(changes["priority"]),
            "by_report": changes,
        },
        "reports_skipped_by_two_stages": sorted(set(full["stage2"]) - set(two["stage2"])),
        "approved_lists": {
            "fields": list(COMPARED),
            "two_stages": _list(two),
            "every_report_through_stage2": _list(full),
        },
        "earlier_estimate": {
            "readme_calls_every_report": README_ESTIMATE,
            "measured_calls_every_report": sf["measured"]["model_calls"],
            "note": f"The README and proposal estimated about {README_ESTIMATE} calls for one Texas week with three "
            f"model calls a report; the measured run with every report through stage 2 made "
            f"{sf['measured']['model_calls']}, because a branch makes two calls (intake coding and standards "
            "terms) and the Writer drafts one document per letter or brief.",
        },
        "method": {
            "backend": "offline (deterministic rules); no model called, nothing paid",
            "mode": services.mode,
            "measured": "model calls, reports through stage 2 and the approved decisions, from one run of the crew's own graph each way",
            "estimated": "tokens at about four characters a token, and cost at config/models.toml prices",
            "counterfactual": "the fan out's thresholds (min_confidence, min_retrieval_margin) set to infinity in a copy of the settings; the router's own settings unchanged",
        },
        "limitations": list(LIMITATIONS),
        "command": "python -I scripts/eval_batch_savings.py",
    }


def run(dense: bool = True, out: Path = RESULTS_DIR / "batch_savings.json") -> dict[str, Any]:
    """Compare both workflows on the Texas week of the built data and write the result file."""
    from safereport.graph import load_services
    from safereport.retrieval import dense_ready

    dense = dense and dense_ready()
    services = load_services(dense=dense)
    result = compare(services)
    result["method"]["retrieval"] = "hybrid" if dense else "bm25"
    if not dense:
        result["command"] += " --no-dense"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
