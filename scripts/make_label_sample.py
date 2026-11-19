"""Draw the cases the team labels by hand with the OSHA standard each injury points to.

The sample comes from manufacturing reports (NAICS 31 to 33) with a narrative of at least 15
words. It is stratified by the two digit OIICS event group, so the common hazards (caught in
machinery, falls, struck by) and a few rarer ones are all present. Every labeler gets the same
number of cases, and some cases go to two labelers so the team can measure agreement.

Usage:
    python3 -I scripts/make_label_sample.py SIR_CSV OUT_CSV [--cases 60] [--overlap 15] [--seed 42]
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import random
import re


LABELERS = ("Kevin", "Hamad", "Khoa")
FILL_IN = ("primary_standard", "secondary_standard", "confidence", "no_standard_reason", "notes")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("sir_csv")
    parser.add_argument("out_csv")
    parser.add_argument("--cases", type=int, default=60)
    parser.add_argument("--overlap", type=int, default=15)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    with open(args.sir_csv, newline="", encoding="utf-8", errors="replace") as handle:
        rows = [
            r
            for r in csv.DictReader(handle)
            if r["Primary NAICS"].startswith(("31", "32", "33")) and len(r["Final Narrative"].split()) >= 15
        ]
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[row["Event"][:2]].append(row)

    rng = random.Random(args.seed)  # noqa: S311 (a reproducible sample, not a secret)
    # Share the cases by group size, with at least one case for each of the larger groups.
    ordered = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    total = sum(len(v) for _, v in ordered)
    quota = {g: max(1, round(args.cases * len(v) / total)) for g, v in ordered if len(v) >= 50}
    while sum(quota.values()) > args.cases:
        biggest = max(quota, key=quota.get)
        quota[biggest] -= 1
    while sum(quota.values()) < args.cases:
        biggest = max(quota, key=lambda g: len(groups[g]) / quota[g])
        quota[biggest] += 1
    picked = []
    for group, count in quota.items():
        picked += rng.sample(groups[group], count)
    rng.shuffle(picked)

    out = []
    for number, row in enumerate(picked, start=1):
        first = LABELERS[(number - 1) % len(LABELERS)]
        second = LABELERS[number % len(LABELERS)] if number <= args.overlap else ""
        out.append(
            {
                "case": f"C{number:02d}",
                "sir_id": row["ID"],
                "event_date": row["EventDate"],
                "naics": row["Primary NAICS"],
                "state": row["State"],
                "narrative": re.sub(r"\s+", " ", row["Final Narrative"]).strip(),
                "event": row["EventTitle"],
                "source": row["SourceTitle"],
                "nature": row["NatureTitle"],
                "body_part": row["Part of Body Title"],
                "labeler": first,
                "second_labeler": second,
                **{name: "" for name in FILL_IN},
            }
        )
    with open(args.out_csv, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(out[0]))
        writer.writeheader()
        writer.writerows(out)
    print(f"{len(out)} cases from {len(rows)} manufacturing reports; groups: {dict(sorted(quota.items()))}")


if __name__ == "__main__":
    main()
