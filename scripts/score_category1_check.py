"""Score the crew's Category 1 rules against a labelled copy of the B3 sample (issue #4).

    python scripts/score_category1_check.py --labels data/labels/category1_check.csv \
        --source human --out eval/results/category1_check.json

The crew's rules run as they are (offline, nothing paid): for each case, the same inputs the
weekly triage gives `triage.category_one` (the employer history, the verified emphasis programs).
Each criterion is then compared with the labels on the cases they decide: recall (rule yes among
label yes) and false alarms (rule yes among label no), with Wilson 95% intervals, plus the
cannot_tell share and its reasons. Imminent danger is reported apart (settled rule 5). Also
reported: the employer history labels for #18, and the notes that say the narrative gives another
hospitalized number than the count (rule 7).

Only complete hand labels go in `eval/results/`: the command refuses a file with an unlabelled row,
a `category_one` that does not follow the four criteria, or a row marked as AI-assisted.

    python scripts/score_category1_check.py --labels data/labels/category1_check.csv \
        --source human --out eval/results/category1_check.json \
        --second data/labels/category1_check_Khoa.csv \
        --ai-pass <the AI first pass> --ai-out eval/provisional/category1_ai_vs_human.json

`--ai-out` holds only how often the AI first pass agrees with the hand labels (no per-case answer),
and never goes in `eval/results/`.

`--source` must say who wrote the labels. A file from a model (`ai-provisional`) is scored the
same way, but its numbers measure agreement with that model, not the rules' accuracy, and the
output says so.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path
import re
from typing import Any


CRITERIA = {
    "two_or_more_hospitalized": "two or more hospitalized",
    "worker_under_18": "worker under 18",
    "similar_report_within_12_months": "similar report from the employer within 12 months",
    "emphasis_program_hazard": "hazard under an emphasis program",
}
LABELLED = [*CRITERIA, "imminent_danger", "category_one", "confidence"]
# Rows approved from an AI-assisted file carry this in notes; they are not hand labels.
AI_ASSISTED_MARK = "[AI-assisted"
SOURCES = {
    "human": "labels written by a person, by hand",
    "ai-provisional": "provisional labels from an AI model and scripts; agreement with them is not accuracy",
}


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float] | None:
    """The Wilson 95% interval for k successes in n trials (None when n is 0)."""
    if n == 0:
        return None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4))


def rate(k: int, n: int) -> dict[str, Any]:
    return {"k": k, "n": n, "rate": round(k / n, 4) if n else None, "ci95": wilson(k, n)}


def compare(labels: list[str], rules: list[bool], reasons: list[str] | None = None) -> dict[str, Any]:
    """Rule output against labels: recall, false alarms, and the cases the labels cannot decide."""
    pairs = list(zip(labels, rules, strict=True))
    yes = [rule for label, rule in pairs if label == "yes"]
    no = [rule for label, rule in pairs if label == "no"]
    unclear = [i for i, (label, _) in enumerate(pairs) if label == "cannot_tell"]
    blank = sum(1 for label, _ in pairs if label == "")
    out = {
        "cases": len(pairs), "label_yes": len(yes), "label_no": len(no), "cannot_tell": len(unclear),
        "unlabelled": blank, "rule_yes": sum(rules),
        "recall": rate(sum(yes), len(yes)), "false_alarm_rate": rate(sum(no), len(no)),
        "cannot_tell_share": rate(len(unclear), len(pairs)),
        "cannot_tell_rule_yes": sum(rules[i] for i in unclear),
    }  # fmt: skip
    if reasons is not None:
        out["cannot_tell_reasons"] = dict(
            Counter(reasons[i] or "no reason given" for i in unclear).most_common()
        )
    return out


def reason(notes: str, column: str) -> str:
    """The `column: reason` part of the notes, cut to its first words so reasons can be counted."""
    for part in notes.split(";"):
        name, _, why = part.strip().partition(":")
        if name.strip() == column:
            return " ".join(why.split()[:6])
    return ""


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def category_one_label(row: dict[str, str]) -> str:
    four = [row[c] for c in CRITERIA]
    return "yes" if "yes" in four else ("no" if all(v == "no" for v in four) else "cannot_tell")


def narrative_vs_count(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Rule 7: notes saying the narrative gives another hospitalized number than the count.

    The label goes by the count. A case "could change Category 1" when reading the narrative's
    number instead would flip the two-or-more criterion and no other criterion is yes.
    """
    cases, could_change = [], []
    for r in rows:
        found = re.search(r"narrative:\s*(\d+)\s*hospitali[sz]ed", r.get("notes", ""), re.IGNORECASE)
        if not found:
            continue
        cases.append(r["case"])
        said, count = int(found.group(1)), int(r.get("hospitalized") or 0)
        others = any(r.get(c) == "yes" for c in CRITERIA if c != "two_or_more_hospitalized")
        if (said >= 2) != (count >= 2) and not others:
            could_change.append(r["case"])
    return {"count": len(cases), "cases": cases, "could_change_category_one": could_change}


