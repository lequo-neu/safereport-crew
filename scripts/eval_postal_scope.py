"""The warehousing program for NAICS 491110 before and after the postal scope rule (issue #26).

Usage:
    python -I scripts/eval_postal_scope.py [--out eval/results/postal_scope.json]

Runs the warehousing program (CPL 03-00-026) twice on every NAICS 491110 Severe Injury Report
outside the 2025 holdout and the answer key: once as it was before issue #26 (every report with a
trigger forced Category 1) and once with the scope rule (forced only at a named processing or
distribution facility; out at delivery or a retail counter; possible otherwise). The B3 sample is
part of the holdout, so it is never read; the script checks that.

The rule's words were written after reading 491110 reports from every year of this data, so these
are development counts, not a test, and nothing here is labelled: "forced" means the rule forces
it, not that it is right. OSHA's own choice to inspect is shown beside each group as past practice,
not as the truth. Only the warehousing program can apply to 491110, so a report it no longer
forces leaves Category 1 unless another criterion keeps it there; the two or more hospitalized
criterion is counted here, the employer history criterion is not (it needs the employer index).

Needs data/processed/reports.parquet (`safereport build-data`). Offline, no model is called.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import replace
import json
from pathlib import Path
import sys

import pandas as pd

from safereport.config import PROJECT_ROOT
from safereport.data import REPORTS_PARQUET
from safereport.evaluation import wilson
from safereport.retrieval import Document, OshaFields, reference_documents


RESULTS_DIR = PROJECT_ROOT / "eval" / "results"
HOLDOUT = PROJECT_ROOT / "data" / "splits" / "holdout_2025.csv"
ANSWER_KEY = PROJECT_ROOT / "data" / "labels" / "answer_key.csv"
B3_SAMPLE = PROJECT_ROOT / "data" / "labels" / "category1_check.csv"
WAREHOUSING = "CPL 03-00-026"
POSTAL = "491110"


def rate(k: int, n: int) -> dict:
    return {"inspected": k, "of": n, "rate": round(k / n, 3) if n else None,
            "wilson_95": [round(x, 3) for x in wilson(k / n, n)] if n else None}  # fmt: skip


def rules() -> tuple[Document, Document]:
    new = next(d for d in reference_documents("emphasis_program") if d.citation == WAREHOUSING)
    old = replace(new, scope_industries=[], scope_evidence=[], scope_exclusions=[], scope_label="")
    return old, new


def postal_reports() -> pd.DataFrame:
    frame = pd.read_parquet(REPORTS_PARQUET)
    frame["id"] = frame["id"].astype(str)
    holdout = set(pd.read_csv(HOLDOUT, dtype=str)["id"])
    b3 = set(pd.read_csv(B3_SAMPLE, dtype=str)["sir_id"])
    key = set(pd.read_csv(ANSWER_KEY, dtype=str)["sir_id"])
    if not b3 <= holdout:
        sys.exit("the B3 sample is not inside the holdout; refusing to run")
    kept = frame[~frame["id"].isin(holdout | key) & (frame["split"] != "holdout")]
    kept = kept[kept["naics"].astype(str).str.startswith(POSTAL)].copy()
    # The same text the weekly list searches in stage 1: the narrative and OSHA's event title.
    kept["query"] = kept["narrative"].fillna("") + " " + kept["event_title"].fillna("")
    return kept


def outcome(found) -> str:
    if found is None:
        return "none"
    return "forced" if found.forces else "possible"


def score(frame: pd.DataFrame, old: Document, new: Document) -> pd.DataFrame:
    frame = frame.copy()
    frame["before"] = [outcome(old.match(q, n)) for q, n in zip(frame["query"], frame["naics"], strict=True)]
    matches = [
        new.match(q, n, OshaFields(employer=e or ""))
        for q, n, e in zip(frame["query"], frame["naics"], frame["employer"], strict=True)
    ]
    frame["after"] = [outcome(m) for m in matches]
    frame["evidence"] = [m.evidence if m else "" for m in matches]
    return frame


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=RESULTS_DIR / "postal_scope.json")
    args = parser.parse_args(argv)
    old, new = rules()
    frame = score(postal_reports(), old, new)
    groups = frame.groupby(["before", "after"]).size()
    removed = frame[(frame["before"] == "forced") & (frame["after"] != "forced")]
    result = {
        "issue": "#26",
        "program": WAREHOUSING,
        "data": f"OSHA Severe Injury Reports with NAICS {POSTAL}, {frame['year'].min()} to {frame['year'].max()}, "
        "without the 2025 holdout (which holds the B3 sample) and the answer key. Query: narrative and OSHA "
        "event title, as in stage 1 of the weekly list; the employer's name is read for facility words.",
        "caveat": "Development counts: the rule's words were written after reading these reports. Nothing is "
        "labelled; OSHA's inspection rate is past practice, not the truth.",
        "rule": {"scope_evidence": new.scope_evidence, "scope_exclusions": new.scope_exclusions},
        "reports": len(frame),
        "before_to_after": {f"{b} -> {a}": int(n) for (b, a), n in groups.items()},
        "forced": {"before": int((frame["before"] == "forced").sum()), "after": int((frame["after"] == "forced").sum())},
        "newly_forced": int(((frame["before"] != "forced") & (frame["after"] == "forced")).sum()),
        "no_longer_forced": len(removed),
        "no_longer_forced_but_two_or_more_hospitalized": int((removed["hospitalized"] >= 2).sum()),
        "osha_inspected": {
            f"{name}": rate(int(part["inspected"].sum()), len(part))
            for name, part in (
                ("still_forced", frame[frame["after"] == "forced"]),
                ("forced_to_possible", frame[(frame["before"] == "forced") & (frame["after"] == "possible")]),
                ("forced_to_none", frame[(frame["before"] == "forced") & (frame["after"] == "none")]),
            )
        },
    }  # fmt: skip
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    listing = args.out.with_name(args.out.stem + "_changed.csv")
    changed = frame[frame["before"] != frame["after"]].sort_values("id")
    with listing.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["id", "year", "employer", "inspected", "before", "after", "evidence", "narrative"])
        for r in changed.itertuples():
            writer.writerow(
                [r.id, r.year, r.employer, bool(r.inspected), r.before, r.after, r.evidence, r.narrative]
            )
    print(json.dumps({k: v for k, v in result.items() if k not in ("rule", "data", "caveat")}, indent=2))
    print(f"Written to {args.out} and {listing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
