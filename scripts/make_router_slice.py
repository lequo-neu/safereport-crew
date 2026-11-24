"""Build a reproducible B7 manufacturing evaluation slice.

Uses the 2025 holdout, excludes the existing answer key,
and leaves all OSHA standards labels blank for independent review.
"""

import csv
from datetime import datetime
from pathlib import Path
import random


ROOT = Path(__file__).resolve().parents[1]
SEED = 5374
SAMPLE_SIZE = 50
REVIEW_SIZE = 15

RAW = ROOT / "data/raw/January2015toNovember2025.csv"
HOLDOUT = ROOT / "data/splits/holdout_2025.csv"
KEY = ROOT / "data/labels/answer_key.csv"

OUTPUT = ROOT / "data/labels/router_slice.csv"
REVIEW = ROOT / "data/labels/router_slice_hamad_15.csv"

COLUMNS = [
    "case",
    "sir_id",
    "naics",
    "narrative",
    "event",
    "source",
    "nature",
    "body_part",
    "primary_standard",
    "secondary_standard",
    "primary_section",
    "accepted_sections",
    "no_standard_reason",
    "confidence",
    "notes",
    "labelers",
    "status",
]


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, records):
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(records)


def main():
    if OUTPUT.exists() or REVIEW.exists():
        raise SystemExit("STOP: B7 output already exists. Nothing overwritten.")

    holdout = {r["id"].strip() for r in read_csv(HOLDOUT)}
    key = {r["sir_id"].strip() for r in read_csv(KEY)}

    eligible = []
    for row in read_csv(RAW):
        sir_id = row["ID"].strip()
        naics = row["Primary NAICS"].strip()
        narrative = row["Final Narrative"].strip()
        event_date = row["EventDate"].strip()

        if sir_id not in holdout or sir_id in key:
            continue
        if naics[:2] not in {"31", "32", "33"}:
            continue
        if not narrative:
            continue

        try:
            year = datetime.strptime(event_date, "%m/%d/%Y").year
        except ValueError:
            continue

        if year != 2025:
            continue

        eligible.append(row)

    ids = [r["ID"].strip() for r in eligible]
    if len(ids) != len(set(ids)):
        raise SystemExit("STOP: Duplicate eligible report IDs.")

    if len(eligible) < SAMPLE_SIZE:
        raise SystemExit(f"STOP: Only {len(eligible)} eligible manufacturing reports.")

    # Fixed seed for reproducible research sampling, not cryptography.
    rng = random.Random(SEED)  # noqa: S311
    selected = rng.sample(sorted(eligible, key=lambda r: r["ID"]), SAMPLE_SIZE)

    records = []
    for number, row in enumerate(selected, 1):
        records.append(
            {
                "case": f"B7-{number:03d}",
                "sir_id": row["ID"].strip(),
                "naics": row["Primary NAICS"].strip(),
                "narrative": row["Final Narrative"].strip(),
                "event": row["EventTitle"].strip(),
                "source": row["SourceTitle"].strip(),
                "nature": row["NatureTitle"].strip(),
                "body_part": row["Part of Body Title"].strip(),
                "primary_standard": "",
                "secondary_standard": "",
                "primary_section": "",
                "accepted_sections": "",
                "no_standard_reason": "",
                "confidence": "",
                "notes": "",
                "labelers": "",
                "status": "",
            }
        )

    review = rng.sample(records, REVIEW_SIZE)
    selected_ids = {r["sir_id"] for r in records}

    assert len(records) == 50
    assert len(review) == 15
    assert len(selected_ids) == 50
    assert selected_ids <= holdout
    assert not (selected_ids & key)

    write_csv(OUTPUT, records)
    write_csv(REVIEW, review)

    print("=== B7 SAMPLE VALIDATION ===")
    print("Random seed:", SEED)
    print("Eligible manufacturing cases:", len(eligible))
    print("Selected cases:", len(records))
    print("Independent review cases:", len(review))
    print("Answer-key overlap:", len(selected_ids & key))
    print("Industry scope: manufacturing, NAICS 31-33")
    print("Reference labels: blank")
    print("Created:", OUTPUT)
    print("Created:", REVIEW)
    print("B7 SAMPLE CREATION PASSED")


if __name__ == "__main__":
    main()
