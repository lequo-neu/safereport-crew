"""Regression tests for measured retrieval accuracy (B7)."""

from pydantic import ValidationError
import pytest

from safereport.config import load_model_settings
from safereport.router import Signals, offline_router
from safereport.router_slice import SliceCase, validate_membership
from safereport.schemas import AnswerKeyCase


def test_unmeasured_model_uses_prior():
    settings = load_model_settings()
    model = settings.model("gpt_nano")
    model.measured = {}

    router = offline_router(settings, {})

    assert router.accuracy(model, "retrieve") == (
        model.prior["retrieve"],
        True,
    )


def test_measured_retrieval_preserves_other_priors():
    settings = load_model_settings()
    model = settings.model("gpt_nano")

    # Synthetic fixture, not an experimental result.
    model.measured = {"retrieve": 0.65}
    model.measured_source = "test fixture"

    router = offline_router(settings, {})

    assert router.accuracy(model, "retrieve") == (
        0.65,
        False,
    )

    for step in ("code", "decide", "write"):
        assert router.accuracy(model, step) == (
            model.prior[step],
            True,
        )


def test_router_choice_uses_measured_accuracy():
    settings = load_model_settings()

    for model in settings.models:
        model.measured = {"retrieve": 0.50}
        model.measured_source = "test fixture"

    model = settings.model("gpt_nano")
    model.measured = {"retrieve": 0.99}

    router = offline_router(settings, {})
    choice = router.choose("retrieve", Signals(), mode="best_quality")

    assert choice.model.name == "gpt_nano"
    assert choice.based_on_prior is False


@pytest.mark.parametrize("invalid", [-0.1, 1.2])
def test_invalid_measured_accuracy_rejected(invalid):
    model = load_model_settings().model("gpt_nano")
    payload = model.model_dump()
    payload["measured"] = {"retrieve": invalid}

    with pytest.raises(ValidationError):
        type(model).model_validate(payload)


@pytest.mark.parametrize("boundary", [0.0, 1.0])
def test_valid_measured_accuracy_boundaries(boundary):
    model = load_model_settings().model("gpt_nano")
    payload = model.model_dump()
    payload["measured"] = {"retrieve": boundary}
    payload["measured_source"] = "test fixture"

    validated = type(model).model_validate(payload)

    assert validated.measured["retrieve"] == boundary


def test_measured_zero_does_not_fall_back_to_prior():
    settings = load_model_settings()
    model = settings.model("gpt_nano")
    model.measured = {"retrieve": 0.0}
    model.measured_source = "test fixture"

    router = offline_router(settings, {})

    assert router.accuracy(model, "retrieve") == (
        0.0,
        False,
    )


@pytest.fixture
def b7_label():
    return {
        "case": "B7-001",
        "sir_id": "synthetic-report",
        "narrative": "Synthetic test narrative.",
        "event": "Caught in equipment",
        "source": "Machine",
        "primary_standard": "1910.212(a)(1)",
        "primary_section": "1910.212",
        "accepted_sections": "1910.212",
        "no_standard_reason": "",
        "confidence": "medium",
        "labelers": "Khoa",
        "status": "single labeler",
    }


def test_b7_schema_accepts_slice_id(b7_label):
    case = SliceCase.model_validate(b7_label)
    assert case.case == "B7-001"
    assert case.has_standard
    assert case.accepted_sections == ["1910.212"]


def test_original_schema_rejects_b7_id(b7_label):
    with pytest.raises(ValidationError):
        AnswerKeyCase.model_validate(b7_label)


def test_b7_schema_rejects_original_key_id(b7_label):
    b7_label["case"] = "C01"
    with pytest.raises(ValidationError):
        SliceCase.model_validate(b7_label)


def test_b7_schema_rejects_missing_label_status(b7_label):
    b7_label["status"] = ""
    with pytest.raises(ValidationError):
        SliceCase.model_validate(b7_label)


def test_b7_schema_rejects_inconsistent_section(b7_label):
    b7_label["primary_section"] = "1910.147"
    with pytest.raises(ValidationError):
        SliceCase.model_validate(b7_label)


