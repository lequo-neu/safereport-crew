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


def test_narrative_disagreements_are_counted_and_the_ones_that_matter_listed():
    rows = [
        {**row("K1", notes="narrative: 2 hospitalized, count says 1"), "hospitalized": "1"},
        {
            **row("K2", notes="narrative: 3 hospitalized, count says 1", worker_under_18="yes"),
            "hospitalized": "1",
        },
        {**row("K3", notes="fatality"), "hospitalized": "0"},
        {
            **row("K4", notes="narrative: 1 hospitalized, count says 2", two_or_more_hospitalized="yes"),
            "hospitalized": "2",
        },
    ]
    found = score_mod.narrative_vs_count(rows)
    assert found["count"] == 3 and found["cases"] == ["K1", "K2", "K4"]
    # K2 stays Category 1 through another criterion, so only K1 and K4 could change.
    assert found["could_change_category_one"] == ["K1", "K4"]


def test_score_reports_employer_history_and_imminent_danger_apart():
    rows = [
        row("K1", similar_report_within_12_months="yes"),
        row(
            "K2",
            similar_report_within_12_months="cannot_tell",
            notes="similar_report_within_12_months: possible",
        ),
        row("K3", imminent_danger="yes"),
        row("K4"),
    ]
    result = score_mod.score(rows, crew(), "human")
    assert result["employer_history_labels"] == {"yes": 1, "no": 2, "cannot_tell": 1, "unlabelled": 0}
    assert result["imminent_danger_yes_cases"] == ["K3"]
    assert result["imminent_danger_apart"] == {"cannot_tell": 3, "yes": 1}
    assert result["narrative_vs_count"]["count"] == 0


def full(case: str, **labels: str) -> dict[str, str]:
    return {**row(case, **labels), "confidence": "high"}


def test_only_complete_untagged_hand_labels_go_to_eval_results():
    good = [full("K1"), full("K2", worker_under_18="yes")]
    out = Path("eval/results/category1_check.json")
    score_mod.check_outputs("human", out, good, None)  # complete hand labels: allowed

    with pytest.raises(SystemExit, match="unlabelled"):
        score_mod.check_outputs("human", out, [*good, {**full("K3"), "confidence": ""}], None)
    with pytest.raises(SystemExit, match="AI-assisted"):
        tagged = {**full("K3"), "notes": "[AI-assisted, user-approved label from CSV export; not blind]"}
        score_mod.check_outputs("human", out, [*good, tagged], None)
    with pytest.raises(SystemExit, match="follow the four criteria"):
        score_mod.check_outputs("human", out, [*good, {**full("K3"), "category_one": "yes"}], None)
    with pytest.raises(SystemExit, match="eval/results"):
        score_mod.check_outputs("ai-provisional", out, good, None)
    with pytest.raises(SystemExit, match="eval/provisional"):
        score_mod.check_outputs("human", out, good, Path("eval/results/ai_vs_human.json"))
    # Outside eval/results anything may be scored (it is labelled by its source).
    score_mod.check_outputs(
        "ai-provisional", Path("elsewhere/x.json"), [{**full("K3"), "confidence": ""}], None
    )


def test_shared_cases_say_when_the_second_file_is_not_complete():
    mine = [full("K1"), full("K2"), full("K3")]
    second = [full("K2"), {**full("K3"), "category_one": ""}, full("K9")]
    assert score_mod.shared_cases(mine, second) == {
        "shared": 2,
        "unlabelled_in_second": ["K3"],
        "complete": False,
    }
    assert score_mod.shared_cases(mine, [full("K1")])["complete"] is True
    assert score_mod.shared_cases(mine, [full("K7")])["complete"] is False
