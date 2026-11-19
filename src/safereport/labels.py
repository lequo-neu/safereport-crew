"""The hand checked answer key for the standards retrieval evaluation.

Three of us reviewed the labels in data/labels/to_label_<name>.csv. A case reviewed by two
people keeps their label when both chose the same CFR section; otherwise the label settled by
the team in settlements.csv is used, and a disagreement nobody settled stops the merge. A label
found wrong later is corrected in corrections.csv, applied last and marked as pending.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from safereport.config import PROJECT_ROOT
from safereport.schemas import AnswerKeyCase, cfr_section


LABEL_DIR = PROJECT_ROOT / "data" / "labels"
LABELERS = ("Kevin", "Hamad", "Khoa")
REVIEWED_FIELDS = ("primary_standard", "secondary_standard", "confidence", "notes")
KEY_FIELDS = (
    "case",
    "sir_id",
    "narrative",
    "event",
    "source",
    "primary_standard",
    "primary_section",
    "accepted_sections",
    "no_standard_reason",
    "confidence",
    "labelers",
    "status",
)


class UnsettledLabelsError(ValueError):
    """Two reviewers chose different sections and the team has not settled the case yet."""


@dataclass
class MergeSummary:
    cases: int
    with_standard: int
    shared: int
    same_section: int
    identical: int
    settled: int

    @property
    def agreement(self) -> float:
        return self.same_section / self.shared if self.shared else 0.0


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def merge_labels(label_dir: Path = LABEL_DIR) -> tuple[list[dict[str, str]], MergeSummary]:
    """Build the answer key rows from the three label files and the settlements."""
    by_case: dict[str, dict[str, dict[str, str]]] = {}
    for name in LABELERS:
        for row in _read(label_dir / f"to_label_{name}.csv"):
            by_case.setdefault(row["case"], {})[name] = row
    settled_path = label_dir / "settlements.csv"
    settled = {r["case"]: r for r in _read(settled_path)} if settled_path.exists() else {}
    # A label that the review found wrong after the merge (C20: the press was locked out, so the
    # lockout label contradicts the narrative). Applied last, and marked until the team confirms.
    corrections_path = label_dir / "corrections.csv"
    corrections = {r["case"]: r for r in _read(corrections_path)} if corrections_path.exists() else {}

    rows, unsettled = [], []
    shared = same_section = identical = 0
    for case in sorted(by_case):
        labels = by_case[case]
        first = next(iter(labels.values()))
        if len(labels) == 1:
            final, status = first, "single labeler"
        else:
            shared += 1
            a, b = labels.values()
            same = cfr_section(a["primary_standard"]) == cfr_section(b["primary_standard"])
            same_section += same
            identical += all(a[k] == b[k] for k in REVIEWED_FIELDS)
            if same:
                final, status = a, "both agreed"
            elif case in settled:
                final, status = settled[case], "settled by the team"
            else:
                unsettled.append(case)
                continue
        if case in corrections:
            final, status = corrections[case], "corrected, pending team confirmation"
        accepted = [cfr_section(final["primary_standard"]), cfr_section(final.get("secondary_standard", ""))]
        rows.append(
            {
                "case": case,
                "sir_id": first["sir_id"],
                "narrative": first["narrative"],
                "event": first["event"],
                "source": first["source"],
                "primary_standard": final["primary_standard"].strip(),
                "primary_section": accepted[0],
                "accepted_sections": ";".join(dict.fromkeys(s for s in accepted if s)),
                "no_standard_reason": final.get("no_standard_reason", "").strip(),
                "confidence": final["confidence"].strip(),
                "labelers": ";".join(labels),
                "status": status,
            }
        )
    if unsettled:
        raise UnsettledLabelsError(f"settle these cases in {settled_path} first: {', '.join(unsettled)}")

    summary = MergeSummary(
        cases=len(rows),
        with_standard=sum(1 for r in rows if r["primary_section"]),
        shared=shared,
        same_section=same_section,
        identical=identical,
        settled=sum(r["status"] == "settled by the team" for r in rows),
    )
    return rows, summary


def write_answer_key(rows: list[dict[str, str]], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=KEY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def load_answer_key(path: Path = LABEL_DIR / "answer_key.csv") -> list[AnswerKeyCase]:
    """The answer key, validated case by case."""
    return [AnswerKeyCase.model_validate(row) for row in _read(path)]
