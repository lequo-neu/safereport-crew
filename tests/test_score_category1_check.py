"""The B3 scoring on hand-made labels: no data, no model, nothing paid."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location(
    "score_category1_check", Path(__file__).parents[1] / "scripts" / "score_category1_check.py"
)
score_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(score_mod)

CRITERIA = list(score_mod.CRITERIA)


def row(case: str, notes: str = "", **labels: str) -> dict[str, str]:
    base = {c: "no" for c in CRITERIA} | {"imminent_danger": "cannot_tell", "notes": notes}
    base |= labels
    return {"case": case, **base, "category_one": score_mod.category_one_label(base)}


def crew(**yes: list[str]) -> dict[str, dict[str, bool]]:
    cases = {case for cases in yes.values() for case in cases} | {"K1", "K2", "K3", "K4"}
    out = {}
    for case in cases:
        flags = {name: case in yes.get(column, []) for column, name in score_mod.CRITERIA.items()}
        out[case] = {**flags, "category_one": any(flags.values())}
    return out


def test_wilson_matches_known_values():
    assert score_mod.wilson(0, 0) is None
    low, high = score_mod.wilson(8, 10)
    assert (low, high) == pytest.approx((0.4902, 0.9433), abs=1e-4)
    assert score_mod.wilson(10, 10)[1] == 1.0


def test_recall_and_false_alarms_are_counted_on_decided_cases_only():
    rows = [
        row("K1", emphasis_program_hazard="yes"),
        row("K2", emphasis_program_hazard="yes"),
        row("K3", emphasis_program_hazard="cannot_tell", notes="emphasis_program_hazard: scope unclear"),
        row("K4"),
    ]
    result = score_mod.score(rows, crew(emphasis_program_hazard=["K1", "K3", "K4"]), "human")
    emphasis = result["criteria"]["emphasis_program_hazard"]
    assert emphasis["recall"]["k"] == 1 and emphasis["recall"]["n"] == 2
    assert emphasis["false_alarm_rate"]["k"] == 1 and emphasis["false_alarm_rate"]["n"] == 1
    assert emphasis["cannot_tell"] == 1 and emphasis["cannot_tell_rule_yes"] == 1
    assert emphasis["cannot_tell_reasons"] == {"scope unclear": 1}
    assert result["disagreements"]["emphasis_program_hazard"] == {
        "rule_yes_label_no": ["K4"],
        "rule_no_label_yes": ["K2"],
    }


def test_category_one_follows_the_guide_and_a_written_mismatch_is_listed():
    rows = [
        row("K1", worker_under_18="yes"),
        row("K2"),
        row("K3", similar_report_within_12_months="cannot_tell"),
    ]
    rows[1]["category_one"] = "yes"  # written by hand against the guide's rule
    result = score_mod.score(rows, crew(), "human")
    assert [score_mod.category_one_label(r) for r in rows] == ["yes", "no", "cannot_tell"]
    assert result["category_one"]["written_differs_from_the_guide_rule"] == ["K2"]


def test_the_source_must_be_named_and_ai_labels_say_what_they_measure():
    rows = [row("K1")]
    with pytest.raises(ValueError):
        score_mod.score(rows, crew(), "someone")
    assert "not accuracy" in score_mod.score(rows, crew(), "ai-provisional")["labels"]


def test_unlabelled_cases_are_neither_right_nor_wrong():
    rows = [row("K1"), {**row("K2"), "two_or_more_hospitalized": ""}]
    hosp = score_mod.score(rows, crew(), "human")["criteria"]["two_or_more_hospitalized"]
    assert hosp["unlabelled"] == 1 and hosp["label_no"] == 1


def test_agreement_gives_cohens_kappa():
    a = [row("K1", worker_under_18="yes"), row("K2"), row("K3"), row("K4", worker_under_18="yes")]
    b = [
        row("K1", worker_under_18="yes"),
        row("K2"),
        row("K3", worker_under_18="yes"),
        row("K4", worker_under_18="yes"),
    ]
    result = score_mod.agreement(a, b, ["worker_under_18", "two_or_more_hospitalized"])
    assert result["worker_under_18"] == {"n": 4, "agreement": 0.75, "kappa": 0.5}
    assert result["two_or_more_hospitalized"]["kappa"] is None  # all agree on one value


def test_the_crew_flags_come_from_the_rules(small_services):
    first = small_services.store.frame("SELECT * FROM reports ORDER BY id LIMIT 1").to_dict("records")[0]
    flags = score_mod.crew_flags(small_services, [{"case": "K1", "sir_id": str(first["id"])}])
    assert set(flags["K1"]) >= {*score_mod.CRITERIA.values(), "category_one"}
    assert flags["K1"]["category_one"] == any(flags["K1"][n] for n in score_mod.CRITERIA.values())
