"""Independent holdout evaluation for measured routing (B7)."""

from __future__ import annotations

from collections.abc import Callable
import csv
from pathlib import Path

from pydantic import Field

from safereport.data import HOLDOUT_IDS
from safereport.evaluation import score_retrieval, wilson
from safereport.labels import LABEL_DIR, load_answer_key
from safereport.retrieval import IndexRegistry
from safereport.schemas import AnswerKeyCase


SLICE_FILE = LABEL_DIR / "router_slice.csv"
PEER_FILE = LABEL_DIR / "router_slice_hamad_15.csv"


class SliceCase(AnswerKeyCase):
    """A B7 case with the existing answer-key validation rules."""

    case: str = Field(pattern=r"^B7-\d{3}$")


def read_rows(path: Path) -> list[dict[str, str]]:
    """Read label files without changing their contents."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def validate_membership(
    rows: list[dict[str, str]],
    holdout_ids: set[str],
    answer_ids: set[str],
) -> None:
    """Check the sample before using any reference labels."""
    if len(rows) != 50:
        raise ValueError("B7 requires exactly 50 reports")

    expected = {f"B7-{i:03d}" for i in range(1, 51)}
    cases = {row["case"] for row in rows}
    report_ids = {row["sir_id"] for row in rows}

    if cases != expected:
        raise ValueError("Missing or duplicate B7 case IDs")

    if len(report_ids) != 50:
        raise ValueError("Duplicate B7 report IDs")

    if report_ids - holdout_ids:
        raise ValueError("B7 contains reports outside the holdout")

    if report_ids & answer_ids:
        raise ValueError("B7 overlaps the original answer key")

    for row in rows:
        if not row["narrative"].strip():
            raise ValueError(f"{row['case']}: empty narrative")

        if row["naics"][:2] not in {"31", "32", "33"}:
            raise ValueError(f"{row['case']}: outside manufacturing")


def load_router_slice(
    path: Path = SLICE_FILE,
) -> list[SliceCase]:
    """Load the final reference labels before evaluation."""
    rows = read_rows(path)

    holdout_ids = {row["id"] for row in read_rows(HOLDOUT_IDS)}
    answer_ids = {case.sir_id for case in load_answer_key()}

    validate_membership(rows, holdout_ids, answer_ids)

    cases = []

    for row in rows:
        case = SliceCase.model_validate(row)

        if not case.labelers:
            raise ValueError(f"{case.case}: missing labeler")

        if case.status == "corrected, pending team confirmation":
            raise ValueError(f"{case.case}: pending confirmation")

        if case.has_standard and case.no_standard_reason.strip():
            raise ValueError(f"{case.case}: conflicting label fields")

        if not case.has_standard and (case.primary_section or case.accepted_sections):
            raise ValueError(f"{case.case}: inconsistent no-standard label")

        cases.append(case)

    if not any(case.has_standard for case in cases):
        raise ValueError("No eligible standards to evaluate")

    return cases


def evaluate_slice(
    registry: IndexRegistry,
    cases: list[SliceCase],
    terms_for: Callable[[AnswerKeyCase], list[str]] | None = None,
) -> dict:
    """Score B7 using the same retrieval metrics as the answer key."""
    eligible = sum(case.has_standard for case in cases)

    if eligible == 0:
        raise ValueError("No eligible standards to evaluate")

    scores = score_retrieval(
        registry,
        list(cases),
        with_codes=True,
        terms_for=terms_for,
    )

    if scores.cases != eligible:
        raise ValueError("Retrieval denominator does not match eligible cases")

    hits = int(scores.per_case["strict_at_3"].sum())
    rate = hits / eligible

    return {
        "total_reports": len(cases),
        "eligible_reports": eligible,
        "excluded_no_standard": len(cases) - eligible,
        "strict_at_3_hits": hits,
        "strict_at_3": rate,
        "strict_at_3_ci95": wilson(rate, eligible),
        "scores": scores.as_dict(),
        "per_case": scores.per_case.to_dict("records"),
    }
