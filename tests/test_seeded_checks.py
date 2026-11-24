"""Regression checks for the B6 seeded citation evaluation."""

import hashlib
import json
from pathlib import Path
import runpy
from types import SimpleNamespace

import pytest

from safereport.evaluation import wilson


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "eval/results/seeded_checks.json"


@pytest.fixture
def report():
    return json.loads(RESULT.read_text())


@pytest.fixture
def scorer():
    return runpy.run_path(str(ROOT / "scripts/score_seeded_checks.py"))


def test_b6_frozen_inputs(report):
    for filename, field in (
        ("answer_key.csv", "answer_key_sha256"),
        ("seeded_errors.csv", "seed_sha256"),
    ):
        path = ROOT / "data/labels" / filename
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == report[field]


def test_b6_denominators(report):
    assert report["reference_reports"] == 60
    assert report["reference_with_standard"] == 51
    assert report["seeded_reports"] == 24

    seeds = report["seeded_per_case"]
    references = report["reference_per_case"]

    assert len(seeds) == 24
    assert len(references) == 51
    assert len({r["case"] for r in seeds}) == 24
    assert len({r["case"] for r in references}) == 51


def test_b6_overall_results_reconcile(report):
    rows = report["seeded_per_case"]
    overall = report["overall"]

    for field, metric in (
        ("expected_rule_detected", "expected_rule_detection"),
        ("caught", "caught"),
        ("flagged_for_person", "flagged_for_person"),
        ("any_issue", "any_issue"),
    ):
        hits = sum(row[field] for row in rows)
        n = len(rows)

        assert overall[metric]["hits"] == hits
        assert overall[metric]["total"] == n
        assert overall[metric]["rate"] == pytest.approx(hits / n)
        assert overall[metric]["ci95"] == wilson(hits / n, n)

    assert overall["caught"]["hits"] + overall["flagged_for_person"]["hits"] + overall[
        "missed_expected_rule"
    ]["hits"] == len(rows)


def test_b6_rule_results_reconcile(report):
    rows = report["seeded_per_case"]

    for rule, metrics in report["by_rule"].items():
        subset = [row for row in rows if row["expected_rule"] == rule]

        hits = sum(row["expected_rule_detected"] for row in subset)

        result = metrics["expected_rule_detection"]

        assert result["hits"] == hits
        assert result["total"] == len(subset)
        assert result["ci95"] == wilson(hits / len(subset), len(subset))

    assert len(report["by_rule"]) == 7

    assert sum(metrics["expected_rule_detection"]["total"] for metrics in report["by_rule"].values()) == len(
        rows
    )


def test_b6_false_rejections_reconcile(report):
    rows = report["reference_per_case"]

    rejected = [row for row in rows if row["wrongly_rejected"]]

    assert report["false_rejections"] == rejected

    result = report["false_rejection"]

    assert result["hits"] == len(rejected)
    assert result["total"] == 51
    assert result["rate"] == pytest.approx(len(rejected) / 51)
    assert result["ci95"] == wilson(len(rejected) / 51, 51)


@pytest.mark.parametrize(
    "issues, detected, caught, flagged",
    [
        (
            [{"rule": "energy_control", "fix": True}],
            True,
            True,
            False,
        ),
        (
            [{"rule": "energy_control", "fix": False}],
            True,
            False,
            True,
        ),
        (
            [{"rule": "other_rule", "fix": True}],
            False,
            False,
            False,
        ),
        ([], False, False, False),
    ],
)
def test_seed_scoring_distinguishes_outcomes(scorer, monkeypatch, issues, detected, caught, flagged):
    score = scorer["score_seed"]

    facts = SimpleNamespace(model_dump=lambda **kwargs: {})

    monkeypatch.setitem(
        score.__globals__,
        "intake_facts",
        lambda reference: facts,
    )

    monkeypatch.setitem(
        score.__globals__,
        "citation_issues",
        lambda *args: issues,
    )

    seed = {
        "seeded_primary": "1910.212(a)(1)",
        "seeded_secondary": "",
        "expected_rule": "energy_control",
    }

    result = score(seed, {}, None)

    assert result["expected_rule_detected"] is detected
    assert result["caught"] is caught
    assert result["flagged_for_person"] is flagged
    assert result["any_issue"] is bool(issues)


def test_b6_offline_only(report):
    assert report["mode"] == "offline"
    assert report["paid_api_calls"] == 0


def test_b6_unknown_citation_check(scorer):
    from safereport.schemas import IntakeResult

    facts = IntakeResult.model_validate(
        scorer["offline"].intake(
            {
                "report_id": "test",
                "narrative": "An employee was operating a machine.",
                "event_title": "",
            }
        )
    )

    citations = SimpleNamespace(exists=lambda citation: citation == "1910.212")

    issues = scorer["citation_issues"](facts, "1910.999(z)", "", citations)

    assert any(issue["rule"] == "unknown_citation" and issue["fix"] for issue in issues)

    valid = scorer["citation_issues"](facts, "1910.212", "", citations)

    assert not any(issue["rule"] == "unknown_citation" for issue in valid)


def test_b6_wrong_part_without_construction_index(scorer):
    from safereport.schemas import IntakeResult

    facts = IntakeResult.model_validate(
        scorer["offline"].intake(
            {
                "report_id": "test",
                "narrative": "An employee was operating a machine.",
                "event_title": "",
            }
        )
    )

    citations = SimpleNamespace(exists=lambda citation: False)

    issues = scorer["citation_issues"](facts, "1926.95", "", citations)

    rules = {issue["rule"] for issue in issues}

    assert "wrong_part" in rules
    assert "unknown_citation" not in rules


def test_b6_false_rejection_breakdown(report):
    rejected = report["false_rejections"]
    breakdown = report["false_rejection_breakdown"]

    automatic = sum(row["automatic_fix_requested"] for row in rejected)

    human_review = len(rejected) - automatic

    assert automatic == 2
    assert human_review == 2

    for name, count in (
        ("automatic_fix_requested", automatic),
        ("human_review_only", human_review),
    ):
        metric = breakdown[name]

        assert metric["hits"] == count
        assert metric["total"] == 51
        assert metric["rate"] == pytest.approx(count / 51)
        assert metric["ci95"] == wilson(count / 51, 51)
