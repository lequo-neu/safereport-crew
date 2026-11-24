"""Hand labels of the reports the #30 work route adds, and the rule's precision (issue #37).

Usage:
    python -I scripts/score_staffing_falls_labels.py

Reads Hamad's labels (`data/labels/staffing_falls_added_Hamad.csv`, written by hand, not by an AI
tool) and adds them to `eval/results/staffing_falls_added.csv` (columns `construction_fall`,
`confidence`, `reason`) and to `eval/results/staffing_falls.json` (key `hand_labels`). Run it after
`scripts/eval_staffing_falls.py`, which rewrites both files without the labels.

The question for each report: construction work and a fall to a lower level (yes, no or
cannot_tell). Precision is reported for the development slice (2015 to 2019, read while the rule
was written) and the test slice (2020 on, outside the 2025 holdout) apart, three ways, because
cannot_tell is neither right nor wrong:

* strict: yes / all labelled (cannot_tell counted as not confirmed); the headline;
* decided: yes / (yes + no), cannot_tell left out;
* lenient: (yes + cannot_tell) / all labelled, the upper bound.

The labels change nothing in the rule. Offline, no model is called.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import sys

from safereport.config import PROJECT_ROOT
from safereport.evaluation import wilson


LABELS = PROJECT_ROOT / "data" / "labels" / "staffing_falls_added_Hamad.csv"
RESULTS_DIR = PROJECT_ROOT / "eval" / "results"
LISTING = RESULTS_DIR / "staffing_falls_added.csv"
RESULTS = RESULTS_DIR / "staffing_falls.json"
ANSWERS = ("yes", "no", "cannot_tell")
CONFIDENCE = ("high", "medium", "low")
LABEL_COLUMNS = ["construction_fall", "confidence", "reason"]
SLICES = ("development", "test")
QUESTION = "construction work and a fall to a lower level (yes, no or cannot_tell)"


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def load_labels(path: Path = LABELS) -> list[dict[str, str]]:
    """The labels as written; refuses a missing, unknown or duplicate value instead of guessing."""
    _, rows = read_csv(path)
    problems = []
    seen: set[str] = set()
    for row in rows:
        rid = row.get("id", "")
        if rid in seen:
            problems.append(f"{rid}: labelled twice")
        seen.add(rid)
        if row.get("slice") not in SLICES:
            problems.append(f"{rid}: slice {row.get('slice')!r}")
        if row.get("construction_fall") not in ANSWERS:
            problems.append(f"{rid}: construction_fall {row.get('construction_fall')!r}")
        if row.get("confidence") not in CONFIDENCE:
            problems.append(f"{rid}: confidence {row.get('confidence')!r}")
        if not (row.get("reason") or "").strip():
            problems.append(f"{rid}: no reason")
    if problems:
        raise ValueError("invalid labels: " + "; ".join(problems))
    return rows


def share(k: int, n: int) -> dict:
    return {
        "k": k,
        "n": n,
        "rate": round(k / n, 3) if n else None,
        "wilson_95": wilson(k / n, n) if n else None,
    }


def precision(rows: list[dict[str, str]]) -> dict:
    counts = {a: sum(r["construction_fall"] == a for r in rows) for a in ANSWERS}
    yes, no, unsure = counts["yes"], counts["no"], counts["cannot_tell"]
    return {
        "labelled": len(rows),
        "answers": counts,
        "precision_strict": share(yes, len(rows)),
        "precision_decided": share(yes, yes + no),
        "precision_lenient": share(yes + unsure, len(rows)),
        "not_yes": {
            r["id"]: f"{r['construction_fall']} ({r['confidence']}): {r['reason']}"
            for r in rows
            if r["construction_fall"] != "yes"
        },
    }


def check_against_listing(labels: list[dict[str, str]], listing: list[dict[str, str]]) -> None:
    want = {r["id"]: r["slice"] for r in listing}
    got = {r["id"]: r["slice"] for r in labels}
    if want != got:
        missing, extra = sorted(set(want) - set(got)), sorted(set(got) - set(want))
        moved = sorted(i for i in set(want) & set(got) if want[i] != got[i])
        raise ValueError(
            f"labels do not match the added reports: missing {missing}, extra {extra}, other slice {moved}"
        )


def summary(labels: list[dict[str, str]]) -> dict:
    return {
        "issue": "#37",
        "labeller": "Hamad, by hand (not an AI tool); data/labels/staffing_falls_added_Hamad.csv",
        "question": QUESTION,
        "headline": "precision_strict on the test slice: cannot_tell is counted as not confirmed",
        "rule_changed_after_labelling": False,
        **{name: precision([r for r in labels if r["slice"] == name]) for name in SLICES},
    }


def write_listing(path: Path, fields: list[str], listing: list[dict[str, str]], labels: dict) -> None:
    fields = [f for f in fields if f not in LABEL_COLUMNS] + LABEL_COLUMNS
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in listing:
            writer.writerow({**row, **{c: labels[row["id"]][c] for c in LABEL_COLUMNS}})


def main(argv: list[str] | None = None) -> int:
    del argv
    labels = load_labels()
    fields, listing = read_csv(LISTING)
    check_against_listing(labels, listing)
    result = json.loads(RESULTS.read_text(encoding="utf-8"))
    if result.get("issue") != "#30":
        sys.exit(f"{RESULTS} is not the #30 evaluation")
    write_listing(LISTING, fields, listing, {r["id"]: r for r in labels})
    result["caveat"] = (
        "'added' counts what the rule flags; whether each added report is construction work and a fall "
        "to a lower level is in 'hand_labels' (issue #37). OSHA's inspection rate is past practice, and "
        "an SIR inspection depends on more than the Falls program."
    )
    result["hand_labels"] = summary(labels)
    RESULTS.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result["hand_labels"], indent=2))
    print(f"Written to {RESULTS} and {LISTING}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
