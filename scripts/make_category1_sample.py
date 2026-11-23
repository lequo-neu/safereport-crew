"""Draw the 100 reports for the hand check of the Category 1 rules (task B3, issue #4).

The reports come from the 2025 holdout (`data/splits/holdout_2025.csv`), which no rule, weight
or threshold was tuned on. It is a simple random draw with a fixed seed, so anyone who runs the
script on the same OSHA file gets the same reports in the same order. Of the 100, a seeded 15 are
also written to a second file for the teammate who checks them; that file holds no labels, so
the check is blind.

The label columns are left empty for a person to fill in by hand, following
docs/CATEGORY1_LABELING.md. The file carries no rule output and not whether OSHA inspected, so
neither can sway the labels. The script refuses to overwrite a file that already exists, so a
second run never wipes labels already written.

Usage:
    python -I scripts/make_category1_sample.py data/raw/January2015toNovember2025.csv
    [--holdout data/splits/holdout_2025.csv] [--out data/labels/category1_check.csv]
    [--check-out data/labels/category1_check_Khoa.csv] [--cases 100] [--shared 15] [--seed 42]
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import random
import re
import sys


SEED = 42
CASES = 100
SHARED = 15
CHECKER = "Khoa"

# Given: what a labeler reads. The report as OSHA published it, nothing a rule or OSHA decided.
GIVEN = (
    "case", "sir_id", "event_date", "employer", "city", "state", "naics", "hospitalized",
    "amputation", "loss_of_eye", "narrative", "event", "source", "nature", "body_part",
)  # fmt: skip
# Filled in by hand, one value per criterion of OSHA's memo of 4 March 2016: yes, no or
# cannot_tell; then the overall answer and the evidence.
CRITERIA = (
    "two_or_more_hospitalized",
    "worker_under_18",
    "similar_report_within_12_months",
    "emphasis_program_hazard",
    "imminent_danger",
)
FILL_IN = (*CRITERIA, "category_one", "emphasis_program", "evidence", "confidence", "notes")


def read_reports(sir_csv: Path) -> dict[str, dict[str, str]]:
    """Every report in OSHA's file, by ID."""
    with sir_csv.open(newline="", encoding="utf-8", errors="replace") as handle:
        return {row["ID"].strip(): row for row in csv.DictReader(handle)}


def read_holdout(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [row["id"].strip() for row in csv.DictReader(handle)]


def count(value: str) -> str:
    """OSHA writes counts as "1.00"; a labeler reads "1". A blank is no one."""
    return str(int(float(value))) if value.strip() else "0"


def draw(
    reports: dict[str, dict[str, str]],
    holdout: list[str],
    cases: int = CASES,
    shared: int = SHARED,
    seed: int = SEED,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """The labeler's rows and the checker's rows (the shared cases, with blank labels)."""
    if not 0 <= shared <= cases:
        raise ValueError(f"the shared cases ({shared}) must be between 0 and the cases ({cases})")
    missing = [i for i in holdout if i not in reports]
    if missing:
        raise ValueError(
            f"{len(missing)} holdout ids are not in the OSHA file (first: {missing[0]}); "
            "is it the January 2015 to November 2025 file?"
        )
    # Sorted first, so the draw depends on the seed alone, not on the order of either file.
    pool = sorted(holdout)
    if len(pool) < cases:
        raise ValueError(f"the holdout has {len(pool)} reports, fewer than the {cases} asked for")
    rng = random.Random(seed)  # noqa: S311 (a reproducible sample, not a secret)
    picked = rng.sample(pool, cases)
    checked = set(rng.sample(picked, shared))

    rows, check_rows = [], []
    for number, report_id in enumerate(picked, start=1):
        report = reports[report_id]
        row = {
            "case": f"K{number:03d}",
            "sir_id": report_id,
            "event_date": report["EventDate"].split()[0],
            "employer": report["Employer"].strip(),
            "city": report["City"].strip(),
            "state": report["State"].strip(),
            "naics": report["Primary NAICS"].strip(),
            "hospitalized": count(report["Hospitalized"]),
            "amputation": count(report["Amputation"]),
            "loss_of_eye": count(report["Loss of Eye"]),
            "narrative": re.sub(r"\s+", " ", report["Final Narrative"]).strip(),
            "event": report["EventTitle"].strip(),
            "source": report["SourceTitle"].strip(),
            "nature": report["NatureTitle"].strip(),
            "body_part": report["Part of Body Title"].strip(),
        }
        blank = dict.fromkeys(FILL_IN, "")
        rows.append({**row, "checked_by": CHECKER if report_id in checked else "", **blank})
        if report_id in checked:
            check_rows.append({**row, **blank})
    return rows, check_rows


def write(path: Path, rows: list[dict[str, str]], force: bool = False) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"{path} exists; it may hold labels. Move it away or pass --force.")
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="" so Windows does not turn the csv module's \r\n into \r\r\n.
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sir_csv", type=Path, help="OSHA's January2015toNovember2025.csv")
    parser.add_argument("--holdout", type=Path, default=Path("data/splits/holdout_2025.csv"))
    parser.add_argument("--out", type=Path, default=Path("data/labels/category1_check.csv"))
    parser.add_argument("--check-out", type=Path, default=Path(f"data/labels/category1_check_{CHECKER}.csv"))
    parser.add_argument("--cases", type=int, default=CASES)
    parser.add_argument("--shared", type=int, default=SHARED)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument(
        "--force", action="store_true", help="overwrite existing files (and any labels in them)"
    )
    args = parser.parse_args(argv)

    try:
        rows, check_rows = draw(
            read_reports(args.sir_csv), read_holdout(args.holdout), args.cases, args.shared, args.seed
        )
        for path in (args.out, args.check_out):
            if path.exists() and not args.force:
                raise FileExistsError(f"{path} exists; it may hold labels. Move it away or pass --force.")
        write(args.out, rows, args.force)
        if check_rows:
            write(args.check_out, check_rows, args.force)
    except (ValueError, FileExistsError) as error:
        print(f"Not written: {error}", file=sys.stderr)
        return 1
    print(f"{len(rows)} reports (seed {args.seed}) written to {args.out}")
    if check_rows:
        print(f"{len(check_rows)} of them, with no labels, written to {args.check_out} for {CHECKER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