def label_problems(rows: list[dict[str, str]]) -> list[str]:
    """Why a file cannot be scored as hand labels into eval/results (empty when it can)."""
    out = []
    for r in rows:
        blank = [c for c in LABELLED if not (r.get(c) or "").strip()]
        if blank:
            out.append(f"{r['case']}: unlabelled {', '.join(blank)}")
        elif r["category_one"] != category_one_label(r):
            out.append(f"{r['case']}: category_one does not follow the four criteria")
        if AI_ASSISTED_MARK in (r.get("notes") or ""):
            out.append(f"{r['case']}: marked as AI-assisted, not a hand label")
    return out


def check_outputs(source: str, out: Path, rows: list[dict[str, str]], ai_out: Path | None) -> None:
    """Refuse to write anything but complete hand labels' scores into eval/results."""
    if ai_out is not None and "eval/results" in ai_out.as_posix():
        raise SystemExit("The AI pass comparison does not go in eval/results; use eval/provisional.")
    if "eval/results" not in out.as_posix():
        return
    if source != "human":
        raise SystemExit("AI-provisional scores do not go in eval/results; write them elsewhere.")
    found = label_problems(rows)
    if found:
        raise SystemExit(
            "Not complete hand labels, so not written to eval/results:\n  " + "\n  ".join(found[:20])
        )


def score(rows: list[dict[str, str]], crew: dict[str, dict[str, bool]], source: str) -> dict[str, Any]:
    if source not in SOURCES:
        raise ValueError(f"--source must be one of {sorted(SOURCES)}")
    rows = [r for r in rows if r["case"] in crew]
    result: dict[str, Any] = {"labels": SOURCES[source], "source": source, "cases": len(rows), "criteria": {}}
    for column, trigger in CRITERIA.items():
        result["criteria"][column] = compare(
            [r[column] for r in rows], [crew[r["case"]][trigger] for r in rows],
            [reason(r.get("notes", ""), column) for r in rows],
        )  # fmt: skip
    written = [r["category_one"] for r in rows]
    result["category_one"] = compare(written, [crew[r["case"]]["category_one"] for r in rows])
    result["category_one"]["written_differs_from_the_guide_rule"] = [
        r["case"] for r in rows if r["category_one"] and r["category_one"] != category_one_label(r)
    ]
    imminent = Counter(r["imminent_danger"] or "unlabelled" for r in rows)
    result["imminent_danger_apart"] = dict(imminent)
    result["imminent_danger_yes_cases"] = [r["case"] for r in rows if r["imminent_danger"] == "yes"]
    history = Counter(r["similar_report_within_12_months"] or "unlabelled" for r in rows)
    result["employer_history_labels"] = {v: history[v] for v in ["yes", "no", "cannot_tell", "unlabelled"]}
    result["narrative_vs_count"] = narrative_vs_count(rows)
    result["disagreements"] = {
        column: {
            "rule_yes_label_no": [r["case"] for r in rows if r[column] == "no" and crew[r["case"]][trigger]],
            "rule_no_label_yes": [
                r["case"] for r in rows if r[column] == "yes" and not crew[r["case"]][trigger]
            ],
        }
        for column, trigger in {**CRITERIA, "category_one": "category_one"}.items()
    }
    return result


