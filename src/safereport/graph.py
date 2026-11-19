"""The crew as a LangGraph graph.

    planner ─▶ (clarify: interrupt) ─▶ next_task ─┬▶ single_report ─────────────┐
                                                   ├▶ trend / repeats / talk ───┤
                                                   └▶ triage_stage1 ─Send─▶ branch (one per report) ─▶ optimizer
    next_task (when every sub task is done) ─▶ writer ─▶ critic ─┬▶ writer (at most 2 retries)
                                                                ├▶ optimizer (at most 2 retries)
                                                                ├▶ approval: interrupt ─▶ optimizer (changes) or END
                                                                └▶ END

Seven agents: the Planner splits the request into sub tasks; Intake reads each narrative;
Standards finds the rule; the Analyst runs the numbers; the Optimizer builds the week's list;
the Decision critic checks citations, domain rules, numbers and plan rules; the Writer drafts
every document. Model steps go through the router; with the offline backend every step answers
from deterministic rules, so the whole graph runs and is tested without an API key.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
import json
import operator
import re
import threading
from typing import Annotated, Any, TypedDict
import uuid

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send, interrupt
import pandas as pd

from safereport import offline
from safereport.baseline import EventBaseline
from safereport.config import ModelSettings
from safereport.data import OIICS_3_FROM_YEAR, Filters, ReportStore
from safereport.domain import check_citation
from safereport.ecfr import CitationIndex
from safereport.employers import EmployerIndex, normalize_name, repeat_summary
from safereport.ledger import FactLedger
from safereport.outputs import sensitivity_chart, trend_chart, triage_csv
from safereport.redaction import redact
from safereport.retrieval import IndexRegistry
from safereport.router import Mode, Router, Signals
from safereport.schemas import CITATION, DIRECTIVE, GENERAL_DUTY, IntakeResult, Report
from safereport.talk_languages import extra_language
from safereport.triage import (
    DEFAULT_CAPACITY,
    Case,
    Rules,
    category_one,
    inspection_days,
    plan_week,
    priority,
    sensitivity,
)


MAX_RETRIES = 2
NO_SPECIFIC = {"overexertion", "violence", "bite", "heat"}


def merge(left: dict | None, right: dict | None) -> dict:
    return {**(left or {}), **(right or {})}


class CrewState(TypedDict, total=False):
    run_id: str
    request: str
    params: dict[str, Any]
    tasks: list[dict[str, Any]]
    missing: list[str]
    done: Annotated[list[str], operator.add]
    week: list[dict[str, Any]]
    stage1: dict[str, dict[str, Any]]
    stage2: Annotated[dict[str, dict[str, Any]], merge]
    findings: Annotated[dict[str, dict[str, Any]], merge]
    # Standards the critic corrected in the weekly list, by report; the Optimizer applies them.
    pick_overrides: Annotated[dict[str, dict[str, Any]], merge]
    plan: dict[str, Any]
    rules: dict[str, Any]
    drafts: dict[str, dict[str, Any]]
    issues: list[dict[str, Any]]
    writer_retries: int
    optimizer_retries: int
    trace: Annotated[list[dict[str, Any]], operator.add]
    decision_log: Annotated[list[dict[str, Any]], operator.add]
    approval: dict[str, Any]
    answer: str


@dataclass
class Services:
    """Everything the agents use, built once and shared by every run."""

    store: ReportStore
    registry: IndexRegistry
    citations: CitationIndex
    baseline: EventBaseline
    router: Router
    settings: ModelSettings
    week: tuple[date, date] = (date(2025, 11, 17), date(2025, 11, 23))
    # Inspector days for the replayed week (config/triage.toml); the user changes it per request.
    capacity: float = DEFAULT_CAPACITY
    mode: Mode = "lowest_cost"
    redact_for_cloud: bool = True
    # A demo and test seam: when set, the Standards agent proposes this pick instead of its own,
    # so the critic can be shown catching a wrong or invented citation.
    seeded_pick: dict[str, str] | None = None
    similar: Any = None  # SimilarReports; None skips the similar injury search
    # Where confirmed and rejected employer matches are kept (a DecisionStore); None keeps them
    # in memory only.
    decisions: Any = None
    _employers: dict[str, EmployerIndex] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def employers(self, state: str) -> EmployerIndex:
        """One employer index per state, built the first time a state is asked about."""
        state = state.upper()
        with self._lock:
            if state not in self._employers:
                rows = self.store.frame("SELECT * FROM reports WHERE upper(state) = ?", [state])
                self._employers[state] = EmployerIndex(rows, store=self.decisions)
            return self._employers[state]


def _trace(agent: str, summary: str, record=None, tool: str = "") -> dict[str, Any]:
    entry = {
        "agent": agent,
        "summary": summary,
        "tool": tool,
        "model": "",
        "reason": "",
        "cost": None,
        "seconds": 0.0,
    }
    if record is not None:
        entry.update(model=record.model, reason=record.reason, cost=record.cost, seconds=round(record.seconds, 4),
                     fallback=record.fallback_from)  # fmt: skip
    return entry


def _report_from_row(row: dict[str, Any]) -> Report:
    return Report(**{name: row[name] for name in Report.model_fields if name in row})


def _restored(value: Any, restore) -> Any:
    """Put the original words back into every string of a model's JSON reply."""
    if isinstance(value, str):
        return restore(value)
    if isinstance(value, list):
        return [_restored(v, restore) for v in value]
    if isinstance(value, dict):
        return {k: _restored(v, restore) for k, v in value.items()}
    return value


def _respan(intake: dict[str, Any], shown: str, original: str) -> dict[str, Any]:
    """Move span offsets found on redacted text back onto the original narrative."""
    spans = []
    for span in intake.get("spans", []):
        words = shown[span["start"] : span["end"]]
        at = original.find(words)
        if at >= 0 and words:
            spans.append({**span, "start": at, "end": at + len(words)})
    return {**intake, "spans": spans}


