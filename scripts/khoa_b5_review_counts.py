"""Reconcile Khoa's manually reviewed B5 cases from the committed CSVs."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "docs" / "reviews" / "khoa_b5"
RESULT = ROOT / "eval" / "results" / "khoa_b5_review_counts.json"


def read_table(filename: str) -> list[dict[str, str]]:
    with (TABLES / filename).open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def review_counts() -> dict:
    texas = read_table("khoa_texas_15_reviewed.csv")
    construction = read_table("khoa_construction_20_reviewed.csv")
    changed = sum(row["changed_between_checkpoints"] == "True" for row in texas)
    human = sum(bool(row["human_review_rules"]) for row in texas)
    object_hits = sum(row["object_fell_on_worker"] == "Yes" for row in construction)
    worker_falls = sum(row["worker_also_fell"] == "Yes" for row in construction)
    mixed = sum(
        row["object_fell_on_worker"] == "Yes" and row["worker_also_fell"] == "Yes" for row in construction
    )
    if (len(texas), changed, human, len(construction), object_hits, worker_falls, mixed) != (
        15,
        11,
        4,
        20,
        17,
        4,
        1,
    ):
        raise ValueError("B5 reviewed tables differ from the documented audit; reconcile before committing.")
    texas_ids = [row["report_id"] for row in texas]
    construction_ids = [row["report_id"] for row in construction]
    if len(set(texas_ids)) != len(texas_ids) or len(set(construction_ids)) != len(construction_ids):
        raise ValueError("Duplicate report IDs in a B5 review table.")
    return {
        "reviewer": "Khoa Tran",
        "method": "Offline checkpoint reconstruction and manual narrative review; purpose-selected construction sample",
        "source_command": "python scripts/khoa_b5_review_counts.py",
        "texas": {
            "reviewed_flagged_cases": len(texas),
            "citation_changed_reports": changed,
            "human_review_cases": human,
            "reported_week_total_offline": 31,
            "reported_team_corrections_not_yet_reproduced": 12,
        },
        "construction_exclusions": {
            "reviewed_sample": len(construction),
            "object_struck_worker_cases": object_hits,
            "worker_fell_cases": worker_falls,
            "mixed_object_and_worker_fall_cases": mixed,
            "worker_fall_only_cases": worker_falls - mixed,
            "object_only_cases": object_hits - mixed,
            "local_helper_exclusion_total_not_reproduced_here": 32,
            "team_plan_exclusion_total_not_reproduced_here": 33,
        },
        "limitations": [
            "The 31-report and 32/33 comparison totals come from separate audit runs or the team plan, not these two sampled CSV files.",
            "This sample was selected for review, not randomly sampled; do not extrapolate its error fraction.",
            "Citation revisions are not necessarily correct OSHA standards or substantiated violations.",
        ],
    }


def main() -> None:
    output = review_counts()
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("B5 reviewed cases reconciled:", output["texas"], output["construction_exclusions"])
    print("Saved", RESULT)


if __name__ == "__main__":
    main()