def agreement(a: list[dict[str, str]], b: list[dict[str, str]], columns: list[str]) -> dict[str, Any]:
    """Two people's labels on the same cases: raw agreement and Cohen's kappa per column."""
    by_case = {r["case"]: r for r in b}
    shared = [(r, by_case[r["case"]]) for r in a if r["case"] in by_case]
    out = {}
    for column in columns:
        pairs = [(x[column], y[column]) for x, y in shared if x[column] and y[column]]
        n = len(pairs)
        if not n:
            out[column] = {"n": 0}
            continue
        observed = sum(x == y for x, y in pairs) / n
        values = {v for pair in pairs for v in pair}
        expected = sum(
            (sum(x == v for x, _ in pairs) / n) * (sum(y == v for _, y in pairs) / n) for v in values
        )
        kappa = None if expected == 1 else round((observed - expected) / (1 - expected), 4)
        out[column] = {"n": n, "agreement": round(observed, 4), "kappa": kappa}
    return out


def shared_cases(a: list[dict[str, str]], b: list[dict[str, str]]) -> dict[str, Any]:
    """Which cases both files hold, and which of them the second file leaves unlabelled."""
    mine = {r["case"] for r in a}
    shared = [r for r in b if r["case"] in mine]
    missing = [r["case"] for r in shared if any(not (r.get(c) or "").strip() for c in LABELLED)]
    return {"shared": len(shared), "unlabelled_in_second": missing, "complete": bool(shared) and not missing}


def crew_flags(services: Any, rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    """What the crew's rules decide for each case, with the inputs the weekly triage gives them."""
    from safereport.graph import _report_from_row
    from safereport.triage import category_one

    flags = {}
    for row in rows:
        found = services.store.frame("SELECT * FROM reports WHERE CAST(id AS VARCHAR) = ?", [row["sir_id"]])
        if found.empty:
            continue
        data = found.to_dict("records")[0]
        report = _report_from_row(data)
        hits = services.registry.search(f"{report.narrative} {report.event_title}", naics=report.naics, k=3)
        emphasis = [h.document.citation for h in hits.emphasis if h.document.verified]
        division = str(data.get("event_code_v3") or report.event_code)[:1]
        repeats = [m.report_id for m in services.employers(report.state).repeats_within(
            report.employer, report.state, report.event_date, division=division, city=report.city,
            zip_code=report.zip, naics=report.naics, exclude_id=report.id)]  # fmt: skip
        triggers = {t.criterion for t in category_one(report, emphasis, repeats)}
        flags[row["case"]] = {**{name: name in triggers for name in CRITERIA.values()},
                              "category_one": bool(triggers), "emphasis": emphasis, "repeats": repeats}  # fmt: skip
    return flags


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--source", choices=sorted(SOURCES), required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--second", type=Path, help="a second person's labels on shared cases, for agreement")
    parser.add_argument(
        "--ai-pass", type=Path, help="the AI first pass, compared with these labels afterwards"
    )
    parser.add_argument("--ai-out", type=Path, help="where that comparison goes (not eval/results)")
    args = parser.parse_args()
    if bool(args.ai_pass) != bool(args.ai_out):
        raise SystemExit("--ai-pass and --ai-out go together.")
    rows = read(args.labels)
    check_outputs(args.source, args.out, rows, args.ai_out)

    from safereport.graph import load_services

    crew = crew_flags(load_services(), rows)
    result = score(rows, crew, args.source)
    result["rules"] = "triage.category_one on the checked-out code, offline"
    result["crew"] = crew
    if args.second:
        second = read(args.second)
        if any(AI_ASSISTED_MARK in (r.get("notes") or "") for r in second):
            raise SystemExit(f"{args.second} has rows marked as AI-assisted; agreement needs hand labels.")
        result["agreement_cases"] = shared_cases(rows, second)
        if result["agreement_cases"]["complete"]:
            result["agreement"] = agreement(rows, second, [*CRITERIA, "imminent_danger", "category_one"])
        else:
            result["agreement"] = "pending: the second file does not label every shared case"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"wrote {args.out}")
    if args.ai_pass:
        ai = read(args.ai_pass)
        compared = {
            "what": "the AI first pass against these labels: agreement with a person, not accuracy",
            "labels": SOURCES[args.source], "cases": shared_cases(rows, ai)["shared"],
            "agreement": agreement(rows, ai, [*CRITERIA, "category_one"]),
        }  # fmt: skip
        args.ai_out.parent.mkdir(parents=True, exist_ok=True)
        args.ai_out.write_text(json.dumps(compared, indent=1), encoding="utf-8")
        print(f"wrote {args.ai_out}")


if __name__ == "__main__":
    main()