def build_graph(services: Services, checkpointer=None):
    router = services.router

    def model(state: CrewState, step, task, payload, node, signals=None):
        return router.call(step, json.dumps(payload, default=str), signals=signals, mode=services.mode,
                           node=node, run_id=state.get("run_id", ""), task=task)  # fmt: skip

    def reaches_cloud(steps: tuple[str, ...], signals: Signals | None = None) -> bool:
        """True when the chosen model, or a model the call can fall back to, runs in the cloud."""
        if not services.redact_for_cloud or services.mode == "private":
            return False
        for step in steps:
            choice = router.choose(step, signals or Signals(), services.mode)
            chain = [choice.model] + [
                m for m in services.settings.fallback_after(choice.model.name) if m.name in router.backends
            ]
            if any(not m.is_local for m in chain):
                return True
        return False

    def cloud_text(narrative: str, report: Report, signals: Signals) -> str:
        if not reaches_cloud(("code", "retrieve"), signals):
            return narrative
        return redact(narrative, employer=report.employer, address=report.address, city=report.city,
                      zip_code=report.zip).text  # fmt: skip

    # ---- Intake, Standards and Analyst for one report (used by single_report and by branches) ----

    def read_report(state: CrewState, report: Report, node: str) -> dict[str, Any]:
        trace = []
        predicted = services.baseline.predict([report.narrative])[0]
        signals = Signals(intake_confidence=predicted.confidence)
        shown = cloud_text(report.narrative, report, signals)
        payload = {"report_id": report.id, "narrative": shown, "event_title": report.event_title,
                   "nature_title": report.nature_title, "baseline_code": predicted.code,
                   "baseline_confidence": predicted.confidence, "source_code": report.source_code}  # fmt: skip
        reply, record = model(state, "code", "intake", payload, node, signals)
        facts = _respan(reply.data or {}, shown, report.narrative)
        intake = IntakeResult.model_validate(facts)
        trace.append(_trace("Intake", f"{intake.hazard_type} during {intake.activity}, code {intake.event_code} "
                                      f"({intake.confidence:.2f})", record))  # fmt: skip

        terms_reply, record = model(state, "retrieve", "standards_terms", {"narrative": shown, "material": intake.material},
                                    node, signals)  # fmt: skip
        terms = (terms_reply.data or {}).get("terms", [])
        query = f"{report.narrative} {report.event_title} {report.source_title}"
        found = services.registry.search(query, naics=report.naics, k=5, terms=terms)
        pick = pick_standard(intake, found)
        trace.append(
            _trace(
                "Standards",
                f"{pick['primary']} (margin {found.margin:.2f})",
                record,
                tool="IndexRegistry.search",
            )
        )

        history = services.employers(report.state).history(
            report.employer,
            report.state,
            city=report.city,
            zip_code=report.zip,
            naics=report.naics,
            exclude_id=report.id,
        )
        earlier = [m for m in history if m.event_date < report.event_date]
        division = (intake.event_code or report.event_code)[:1]
        repeats = [
            m.report_id
            for m in earlier
            if m.status == "same"
            and (report.event_date - m.event_date).days <= 365
            and (not division or not m.event_code_v3 or m.event_code_v3.startswith(division))
        ]
        share = industry_share(report, intake.event_code)
        similar = []
        if services.similar is not None:
            group = (intake.event_code or report.event_code)[:2]
            similar = [
                s.__dict__
                for s in services.similar.find(report.narrative, report.naics, group, exclude=report.id)
            ]
            trace.append(_trace("Analyst", f"{len(similar)} similar past injuries by {services.similar.method}",
                                tool="SimilarReports"))  # fmt: skip
        trace.append(_trace("Analyst", f"{len(repeats)} confirmed repeats within a year, "
                                       f"{sum(m.status == 'possible' for m in earlier)} possible", tool="EmployerIndex"))  # fmt: skip
        return {
            "report": report.model_dump(mode="json"),
            "intake": intake.model_dump(),
            "pick": pick,
            "margin": found.margin,
            "candidates": [s.section for s in found.sections],
            "emphasis": [h.document.citation for h in found.emphasis if h.document.verified],
            "possible_emphasis": [h.document.citation for h in found.emphasis if not h.document.verified],
            "history_same": sum(m.status == "same" for m in earlier),
            "history_possible": sum(m.status == "possible" for m in earlier),
            "repeats": repeats,
            "industry_share": share,
            "similar": similar,
            "trace": trace,
        }

    def pick_standard(intake: IntakeResult, found) -> dict[str, Any]:
        if services.seeded_pick is not None:
            seeded, services.seeded_pick = services.seeded_pick, None
            return {"primary": seeded["primary"], "secondary": seeded.get("secondary", ""), "quote": ""}
        if intake.hazard_type in NO_SPECIFIC or not found.sections:
            return {"primary": GENERAL_DUTY, "secondary": "", "quote": services.registry.general_duty().text}
        # The section is cited: retrieval is measured at section level, and the closest paragraph
        # can be the wrong one (for a laminator jam, the cord and plug exemption of 1910.147). The
        # paragraph is kept for a person to check. A secondary comes only from a domain rule; the
        # runner up section is a candidate, not a citation.
        best = found.sections[0].best.document
        opening = services.citations.text(best.section)[:600] or best.text[:600]
        paragraph = best.citation if best.exact_citation and best.citation != best.section else ""
        return {"primary": best.section, "secondary": "", "quote": opening, "paragraph": paragraph,
                "paragraph_text": best.text[:600] if paragraph else ""}  # fmt: skip

    def industry_share(report: Report, code: str = "") -> float:
        """Share of the industry's reports since 2022 in the same estimated OIICS 3 event group.

        `code` is the OIICS 3 code the Intake agent read; a pasted narrative has no code of its own.
        """
        code = code or (report.event_code if report.event_date.year >= 2024 else "")
        group = code[:2]
        if not group:
            return 0.0
        rows = services.store.frame(
            "SELECT avg(CASE WHEN starts_with(event_code_v3, ?) THEN 1.0 ELSE 0.0 END) AS share FROM reports "
            "WHERE starts_with(naics, ?) AND year >= 2022", [group, report.naics[:3]],
        )  # fmt: skip
        value = rows["share"].iloc[0]
        return float(value) if pd.notna(value) else 0.0

    # ---- Planner ----

    def planner(state: CrewState) -> dict[str, Any]:
        # A pasted narrative reaches the Planner first, so names and addresses are hidden here too;
        # state names stay visible because the plan needs them. Placeholders in the plan are put back.
        hidden = redact(state["request"], keep=tuple(offline.STATES)) if reaches_cloud(("decide",)) else None
        request = hidden.text if hidden else state["request"]
        reply, record = model(state, "decide", "planner", {"request": request}, "planner")
        plan = _restored(reply.data or {}, hidden.restore) if hidden else (reply.data or {})
        params = {**plan.get("params", {}), **state.get("params", {})}
        tasks = plan.get("tasks", [])
        missing = sorted({n for t in tasks for n in t.get("needs", []) if n not in params}) or plan.get(
            "missing", []
        )
        if not tasks:
            missing = ["request"]
        summary = ", ".join(t["kind"] for t in tasks) or "nothing it can do yet"
        return {"run_id": state.get("run_id") or uuid.uuid4().hex[:12], "tasks": tasks, "params": params,
                "missing": missing, "trace": [_trace("Planner", f"sub tasks: {summary}", record)]}  # fmt: skip

    def after_planner(state: CrewState) -> str:
        return "clarify" if state.get("missing") else "next_task"

    def clarify(state: CrewState) -> dict[str, Any]:
        question = {
            "state": "Which state should I look at?",
            "start": "From which year?",
            "request": "What would you like to know? For example a narrative, a trend, or this week's inspections.",
        }
        answers = dict(
            interrupt(
                {"missing": state["missing"], "questions": [question.get(m, m) for m in state["missing"]]}
            )
        )
        update: dict[str, Any] = {
            "missing": [],
            "trace": [_trace("Planner", f"user answered {sorted(answers)}")],
        }
        if "request" in answers:
            update["request"] = answers.pop("request")
        update["params"] = {
            **state["params"],
            **{k: (v.upper() if k == "state" else v) for k, v in answers.items()},
        }
        return update

    def after_clarify(state: CrewState) -> str:
        return "next_task" if state.get("tasks") else "planner"

    # ---- Sub task dispatch ----

    nodes_for = {"single_report": "single_report", "trend": "trend", "repeat_employers": "repeats",
                 "triage": "triage_stage1", "safety_talk": "safety_talk", "prevention_plan": "prevention"}  # fmt: skip

    def next_task(state: CrewState) -> dict[str, Any]:
        return {}

    def route_task(state: CrewState) -> str:
        done = set(state.get("done", []))
        for task in state.get("tasks", []):
            if task["id"] not in done and all(d in done for d in task.get("depends_on", [])):
                return nodes_for[task["kind"]]
        return "writer"

    def task_of(state: CrewState, kind: str) -> dict[str, Any]:
        return next(
            t for t in state["tasks"] if t["kind"] == kind and t["id"] not in set(state.get("done", []))
        )

    # ---- Task nodes ----

    def single_report(state: CrewState) -> dict[str, Any]:
        task = task_of(state, "single_report")
        narrative = state["request"].strip()
        params = state.get("params", {})
        # A pasted report is dated to the last day of the replayed week, the "today" of the demo, so
        # the twelve month repeat window and the OIICS 3 era match the data (which ends in 2025).
        report = Report(
            id="new", event_date=services.week[1], employer=params.get("employer", "the employer"),
            state=params.get("state", ""), naics=params.get("naics", params.get("naics_prefix", "3")),
            hospitalized=0, amputation=int("amputat" in narrative.lower()), loss_of_eye=0, narrative=narrative,
            event_code="", event_title="", source_code="", source_title="",
        )  # fmt: skip
        result = read_report(state, report, "single_report")
        return {"done": [task["id"]], "findings": {task["id"]: {"kind": "single_report", **result}},
                "trace": result.pop("trace")}  # fmt: skip

    def trend(state: CrewState) -> dict[str, Any]:
        task = task_of(state, "trend")
        p = state["params"]
        filters = Filters(state=p.get("state", ""), naics_prefix=p.get("naics_prefix", ""),
                          event_group_v3=p.get("event_group_v3", ""),
                          start=date.fromisoformat(p["start"]) if p.get("start") else None)  # fmt: skip
        frame = services.store.yearly_trend(filters)
        if not frame.empty:
            frame = frame[frame["year"] >= (filters.start.year if filters.start else frame["year"].min())]
        place = f" in {p['state'].title()}" if p.get("state") else ""
        hazard = f", {p['hazard_label']}" if p.get("hazard_label") else ""
        subject = f"Severe injury reports{place}{hazard}"
        if frame.empty:
            finding = {"kind": "note", "text": f"{subject}: no report matches this range."}
            return {"done": [task["id"]], "findings": {task["id"]: finding},
                    "trace": [_trace("Analyst", "no reports in the range", tool="ReportStore.yearly_trend")]}  # fmt: skip
        latest = frame.iloc[-1]
        # With a single year in the range there is no earlier year to compare with.
        previous = frame.iloc[-2] if len(frame) > 1 else None
        chart = trend_chart(frame, subject)
        finding = {
            "kind": "trend",
            "subject": subject,
            "estimated": bool((frame["estimated_share"] > 0).any()),
            "facts": {
                "latest_reports": (int(latest["same_months"]), "ReportStore.yearly_trend", True),
                "latest_year": (str(int(latest["year"])), "ReportStore.yearly_trend", True),
                "oiics_change_year": (str(OIICS_3_FROM_YEAR), "data.OIICS_3_FROM_YEAR", True),
                "latest_note": (
                    "January to November only" if latest["partial"] else "full year",
                    "data",
                    True,
                ),
            },
            "rows": frame.to_dict("records"),
            "chart": chart,
            "single_year": previous is None,
        }
        if previous is not None:
            finding["facts"] |= {
                "previous_reports": (int(previous["same_months"]), "ReportStore.yearly_trend", True),
                "previous_year": (str(int(previous["year"])), "ReportStore.yearly_trend", True),
                "change": (
                    float(latest["change"]) if pd.notna(latest["change"]) else "not measurable",
                    "ReportStore.yearly_trend",
                    True,
                ),
            }
        return {"done": [task["id"]], "findings": {task["id"]: finding},
                "trace": [_trace("Analyst", f"{len(frame)} years of {subject.lower()}", tool="ReportStore.yearly_trend")]}  # fmt: skip

    def repeats(state: CrewState) -> dict[str, Any]:
        task = task_of(state, "repeat_employers")
        p = state["params"]
        filters = Filters(state=p["state"], naics_prefix=p.get("naics_prefix", ""),
                          event_group_v3=p.get("event_group_v3", ""),
                          start=date.fromisoformat(p["start"]) if p.get("start") else None)  # fmt: skip
        services.store.check_coding(filters)
        where, params = filters.where()
        frame = services.store.frame(f"SELECT employer, city, naics FROM reports WHERE {where}", params)  # noqa: S608 (fixed fragments, parameter values)
        repeated, possible, pairs = repeat_summary(frame)
        finding = {"kind": "repeat_answer", "pairs": pairs,
                   "facts": {"repeat_employers": (repeated, "employers.repeat_summary", True),
                             "possible_pairs": (possible, "employers.repeat_summary", True),
                             "state": (p["state"].title(), "request", True)}}  # fmt: skip
        return {"done": [task["id"]], "findings": {task["id"]: finding},
                "trace": [_trace("Analyst", f"{repeated} repeat employers, {possible} pairs to confirm", tool="repeat_summary")]}  # fmt: skip

    def safety_talk(state: CrewState) -> dict[str, Any]:
        task = task_of(state, "safety_talk")
        words = {"lockout": "lock|clean|jam|maint|servic", "forklift": "forklift|fork lift|pallet jack",
                 "ladder": "ladder", "fall": "fell|fall", "machine guarding": "guard|caught", "slip": "slip|trip"}  # fmt: skip
        prefix = state["params"].get("naics_prefix", "3")
        count = services.store.frame(
            "SELECT count(*) AS n FROM reports WHERE starts_with(naics, ?) AND regexp_matches(lower(narrative), ?)",
            [prefix, words.get(task["topic"], "lock")],
        )["n"].iloc[0]  # fmt: skip
        # English always, and at most one more language for the floor crew.
        extra, _ = extra_language(task.get("extra_language") or ("es" if task.get("spanish") else ""))
        finding = {"kind": "safety_talk", "topic": task["topic"], "languages": ["en", *([extra] if extra else [])],
                   "facts": {"topic_reports": (int(count), "ReportStore", True), "since": ("2015", "data", True)}}  # fmt: skip
        return {"done": [task["id"]], "findings": {task["id"]: finding},
                "trace": [_trace("Analyst", f"{count} reports on {task['topic']}", tool="ReportStore")]}  # fmt: skip

    def prevention(state: CrewState) -> dict[str, Any]:
        task = task_of(state, "prevention_plan")
        finding = {
            "kind": "note",
            "text": "The prevention plan is an extension planned for Phase 4; it is not built yet.",
        }
        return {"done": [task["id"]], "findings": {task["id"]: finding},
                "trace": [_trace("Optimizer", "prevention plan not built yet")]}  # fmt: skip

    # ---- Triage: stage 1 for every report, stage 2 branches only where needed ----

    def triage_stage1(state: CrewState) -> dict[str, Any]:
        p = state["params"]
        start, end = services.week
        rows = services.store.reports_between(start, end, p["state"]).to_dict("records")
        week, stage1 = [], {}
        index = services.employers(p["state"])
        predictions = services.baseline.predict([r["narrative"] for r in rows]) if rows else []
        for row, predicted in zip(rows, predictions, strict=True):
            report = _report_from_row(row)
            facts = IntakeResult.model_validate(offline.intake(
                {"report_id": report.id, "narrative": report.narrative, "event_title": report.event_title,
                 "nature_title": report.nature_title, "baseline_code": predicted.code,
                 "baseline_confidence": predicted.confidence}))  # fmt: skip
            found = services.registry.search(
                f"{report.narrative} {report.event_title}", naics=report.naics, k=3
            )
            division = str(row.get("event_code_v3") or report.event_code)[:1]
            repeats_found = [m.report_id for m in index.repeats_within(
                report.employer, report.state, report.event_date, division=division, city=report.city,
                zip_code=report.zip, naics=report.naics, exclude_id=report.id)]  # fmt: skip
            # Only a program whose scope was read from its directive forces an inspection; the
            # others raise the priority and are shown for a person to check.
            emphasis = [h.document.citation for h in found.emphasis if h.document.verified]
            possible = [h.document.citation for h in found.emphasis if not h.document.verified]
            score, parts = priority(
                report, facts, bool(found.sections), industry_share(report), possible_emphasis=bool(possible)
            )
            stage1[report.id] = {
                "report": report.model_dump(mode="json"), "intake": facts.model_dump(), "priority": score,
                "parts": parts, "days": inspection_days(facts), "margin": found.margin,
                "emphasis": emphasis, "possible_emphasis": possible, "repeats": repeats_found,
                "category_one": [t.__dict__ for t in category_one(report, emphasis, repeats_found)],
                "candidates": [s.section for s in found.sections],
                "pick": {"primary": found.sections[0].section if found.sections else GENERAL_DUTY, "secondary": "",
                         "quote": found.sections[0].best.document.text[:600] if found.sections else ""},
            }  # fmt: skip
            week.append(row)
        return {"week": [{"id": r["id"]} for r in week], "stage1": stage1,
                "trace": [_trace("Intake", f"stage 1 coded {len(stage1)} reports without a model", tool="EventBaseline")]}  # fmt: skip

    def fan_out(state: CrewState):
        """Send the unclear, severe or borderline reports to full model branches; the rest skip them."""
        stage1 = state.get("stage1", {})
        if not stage1:
            return "optimizer"
        cases = [_case(item) for item in stage1.values()]
        plan = plan_week(cases, state["params"].get("capacity", services.capacity))
        chosen = [
            c.priority for c in cases if plan.decisions[c.report_id] == "inspection" and not c.must_inspect
        ]
        cut = min(chosen) if chosen else 0.0
        send = []
        for item in stage1.values():
            unclear = item["intake"]["confidence"] < services.settings.router.min_confidence
            close = item["margin"] < services.settings.router.min_retrieval_margin
            severe = item["report"]["hospitalized"] >= 2 or item["intake"]["fatality_potential"]
            borderline = abs(item["priority"] - cut) <= 0.5
            # A Category 1 report is inspected whatever a model reads, so only an unclear one needs a branch.
            needed = unclear if item["category_one"] else (unclear or close or severe or borderline)
            if needed:
                send.append(
                    Send("branch", {"run_id": state.get("run_id", ""), "branch_report": item["report"]})
                )
        return send or "optimizer"

    def branch(payload: dict[str, Any]) -> dict[str, Any]:
        report = Report.model_validate(payload["branch_report"])
        result = read_report({"run_id": payload.get("run_id", "")}, report, "branch")
        trace = result.pop("trace")
        return {"stage2": {report.id: result}, "trace": trace}

    def _case(item: dict[str, Any]) -> Case:
        from safereport.triage import Trigger

        return Case(item["report"]["id"], item["report"]["employer"], item["days"], item["priority"], item["parts"],
                    [Trigger(**t) for t in item["category_one"]])  # fmt: skip

    def optimizer(state: CrewState) -> dict[str, Any]:
        p = state["params"]
        stage1 = dict(state.get("stage1", {}))
        for report_id, result in state.get("stage2", {}).items():
            report = Report.model_validate(result["report"])
            intake = IntakeResult.model_validate(result["intake"])
            score, parts = priority(
                report,
                intake,
                result["pick"]["primary"] != GENERAL_DUTY,
                result["industry_share"],
                possible_emphasis=bool(result["possible_emphasis"]),
            )
            stage1[report_id] = {
                **stage1[report_id], "intake": result["intake"], "priority": score, "parts": parts,
                "days": inspection_days(intake), "pick": result["pick"], "candidates": result["candidates"],
                "stage2": True,
                "category_one": [t.__dict__ for t in category_one(report, result["emphasis"], result["repeats"])],
                "history_same": result["history_same"], "history_possible": result["history_possible"],
            }  # fmt: skip
        for report_id, pick in state.get("pick_overrides", {}).items():
            if report_id in stage1:
                stage1[report_id] = {**stage1[report_id], "pick": pick}
        rules = Rules(**{k: set(v) if isinstance(v, list) else v for k, v in state.get("rules", {}).items()})
        capacity = float(p.get("capacity", services.capacity))
        cases = [_case(item) for item in stage1.values()]
        plan = plan_week(cases, capacity, rules)
        curve = sensitivity(cases, [max(0.0, capacity + d) for d in (-4, -2, 0, 2, 4, 6)], rules)
        rows = [
            {"report_id": c.report_id, "employer": c.employer, "decision": plan.decisions[c.report_id],
             "priority": c.priority, "days": c.days, "reason": plan.reasons[c.report_id],
             "category_one": "; ".join(t.criterion for t in c.category_one),
             "standard": stage1[c.report_id]["pick"]["primary"], "stage": 2 if stage1[c.report_id].get("stage2") else 1}
            for c in sorted(cases, key=lambda c: (-int(c.must_inspect), -c.priority))
        ]  # fmt: skip
        task = next((t for t in state.get("tasks", []) if t["kind"] == "triage"), {"id": "triage"})
        finding = {
            "kind": "triage", "rows": rows, "stage1": stage1, "capacity": capacity,
            "plan": {"decisions": plan.decisions, "days_used": plan.days_used, "shortfall": plan.shortfall_days,
                     "priority_covered": plan.priority_covered},
            "sensitivity": curve, "chart": sensitivity_chart(curve), "csv": triage_csv(rows),
            "stage2_reports": sorted(state.get("stage2", {})),
        }  # fmt: skip
        summary = (f"{len(plan.inspections)} inspections, {len(cases) - len(plan.inspections)} letters, "
                   f"{plan.days_used:g} of {capacity:g} days" + (f", {plan.shortfall_days:g} days short" if plan.shortfall_days else ""))  # fmt: skip
        update: dict[str, Any] = {"findings": {task["id"]: finding}, "plan": finding["plan"],
                                  "trace": [_trace("Optimizer", summary, tool="PuLP CBC")]}  # fmt: skip
        if task["id"] not in state.get("done", []):
            update["done"] = [task["id"]]
        return update

    # ---- Writer ----

    def writer(state: CrewState) -> dict[str, Any]:
        signals = Signals(critic_rejected=bool(state.get("issues")))
        drafts, trace = {}, []
        for task_id, finding in state.get("findings", {}).items():
            for doc_id, payload, facts in documents(task_id, finding, state):
                reply, record = model(state, "write", "writer", payload, "writer", signals)
                drafts[doc_id] = {"template": reply.data["template"], "facts": facts, "kind": payload["kind"],
                                  "language": payload.get("language", "en"), "task": task_id,
                                  "citation": payload.get("citation", "")}  # fmt: skip
                trace.append(_trace("Writer", f"drafted {doc_id}", record))
        return {"drafts": drafts, "trace": trace}

    def documents(task_id: str, finding: dict[str, Any], state: CrewState):
        kind = finding["kind"]
        if kind == "single_report":
            report, intake, pick = finding["report"], finding["intake"], finding["pick"]
            facts = {**_report_facts(report), "quote": (pick["quote"], "eCFR", True),
                     "history_same": (finding["history_same"], "EmployerIndex.history", True),
                     "history_possible": (finding["history_possible"], "EmployerIndex.history", True)}  # fmt: skip
            for number, past in enumerate(finding.get("similar", []), start=1):
                facts[f"similar_{number}"] = (f"{past['event_date']}, {past['state'].title()}: {past['narrative'][:220]}",
                                              "SimilarReports", True)  # fmt: skip
            payload = {"kind": "inspection_brief", "hazard": intake["hazard_type"].replace("_", " "),
                       "activity": intake["activity"], "citation": pick["primary"],
                       "secondary_note": f", secondary {pick['secondary']}" if pick.get("secondary") else "",
                       "questions": intake["missing_facts"], "similar": len(finding.get("similar", []))}  # fmt: skip
            yield f"{task_id}:brief", payload, facts
        elif kind in ("trend", "repeat_answer"):
            payload = {"kind": "trend_answer" if kind == "trend" else "repeat_answer",
                       "subject": finding.get("subject", ""), "estimated": finding.get("estimated", False),
                       "single_year": finding.get("single_year", False)}  # fmt: skip
            yield f"{task_id}:answer", payload, finding["facts"]
        elif kind == "safety_talk":
            for language in finding["languages"]:
                yield (f"{task_id}:talk_{language}", {"kind": "safety_talk", "topic": finding["topic"], "language": language},
                       finding["facts"])  # fmt: skip
        elif kind == "triage":
            plan = finding["plan"]
            decisions = plan["decisions"]
            start, end = services.week
            facts = {
                "state": (state["params"]["state"].title(), "request", True),
                "week": (f"{start:%d %B} to {end:%d %B %Y}", "replayed week", True),
                "reports": (len(decisions), "ReportStore", True),
                "category_one": (
                    sum(bool(r["category_one"]) for r in finding["rows"]),
                    "triage.category_one",
                    True,
                ),
                "inspections": (sum(d == "inspection" for d in decisions.values()), "triage.plan_week", True),
                "letters": (sum(d == "rri_letter" for d in decisions.values()), "triage.plan_week", True),
                "days_used": (plan["days_used"], "triage.plan_week", True),
                "capacity": (finding["capacity"], "request", True),
                "shortfall": (plan["shortfall"], "triage.plan_week relaxed model", True),
            }
            yield f"{task_id}:summary", {"kind": "triage_summary", "infeasible": plan["shortfall"] > 0}, facts
            for report_id, decision in decisions.items():
                item = finding["stage1"][report_id]
                if decision != "rri_letter":
                    continue
                yield (f"{task_id}:letter_{report_id}",
                       {"kind": "rri_letter", "citation": item["pick"]["primary"], "questions": item["intake"]["missing_facts"]},
                       _report_facts(item["report"]))  # fmt: skip
        elif kind == "note":
            return

    def _report_facts(report: dict[str, Any]) -> dict[str, tuple]:
        pasted = report["id"] == "new"
        return {
            "report_id": ("pasted narrative" if pasted else report["id"], "report", True),
            "employer": (report["employer"] or "not given", "report", True),
            "city": (report.get("city", "").title() or "city not given", "report", True),
            "state": (report["state"].title() or "state not given", "report", True),
            "event_date": ("not given" if pasted else str(report["event_date"]), "report", True),
            "narrative": (report["narrative"], "report", True),
        }

    # ---- Decision critic ----

    def critic(state: CrewState) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        for doc_id, draft in state.get("drafts", {}).items():
            ledger = _ledger(draft["facts"])
            for number in ledger.untraced(draft["template"]):
                issues.append({"doc": doc_id, "rule": "untraced_number", "message": f"{number} does not come from a tool",
                               "route": "writer"})  # fmt: skip
            for key in ledger.unknown(draft["template"]):
                issues.append(
                    {
                        "doc": doc_id,
                        "rule": "unknown_fact",
                        "message": f"no fact named {key}",
                        "route": "writer",
                    }
                )
            for key in ledger.unequal_periods(draft["template"]):
                issues.append({"doc": doc_id, "rule": "unequal_periods", "message": f"{key} compares unequal periods",
                               "route": "writer"})  # fmt: skip
            citation = draft.get("citation", "")
            weekly = state.get("findings", {}).get(draft["task"], {}).get("kind") == "triage"
            if citation and not weekly and not _citation_ok(citation):
                issues.append({"doc": doc_id, "rule": "unknown_citation", "message": f"{citation} is not in eCFR",
                               "route": "standards", "task": draft["task"], "citation": citation})  # fmt: skip
        for task_id, finding in state.get("findings", {}).items():
            if finding["kind"] == "single_report":
                secondary = finding["pick"].get("secondary", "")
                if secondary and not _citation_ok(secondary):
                    issues.append({"doc": task_id, "rule": "unknown_citation", "route": "standards", "task": task_id,
                                   "citation": secondary, "message": f"{secondary} is not in eCFR"})  # fmt: skip
                facts = IntakeResult.model_validate(finding["intake"])
                for issue in check_citation(facts, finding["pick"]["primary"], finding["pick"].get("secondary", ""),
                                            finding["report"]["naics"], "1926" in services.registry.retrievers):  # fmt: skip
                    issues.append({"doc": task_id, "rule": issue.rule, "message": issue.message,
                                   "suggestion": issue.suggestion, "route": "standards" if issue.fix else "person",
                                   "task": task_id})  # fmt: skip
            if finding["kind"] == "triage":
                issues += plan_issues(finding)
                issues += triage_citation_issues(task_id, finding)
        writer_retries = state.get("writer_retries", 0)
        update: dict[str, Any] = {"issues": issues}
        fixes = [i for i in issues if i["route"] != "person"]
        checks = len(issues) - len(fixes)
        summary = f"{len(fixes)} issues" if fixes else "every citation, number and rule checks out"
        if checks:
            summary += f"; {checks} left for a person to check"
        update["trace"] = [
            _trace("Decision critic", summary, tool="CitationIndex, domain checks, FactLedger")
        ]
        if (
            issues
            and any(i["route"] in ("writer", "standards") for i in issues)
            and writer_retries >= MAX_RETRIES
        ):
            update["answer"] = finalize(state, issues)
        return update

    def triage_citation_issues(task_id: str, finding: dict[str, Any]) -> list[dict[str, Any]]:
        """The same citation and domain checks as for one report, on every report of the week."""
        problems = []
        for report_id, item in finding["stage1"].items():
            pick = item["pick"]
            where = {
                "doc": f"{task_id}:{report_id}",
                "route": "standards",
                "task": task_id,
                "report": report_id,
            }
            for cited in (pick["primary"], pick.get("secondary", "")):
                if cited and not _citation_ok(cited):
                    problems.append({**where, "rule": "unknown_citation", "citation": cited,
                                     "message": f"{report_id}: {cited} is not in eCFR"})  # fmt: skip
            facts = IntakeResult.model_validate(item["intake"])
            for issue in check_citation(facts, pick["primary"], pick.get("secondary", ""), item["report"]["naics"],
                                        "1926" in services.registry.retrievers):  # fmt: skip
                problems.append({**where, "rule": issue.rule, "message": f"{report_id}: {issue.message}",
                                 "suggestion": issue.suggestion, "route": "standards" if issue.fix else "person"})  # fmt: skip
        return problems

    def _citation_ok(citation: str) -> bool:
        return (citation == GENERAL_DUTY or bool(DIRECTIVE.match(citation))
                or (bool(CITATION.match(citation)) and services.citations.exists(citation)))  # fmt: skip

    def plan_issues(finding: dict[str, Any]) -> list[dict[str, Any]]:
        problems = []
        plan = finding["plan"]
        for row in finding["rows"]:
            if row["category_one"] and row["decision"] != "inspection":
                problems.append({"doc": row["report_id"], "rule": "category_one", "route": "optimizer",
                                 "message": f"{row['report_id']} meets Category 1 but is not inspected"})  # fmt: skip
        if plan["days_used"] > finding["capacity"] + plan["shortfall"] + 1e-6:
            problems.append({"doc": "plan", "rule": "capacity", "route": "optimizer",
                             "message": "the list uses more inspector days than the week has"})  # fmt: skip
        return problems

    def after_critic(state: CrewState) -> str:
        issues = state.get("issues", [])
        if any(i["route"] == "optimizer" for i in issues) and state.get("optimizer_retries", 0) < MAX_RETRIES:
            return "retry_optimizer"
        if (
            any(i["route"] in ("writer", "standards") for i in issues)
            and state.get("writer_retries", 0) < MAX_RETRIES
        ):
            return "revise"
        if any(f["kind"] == "triage" for f in state.get("findings", {}).values()) and not state.get(
            "approval"
        ):
            return "approval"
        return "finish"

    def retry_optimizer(state: CrewState) -> dict[str, Any]:
        return {"optimizer_retries": state.get("optimizer_retries", 0) + 1,
                "trace": [_trace("Decision critic", "sent the list back to the Optimizer")]}  # fmt: skip

    def revise(state: CrewState) -> dict[str, Any]:
        """Fix what the critic found: apply a domain suggestion or the next candidate, then redraft.

        A report of the weekly list is corrected through `pick_overrides`, so the Optimizer rebuilds
        the list (its standard column, CSV and letters) with the corrected standard.
        """
        findings: dict[str, dict[str, Any]] = {}
        overrides: dict[str, dict[str, Any]] = {}
        for issue in state.get("issues", []):
            if issue["route"] != "standards":
                continue
            if issue.get("report"):
                report_id = issue["report"]
                item = state["findings"][issue["task"]]["stage1"][report_id]
                pick = overrides.get(report_id) or item["pick"]
                overrides[report_id] = revised_pick(issue, pick, item.get("candidates", []), item)
                continue
            finding = findings.get(issue["task"]) or dict(state["findings"][issue["task"]])
            finding["pick"] = revised_pick(
                issue, dict(finding["pick"]), finding.get("candidates", []), finding
            )
            findings[issue["task"]] = finding
        update: dict[str, Any] = {"findings": findings, "writer_retries": state.get("writer_retries", 0) + 1,
                                  "trace": [_trace("Decision critic", f"sent {sum(i['route'] == 'standards' for i in state.get('issues', []))} issues back")]}  # fmt: skip
        if overrides:
            update["pick_overrides"] = overrides
        return update

    def revised_pick(
        issue: dict[str, Any], pick: dict[str, Any], candidates: list[str], item: dict[str, Any]
    ) -> dict[str, Any]:
        suggested = re.search(
            r"(19(?:10|26)\.\d+(?:\([A-Za-z0-9]+\))*|OSH Act 5\(a\)\(1\))", issue.get("suggestion", "")
        )
        if issue["rule"] == "energy_control":
            kept = pick["primary"] if _citation_ok(pick["primary"]) and pick["primary"] != "1910.147" else ""
            return {**pick, "primary": "1910.147", "secondary": kept,
                    "quote": services.citations.text("1910.147")[:600]}  # fmt: skip
        if suggested and _citation_ok(suggested.group(1)):
            cited = suggested.group(1)
            return {**pick, "primary": cited, "secondary": pick["primary"] if issue["rule"] == "mechanical_press_only" else "",
                    "quote": services.citations.text(cited)[:600] if cited != GENERAL_DUTY else services.registry.general_duty().text}  # fmt: skip
        if issue["rule"] == "unknown_citation" and issue.get("citation") == pick.get("secondary"):
            return {**pick, "secondary": ""}
        # The next candidate that eCFR has and that breaks no domain rule; else the General Duty Clause.
        facts = IntakeResult.model_validate(item["intake"])
        part_1926 = "1926" in services.registry.retrievers
        others = [c for c in candidates if c != pick["primary"] and _citation_ok(c)
                  and not check_citation(facts, c, "", item["report"]["naics"], part_1926)]  # fmt: skip
        primary = others[0] if others else GENERAL_DUTY
        quote = (
            services.citations.text(primary)[:600]
            if primary != GENERAL_DUTY
            else services.registry.general_duty().text
        )
        return {**pick, "primary": primary, "quote": quote}

    def after_revise(state: CrewState) -> str:
        # A corrected weekly list is rebuilt by the Optimizer, which hands on to the Writer.
        triage_fixed = any(i.get("report") and i["route"] == "standards" for i in state.get("issues", []))
        return "optimizer" if triage_fixed else "writer"

    def approval(state: CrewState) -> Command:
        triage = next(f for f in state["findings"].values() if f["kind"] == "triage")
        answer = interrupt({"question": "Approve the list, or ask for changes?", "rows": triage["rows"],
                            "shortfall": triage["plan"]["shortfall"]})  # fmt: skip
        who = answer.get("by", "Area Director")
        if answer.get("action") == "approve":
            entry = {"at": datetime.now(UTC).isoformat(timespec="seconds"), "by": who, "action": "approved",
                     "decisions": triage["plan"]["decisions"], "reasons": {r["report_id"]: r["reason"] for r in triage["rows"]}}  # fmt: skip
            return Command(
                goto="finish", update={"approval": {"status": "approved", "by": who}, "decision_log": [entry]}
            )
        rules = state.get("rules", {})
        merged = {
            "force_inspection": sorted(
                set(rules.get("force_inspection", [])) | set(answer.get("force_inspection", []))
            ),
            "force_letter": sorted(set(rules.get("force_letter", [])) | set(answer.get("force_letter", []))),
            "inspect_employers": sorted(
                set(rules.get("inspect_employers", [])) | set(answer.get("inspect_employers", []))
            ),
            "notes": {**rules.get("notes", {}), **answer.get("notes", {})},
        }
        params = {**state["params"], **({"capacity": answer["capacity"]} if "capacity" in answer else {})}
        entry = {"at": datetime.now(UTC).isoformat(timespec="seconds"), "by": who, "action": "asked for changes",
                 "changes": {k: v for k, v in answer.items() if k not in ("action", "by")}}  # fmt: skip
        return Command(goto="optimizer", update={"rules": merged, "params": params, "decision_log": [entry],
                                                  "trace": [_trace("Area Director", "asked for changes; resuming at the Optimizer")]})  # fmt: skip

    def finish(state: CrewState) -> dict[str, Any]:
        # Checks left for a person (route "person") are listed under the answer; nothing else is open here.
        return {
            "answer": state.get("answer")
            or finalize(state, [i for i in state.get("issues", []) if i["route"] == "person"])
        }

    def finalize(state: CrewState, issues: list[dict[str, Any]]) -> str:
        """Render every draft once the retries are spent.

        A line that still fails a check (an untraced number, an unknown fact, a comparison of
        unequal periods, a citation eCFR does not have) is left out, and the answer says so; the
        domain warnings that remain are listed at the end for the person to weigh.
        """
        parts = []
        number_rules = ("untraced_number", "unknown_fact", "unequal_periods")
        bad_docs = {i["doc"] for i in issues if i["rule"] in number_rules}
        bad_citations: dict[str, set[str]] = {}
        for issue in issues:
            if issue["rule"] == "unknown_citation" and issue.get("citation"):
                bad_citations.setdefault(issue["doc"], set()).add(issue["citation"])
        for doc_id, draft in sorted(state.get("drafts", {}).items()):
            if ":letter_" in doc_id:
                continue
            ledger = _ledger(draft["facts"])
            template = draft["template"]
            if doc_id in bad_docs or doc_id in bad_citations or draft["task"] in bad_citations:
                cited = bad_citations.get(doc_id, set()) | bad_citations.get(draft["task"], set())
                kept = [
                    line
                    for line in template.split("\n")
                    if not ledger.untraced(line) and not ledger.unknown(line)
                    and not ledger.unequal_periods(line) and not any(c in ledger.render(line) for c in cited)
                ]  # fmt: skip
                template = (
                    "\n".join(kept)
                    + "\n\n_One or more lines could not be traced to a tool or found in eCFR and were left out._"
                )
            parts.append(ledger.render(template))
        warnings = sorted(
            {
                i["message"]
                for i in issues
                if i["route"] in ("standards", "person") and i["rule"] != "unknown_citation"
            }
        )
        if warnings:
            parts.append("For a person to check before this goes out:\n"
                         + "\n".join(f"* {w}" for w in warnings))  # fmt: skip
        for finding in state.get("findings", {}).values():
            if finding["kind"] == "note":
                parts.append(finding["text"])
        return "\n\n".join(parts)

    def _ledger(facts: dict[str, tuple]) -> FactLedger:
        ledger = FactLedger()
        for key, (value, source, same_months) in facts.items():
            ledger.add(key, value, source, same_months=same_months)
        return ledger

    graph = StateGraph(CrewState)
    for name, function in [
        ("planner", planner), ("clarify", clarify), ("next_task", next_task), ("single_report", single_report),
        ("trend", trend), ("repeats", repeats), ("safety_talk", safety_talk), ("prevention", prevention),
        ("triage_stage1", triage_stage1), ("branch", branch), ("optimizer", optimizer), ("writer", writer),
        ("critic", critic), ("retry_optimizer", retry_optimizer), ("revise", revise), ("finish", finish),
    ]:  # fmt: skip
        graph.add_node(name, function)
    graph.add_node("approval", approval, destinations=("optimizer", "finish"))
    graph.add_edge(START, "planner")
    graph.add_conditional_edges("planner", after_planner, ["clarify", "next_task"])
    graph.add_conditional_edges("clarify", after_clarify, ["planner", "next_task"])
    graph.add_conditional_edges("next_task", route_task, [*nodes_for.values(), "writer"])
    for name in ("single_report", "trend", "repeats", "safety_talk", "prevention", "optimizer"):
        graph.add_edge(name, "next_task")
    graph.add_conditional_edges("triage_stage1", fan_out, ["branch", "optimizer"])
    graph.add_edge("branch", "optimizer")
    graph.add_edge("writer", "critic")
    graph.add_conditional_edges("critic", after_critic, ["retry_optimizer", "revise", "approval", "finish"])
    graph.add_edge("retry_optimizer", "optimizer")
    graph.add_conditional_edges("revise", after_revise, ["optimizer", "writer"])
    graph.add_edge("finish", END)
    return graph.compile(checkpointer=checkpointer)