def test_b7_schema_requires_no_standard_reason(b7_label):
    b7_label["primary_standard"] = ""
    b7_label["primary_section"] = ""
    b7_label["accepted_sections"] = ""

    with pytest.raises(ValidationError):
        SliceCase.model_validate(b7_label)

    b7_label["no_standard_reason"] = "vague narrative"

    case = SliceCase.model_validate(b7_label)
    assert not case.has_standard


@pytest.fixture
def sample_rows():
    return [
        {
            "case": f"B7-{i:03d}",
            "sir_id": f"synthetic-{i}",
            "narrative": "Synthetic test narrative.",
            "naics": "311111",
        }
        for i in range(1, 51)
    ]


def test_b7_membership_accepts_independent_holdout(sample_rows):
    ids = {row["sir_id"] for row in sample_rows}
    validate_membership(sample_rows, ids, {"original-key-id"})


def test_b7_membership_rejects_answer_key_overlap(sample_rows):
    ids = {row["sir_id"] for row in sample_rows}

    with pytest.raises(ValueError, match="overlaps"):
        validate_membership(sample_rows, ids, {"synthetic-1"})


def test_b7_membership_rejects_non_holdout(sample_rows):
    ids = {row["sir_id"] for row in sample_rows}
    ids.remove("synthetic-1")

    with pytest.raises(ValueError, match="outside the holdout"):
        validate_membership(sample_rows, ids, set())


def test_b7_membership_rejects_duplicate_reports(sample_rows):
    ids = {row["sir_id"] for row in sample_rows}
    sample_rows[1]["sir_id"] = sample_rows[0]["sir_id"]

    with pytest.raises(ValueError, match="Duplicate"):
        validate_membership(sample_rows, ids, set())


def test_b7_retrieval_denominator(b7_label):
    from types import SimpleNamespace

    from safereport.router_slice import evaluate_slice

    cases = []

    for i in range(1, 5):
        row = dict(b7_label)
        row["case"] = f"B7-{i:03d}"
        row["sir_id"] = f"synthetic-{i}"
        row["narrative"] = f"Synthetic case {i}"
        row["accepted_sections"] = "1910.212;1910.147"

        if i == 4:
            row["primary_standard"] = ""
            row["primary_section"] = ""
            row["accepted_sections"] = ""
            row["no_standard_reason"] = "vague narrative"

        cases.append(SliceCase.model_validate(row))

    class FakeRegistry:
        def __init__(self):
            self.calls = 0

        def search(self, query, *, naics, k, terms):
            self.calls += 1
            assert naics == "31"
            assert k == 3

            if query.startswith("Synthetic case 1"):
                found = ["1910.212", "1910.147", "1910.178"]
            elif query.startswith("Synthetic case 2"):
                found = ["1910.178", "1910.147", "1910.212"]
            elif query.startswith("Synthetic case 3"):
                found = ["1910.147", "1910.178", "1910.179"]
            else:
                raise AssertionError("No-standard case should be excluded")

            return SimpleNamespace(sections=[SimpleNamespace(section=section) for section in found])

    registry = FakeRegistry()
    result = evaluate_slice(registry, cases)

    assert registry.calls == 3
    assert result["total_reports"] == 4
    assert result["eligible_reports"] == 3
    assert result["excluded_no_standard"] == 1
    assert result["strict_at_3_hits"] == 2
    assert result["strict_at_3"] == pytest.approx(2 / 3)
    assert result["scores"]["lenient_at_3"] == 1.0
    assert len(result["per_case"]) == 3


def test_b7_evaluation_rejects_empty_denominator(b7_label):
    from safereport.router_slice import evaluate_slice

    b7_label["primary_standard"] = ""
    b7_label["primary_section"] = ""
    b7_label["accepted_sections"] = ""
    b7_label["no_standard_reason"] = "vague narrative"

    case = SliceCase.model_validate(b7_label)

    with pytest.raises(ValueError, match="No eligible"):
        evaluate_slice(None, [case])
