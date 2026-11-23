"""Score the crew's Category 1 rules against a labelled copy of the B3 sample (issue #4).

    python scripts/score_category1_check.py --labels data/labels/category1_check.csv \
        --source human --out eval/results/category1_check.json

The crew's rules run as they are (offline, nothing paid): for each case, the same inputs the
weekly triage gives `triage.category_one` (the employer history, the verified emphasis programs).
Each criterion is then compared with the labels on the cases they decide: recall (rule yes among
label yes) and false alarms (rule yes among label no), with Wilson 95% intervals, plus the
cannot_tell share and its reasons. Imminent danger is reported apart (settled rule 5).

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
from typing import Any


CRITERIA = {
    "two_or_more_hospitalized": "two or more hospitalized",
    "worker_under_18": "worker under 18",
    "similar_report_within_12_months": "similar report from the employer within 12 months",
    "emphasis_program_hazard": "hazard under an emphasis program",
}
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


def category_one_label(row: dict[str, str]) -> str:
    four = [row[c] for c in CRITERIA]
    return "yes" if "yes" in four else ("no" if all(v == "no" for v in four) else "cannot_tell")


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
    args = parser.parse_args()
    if args.source != "human" and "eval/results" in args.out.as_posix():
        raise SystemExit("AI-provisional scores do not go in eval/results; write them elsewhere.")

    from safereport.graph import load_services

    rows = list(csv.DictReader(args.labels.open(encoding="utf-8")))
    crew = crew_flags(load_services(), rows)
    result = score(rows, crew, args.source)
    result["rules"] = "triage.category_one on the checked-out code, offline"
    result["crew"] = crew
    if args.second:
        second = list(csv.DictReader(args.second.open(encoding="utf-8")))
        result["agreement"] = agreement(rows, second, [*CRITERIA, "category_one"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
