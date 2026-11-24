"""The Falls program for staffing agencies doing construction work, old rule against new (issue #30).

Usage:
    python -I scripts/eval_staffing_falls.py [--out eval/results/staffing_falls.json]

Runs the Falls program (CPL 03-00-025) twice on every Severe Injury Report outside the 2025
holdout: once as it was in the Basic stage, once with the work route for staffing agencies
(NAICS 5613). The B3 sample is part of the holdout, so it is never read; the script checks that.
The reports are split by year: 2015 to 2019 were read while the construction words were written
(development), and 2020 onward were run once after the rule was fixed (test). Nothing is labelled
here: an added report is one the new rule flags, not one known to be right. OSHA's own choice to
inspect is shown beside each group as past practice, not as the truth. The hand labels of the
added reports (issue #37) are added by scripts/score_staffing_falls_labels.py; run it after this.

Needs data/processed/reports.parquet (`safereport build-data`). Offline, no model is called.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import replace
import json
from pathlib import Path
import re
import sys

import pandas as pd

from safereport.config import PROJECT_ROOT
from safereport.data import REPORTS_PARQUET
from safereport.evaluation import wilson
from safereport.retrieval import Document, _first, _triggered, reference_documents


RESULTS_DIR = PROJECT_ROOT / "eval" / "results"
HOLDOUT = PROJECT_ROOT / "data" / "splits" / "holdout_2025.csv"
B3_SAMPLE = PROJECT_ROOT / "data" / "labels" / "category1_check.csv"
FALLS = "CPL 03-00-025"
DEVELOPMENT_UNTIL = 2019
# Measured as an alternative and not adopted: the employer's name is not the work the worker did.
EMPLOYER_NAME = re.compile(r"construct|roofing|builders?\b|contracting|scaffold", re.IGNORECASE)


def rate(k: int, n: int) -> dict:
    return {"inspected": k, "of": n, "rate": round(k / n, 3) if n else None,
            "wilson_95": [round(x, 3) for x in wilson(k / n, n)] if n else None}  # fmt: skip


def rules() -> tuple[Document, Document]:
    new = next(d for d in reference_documents("emphasis_program") if d.citation == FALLS)
    old = replace(new, work_industries=[], work_evidence=[], work_exclusions=[], work_label="")
    return old, new


def outside_holdout() -> pd.DataFrame:
    frame = pd.read_parquet(REPORTS_PARQUET)
    frame["id"] = frame["id"].astype(str)
    holdout = set(pd.read_csv(HOLDOUT, dtype=str)["id"])
    b3 = set(pd.read_csv(B3_SAMPLE, dtype=str)["sir_id"])
    if not b3 <= holdout:
        sys.exit("the B3 sample is not inside the holdout; refusing to run")
    kept = frame[~frame["id"].isin(holdout) & (frame["split"] != "holdout")].copy()
    if kept["id"].isin(b3).any():
        sys.exit("a B3 report is outside the holdout; refusing to run")
    # The same text the weekly list searches in stage 1: the narrative and OSHA's event title.
    kept["query"] = kept["narrative"].fillna("") + " " + kept["event_title"].fillna("")
    kept["slice"] = kept["year"].map(lambda y: "development" if y <= DEVELOPMENT_UNTIL else "test")
    return kept


def score(frame: pd.DataFrame, old: Document, new: Document) -> pd.DataFrame:
    frame = frame.copy()
    frame["old"] = [old.applies_to(q, n) for q, n in zip(frame["query"], frame["naics"], strict=True)]
    matches = [new.match(q, n) for q, n in zip(frame["query"], frame["naics"], strict=True)]
    frame["new"] = [m is not None for m in matches]
    frame["route"] = [m.route if m else "" for m in matches]
    frame["evidence"] = [m.evidence if m else "" for m in matches]
    frame["staffing"] = frame["naics"].str.startswith("5613")
    # The parts of the work route, read for staffing reports only (the rest cannot take it).
    staffing = frame["staffing"]
    queries = frame.loc[staffing, "query"]
    frame["fall"] = frame["work"] = frame["vetoed"] = False
    frame["evidence_rule"] = -1
    frame.loc[staffing, "fall"] = [any(_triggered(p, q) for p in new.triggers) for q in queries]
    frame.loc[staffing, "work"] = [_first(new.work_evidence, q) is not None for q in queries]
    frame.loc[staffing, "vetoed"] = [_first(new.work_exclusions, q) is not None for q in queries]
    frame.loc[staffing, "evidence_rule"] = [
        next((i for i, p in enumerate(new.work_evidence) if re.search(p, q, re.IGNORECASE)), -1)
        for q in queries
    ]
    return frame


def summary(frame: pd.DataFrame, new: Document) -> dict:
    staffing = frame[frame["staffing"]]
    added = frame[frame["new"] & ~frame["old"]]
    falls_23 = frame[frame["naics"].str.startswith("23") & frame["old"]]
    staffing_falls_left = staffing[staffing["fall"] & ~staffing["new"]]
    named = staffing[staffing["fall"] & ~staffing["work"] & ~staffing["new"]
                     & staffing["employer"].fillna("").str.contains(EMPLOYER_NAME)]  # fmt: skip
    return {
        "reports": len(frame),
        "flagged_by_falls": {"old": int(frame["old"].sum()), "new": int(frame["new"].sum())},
        "added": len(added),
        "removed": int((frame["old"] & ~frame["new"]).sum()),
        "changed_outside_naics_5613": int(((frame["old"] != frame["new"]) & ~frame["staffing"]).sum()),
        "staffing_reports": len(staffing),
        "staffing_fall_to_lower_level_wording": int(staffing["fall"].sum()),
        "staffing_flagged": {"old": int(staffing["old"].sum()), "new": int(staffing["new"].sum())},
        "staffing_with_construction_words_and_a_fall_vetoed": int(
            (staffing["work"] & staffing["fall"] & staffing["vetoed"] & ~staffing["old"]).sum()
        ),
        "added_by_naics": dict(Counter(added["naics"]).most_common()),
        "added_by_evidence_pattern": {
            new.work_evidence[i]: n for i, n in Counter(added["evidence_rule"]).most_common()
        },
        "osha_inspected": {
            "added": rate(int(added["inspected"].sum()), len(added)),
            "staffing_fall_wording_not_flagged": rate(
                int(staffing_falls_left["inspected"].sum()), len(staffing_falls_left)
            ),
            "construction_naics_23_flagged_by_falls": rate(int(falls_23["inspected"].sum()), len(falls_23)),
        },
        "not_adopted_employer_name_route": {
            "would_add": len(named),
            "examples": named["employer"].head(8).tolist(),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=RESULTS_DIR / "staffing_falls.json")
    args = parser.parse_args(argv)
    old, new = rules()
    frame = score(outside_holdout(), old, new)
    added = frame[frame["new"] & ~frame["old"]].sort_values("id")
    result = {
        "issue": "#30",
        "program": FALLS,
        "data": "OSHA Severe Injury Reports, January 2015 to November 2025, without the 1,000 reports of "
        "the 2025 holdout (data/splits/holdout_2025.csv), which hold the B3 sample. Query: narrative and "
        "OSHA event title, as in stage 1 of the weekly list.",
        "slices": {
            "development": f"{frame['year'].min()} to {DEVELOPMENT_UNTIL}: read while the construction words "
            "were written",
            "test": f"{DEVELOPMENT_UNTIL + 1} to {frame['year'].max()}: run once with the rule fixed",
        },
        "rule": {
            "work_industries": new.work_industries,
            "work_evidence": new.work_evidence,
            "work_exclusions": new.work_exclusions,
        },
        "caveat": "No report here is labelled. 'added' counts what the rule flags, not what is right; "
        "OSHA's inspection rate is past practice, and an SIR inspection depends on more than the Falls program.",
        "all": summary(frame, new),
        **{name: summary(frame[frame["slice"] == name], new) for name in ("development", "test")},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    listing = args.out.with_name(args.out.stem + "_added.csv")
    with listing.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            ["id", "slice", "year", "naics", "employer", "inspected", "event_title", "evidence", "narrative"]
        )
        for r in added.itertuples():
            writer.writerow([r.id, r.slice, r.year, r.naics, r.employer, bool(r.inspected), r.event_title,
                             r.evidence, r.narrative])  # fmt: skip
    print(json.dumps({k: result[k] for k in ("all", "development", "test")}, indent=2))
    print(f"Written to {args.out} and {listing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
