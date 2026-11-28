"""The trenching and excavation program before and after its scope was read (issue #27).

Usage:
    python -I scripts/eval_trenching_scope.py [--out eval/results/trenching_scope.json]

Runs the trenching program (CPL 02-00-161) twice on every Severe Injury Report outside the 2025
holdout and the answer key: once as it was before issue #27 (scope not read, so it never forced
an inspection, and its triggers matched "excavator") and once with the scope read from the
directive (forced by OSHA's trench collapse event codes or by narrative words that put the worker
in a trench or excavation; possible for source 611 or a bare mention; out for a trench drain).
The B3 sample is part of the holdout, so it is never read; the script checks that.

The rule's words were written after reading reports from every year of this data, so these are
development counts, not a test, and nothing here is labelled: "forced" means the rule forces it,
not that it is right. OSHA's own choice to inspect is shown beside each group as past practice,
not as the truth. A report the program now forces may already be Category 1 by another criterion;
the two or more hospitalized criterion is counted here, the others are not. The Texas week
(17 to 23 November 2025) is listed on its own, because the README shows its Category 1 count.

Needs data/processed/reports.parquet (`safereport build-data`). Offline, no model is called.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import replace
from datetime import date
import json
from pathlib import Path
import sys

import pandas as pd

from safereport.config import PROJECT_ROOT
from safereport.data import OIICS_3_FROM_YEAR, REPORTS_PARQUET
from safereport.evaluation import wilson
from safereport.retrieval import Document, OshaFields, reference_documents


RESULTS_DIR = PROJECT_ROOT / "eval" / "results"
HOLDOUT = PROJECT_ROOT / "data" / "splits" / "holdout_2025.csv"
ANSWER_KEY = PROJECT_ROOT / "data" / "labels" / "answer_key.csv"
B3_SAMPLE = PROJECT_ROOT / "data" / "labels" / "category1_check.csv"
TRENCHING = "CPL 02-00-161"
# The triggers on main before issue #27, kept here so the comparison does not depend on history.
BEFORE_TRIGGERS = [r"\btrench", "excavat", "cave[ -]?in"]
TEXAS_WEEK = (date(2025, 11, 17), date(2025, 11, 23))


def rate(k: int, n: int) -> dict:
    return {"inspected": k, "of": n, "rate": round(k / n, 3) if n else None,
            "wilson_95": [round(x, 3) for x in wilson(k / n, n)] if n else None}  # fmt: skip


def rules() -> tuple[Document, Document]:
    new = next(d for d in reference_documents("emphasis_program") if d.citation == TRENCHING)
    old = replace(new, triggers=BEFORE_TRIGGERS, verified=False, scope_evidence=[], scope_exclusions=[],
                  scope_event_codes=[], source_codes=[], scope_label="")  # fmt: skip
    return old, new


def reports() -> pd.DataFrame:
    frame = pd.read_parquet(REPORTS_PARQUET)
    frame["id"] = frame["id"].astype(str)
    holdout = set(pd.read_csv(HOLDOUT, dtype=str)["id"])
    b3 = set(pd.read_csv(B3_SAMPLE, dtype=str)["sir_id"])
    key = set(pd.read_csv(ANSWER_KEY, dtype=str)["sir_id"])
    if not b3 <= holdout:
        sys.exit("the B3 sample is not inside the holdout; refusing to run")
    kept = frame[~frame["id"].isin(holdout | key) & (frame["split"] != "holdout")].copy()
    # The same text the weekly list searches in stage 1: the narrative and OSHA's event title.
    kept["query"] = kept["narrative"].fillna("") + " " + kept["event_title"].fillna("")
    kept["oiics_version"] = (kept["year"] >= OIICS_3_FROM_YEAR).map({True: 3, False: 2})
    return kept


def outcome(document: Document, found) -> str:
    if found is None:
        return "none"
    return "forced" if document.verified and found.forces else "possible"


def score(frame: pd.DataFrame, old: Document, new: Document) -> pd.DataFrame:
    frame = frame.copy()
    rows = list(zip(frame["query"], frame["naics"].astype(str), frame["employer"].fillna(""),
                    frame["event_code"].astype(str).str.strip(), frame["source_code"].astype(str).str.strip(),
                    frame["oiics_version"], strict=True))  # fmt: skip
    frame["before"] = [outcome(old, old.match(q, n)) for q, n, *_ in rows]
    matches = [new.match(q, n, OshaFields(e, ev, so, int(v))) for q, n, e, ev, so, v in rows]
    frame["after"] = [outcome(new, m) for m in matches]
    frame["evidence"] = [m.evidence if m else "" for m in matches]
    return frame


def counts(frame: pd.DataFrame) -> dict:
    groups = frame.groupby(["before", "after"]).size()
    forced = frame[(frame["after"] == "forced") & (frame["before"] != "forced")]
    return {
        "reports": len(frame),
        "before_to_after": {f"{b} -> {a}": int(n) for (b, a), n in groups.items() if b != "none" or a != "none"},
        "newly_forced": len(forced),
        "newly_forced_already_two_or_more_hospitalized": int((forced["hospitalized"] >= 2).sum()),
        "newly_forced_by": {
            "osha_event_code": int(forced["evidence"].str.contains("OSHA event code").sum()),
            "narrative_words": int((~forced["evidence"].str.contains("OSHA event code")).sum()),
        },
        "osha_inspected": {
            name: rate(int(part["inspected"].sum()), len(part))
            for name, part in (
                ("newly_forced", forced),
                ("possible_after", frame[frame["after"] == "possible"]),
                ("possible_to_none", frame[(frame["before"] == "possible") & (frame["after"] == "none")]),
            )
        },
    }  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=RESULTS_DIR / "trenching_scope.json")
    args = parser.parse_args(argv)
    old, new = rules()
    frame = score(reports(), old, new)
    day = pd.to_datetime(frame["event_date"]).dt.date
    week = frame[(day >= TEXAS_WEEK[0]) & (day <= TEXAS_WEEK[1]) & (frame["state"] == "TEXAS")]
    changed = frame[frame["before"] != frame["after"]].sort_values("id")
    result = {
        "issue": "#27",
        "program": TRENCHING,
        "data": f"OSHA Severe Injury Reports, {frame['year'].min()} to {frame['year'].max()}, without the 2025 "
        "holdout (which holds the B3 sample) and the answer key. Query: narrative and OSHA event title, as in "
        "stage 1 of the weekly list; OSHA's event and source codes are read with their OIICS version.",
        "caveat": "Development counts: the rule's words were written after reading these reports. Nothing is "
        "labelled; OSHA's inspection rate is past practice, not the truth.",
        "rule": {"scope_event_codes": new.scope_event_codes, "source_codes": new.source_codes,
                 "scope_evidence": new.scope_evidence, "scope_exclusions": new.scope_exclusions},
        "all": counts(frame),
        "texas_week_changed": [
            {"id": r.id, "before": r.before, "after": r.after, "evidence": r.evidence}
            for r in week[week["before"] != week["after"]].sort_values("id").itertuples()
        ],
    }  # fmt: skip
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    listing = args.out.with_name(args.out.stem + "_changed.csv")
    with listing.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["id", "year", "naics", "inspected", "event_code", "source_code", "before", "after",
                         "evidence", "narrative"])  # fmt: skip
        for r in changed.itertuples():
            writer.writerow([r.id, r.year, r.naics, bool(r.inspected), r.event_code, r.source_code, r.before,
                             r.after, r.evidence, r.narrative])  # fmt: skip
    print(json.dumps({k: result[k] for k in ("all", "texas_week_changed")}, indent=2))
    print(f"Written to {args.out} and {listing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
