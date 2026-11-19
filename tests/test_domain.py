from __future__ import annotations

import pytest

from safereport import offline
from safereport.domain import check_citation
from safereport.labels import load_answer_key
from safereport.schemas import IntakeResult


def facts(**fields) -> IntakeResult:
    base = {"report_id": "1", "activity": "normal operation", "hazard_type": "machine", "machine_or_hazard": "",
            "material": "", "injury": "amputation", "event_code": "", "confidence": 0.9, "fatality_potential": False}  # fmt: skip
    return IntakeResult(**{**base, **fields})


@pytest.mark.parametrize(
    ("intake", "primary", "rule"),
    [
        (facts(activity="unjamming"), "1910.212(a)(1)", "energy_control"),
        (facts(material="food", machine_or_hazard="band saw"), "1910.213", "woodworking_only"),
        (facts(machine_or_hazard="press"), "1910.217", "mechanical_press_only"),
        (
            facts(hazard_type="other_vehicle", machine_or_hazard="front end loader"),
            "1910.178",
            "powered_truck_only",
        ),
        (facts(hazard_type="ladder"), "1910.28(b)(1)", "fall_family"),
        (facts(hazard_type="overexertion"), "1910.212", "general_duty"),
        (facts(), "1926.501(b)(1)", "wrong_part"),
    ],
)
def test_each_rule_catches_its_error(intake: IntakeResult, primary: str, rule: str):
    assert rule in [i.rule for i in check_citation(intake, primary, naics="332")]


@pytest.mark.parametrize(
    ("intake", "primary", "secondary"),
    [
        (facts(activity="cleaning"), "1910.147", "1910.212(a)(1)"),
        (facts(material="wood", machine_or_hazard="table saw"), "1910.213", ""),
        (facts(machine_or_hazard="mechanical power press"), "1910.217", ""),
        (facts(hazard_type="powered_truck", machine_or_hazard="forklift"), "1910.178", ""),
        (facts(hazard_type="ladder"), "1910.23", ""),
        (facts(hazard_type="overexertion"), "OSH Act 5(a)(1)", ""),
    ],
)
def test_correct_citations_pass(intake: IntakeResult, primary: str, secondary: str):
    assert check_citation(intake, primary, secondary, naics="332") == []


def test_seeded_guarding_errors_on_jam_and_cleaning_cases_of_the_key_are_caught():
    """Seed the error from the proposal: 1910.212 where the key says lockout (1910.147)."""
    key = [c for c in load_answer_key() if c.primary_section == "1910.147"]
    caught = 0
    for case in key:
        intake = IntakeResult.model_validate(
            offline.intake({"report_id": case.case, "narrative": case.narrative, "event_title": case.event})
        )
        caught += any(
            i.rule == "energy_control" for i in check_citation(intake, "1910.212(a)(1)", naics="332")
        )
    assert len(key) == 11
    # The rule needs the narrative to name the servicing activity; most lockout cases do.
    assert caught >= 9


def test_a_fall_standard_needs_a_worker_who_fell_and_a_person_decides():
    hit = check_citation(
        facts(hazard_type="crane_load", machine_or_hazard="crane"), "1910.28(b)(1)", naics="331"
    )
    assert [i.rule for i in hit] == ["fall_only"] and hit[0].fix is False, (
        "flagged for a person, not corrected"
    )
    for hazard in ("fall_height", "ladder", "same_level", "other"):
        assert check_citation(facts(hazard_type=hazard), FALL_SECTIONS[hazard], naics="331") == [], hazard
    assert check_citation(facts(hazard_type="crane_load"), "1910.179(b)(1)", naics="331") == []


FALL_SECTIONS = {"fall_height": "1910.28(b)(1)", "ladder": "1910.23(b)(1)", "same_level": "1910.22(a)(1)",
                 "other": "1910.28"}  # fmt: skip