def load_services(
    mode: Mode = "lowest_cost", handlers: dict | None = None, dense: bool | None = None, live: bool = False
) -> Services:
    """Services on the built data. With `live`, every model that has a key (or the local LM Studio
    server) answers for real; with none available, or without `live`, the offline rules answer.

    `dense` switches the embeddings on or off for both the standards search and the similar
    injury search; left as None, they are used when the embedding model is in the local cache.
    """
    from safereport.config import load_model_settings
    from safereport.ecfr import ECFR_DIR, parse_part
    from safereport.retrieval import dense_ready
    from safereport.router import offline_router

    dense = dense_ready() if dense is None else dense
    settings = load_model_settings()
    router = offline_router(settings, handlers or offline.handlers())
    if live:
        from safereport.providers import live_backends
        from safereport.spend import guarded

        backends = live_backends(settings)
        if backends:
            # Every live call goes through the response cache and the team's spend cap.
            router.backends = guarded(backends, settings)
    from safereport.similar import SimilarReports

    store = ReportStore()
    return Services(
        store=store,
        similar=SimilarReports(store, dense=dense),
        registry=IndexRegistry.load(dense=dense),
        # Every part on disk, so a Part 1926 file added later is checked as well.
        citations=CitationIndex(
            [p for xml in sorted(ECFR_DIR.glob("title-29-part-*.xml")) for p in parse_part(xml)]
        ),
        baseline=EventBaseline.load(),
        router=router,
        settings=settings,
        mode=mode,
    )


def sqlite_checkpointer(path: str = ":memory:"):
    """A SQLite checkpointer, so a paused run (a question, an approval) survives a restart."""
    import sqlite3

    from langgraph.checkpoint.sqlite import SqliteSaver

    return SqliteSaver(sqlite3.connect(path, check_same_thread=False))


def run_config(thread: str | None = None, recursion_limit: int = 60) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread or uuid.uuid4().hex}, "recursion_limit": recursion_limit}


def week_of(day: date) -> tuple[date, date]:
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=6)


__all__ = ["CrewState", "Services", "build_graph", "load_services", "normalize_name", "run_config", "week_of"]
