"""Merge the three label files into data/labels/answer_key.csv.

Usage:
    python scripts/merge_labels.py [LABEL_DIR]

The logic lives in safereport.labels; this script only runs it and prints the summary.
"""

from __future__ import annotations

from pathlib import Path
import sys

from safereport.labels import LABEL_DIR, UnsettledLabelsError, merge_labels, write_answer_key


def main() -> None:
    label_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else LABEL_DIR
    try:
        rows, summary = merge_labels(label_dir)
    except UnsettledLabelsError as error:
        sys.exit(str(error))
    out = label_dir / "answer_key.csv"
    write_answer_key(rows, out)
    print(
        f"{summary.cases} cases written to {out}: {summary.with_standard} with a standard, "
        f"{summary.cases - summary.with_standard} without.\n"
        f"Shared cases: {summary.shared}, same section {summary.same_section} ({summary.agreement:.1%}), "
        f"identical in every field {summary.identical}, settled {summary.settled}."
    )


if __name__ == "__main__":
    main()
