from __future__ import annotations

from datetime import date

from safereport.schemas import IntakeResult, Report
from safereport.triage import Case, Rules, Trigger, category_one, plan_week, priority, sensitivity


def report(**fields) -> Report:
    base = {"id": "1", "event_date": date(2025, 5, 1), "employer": "Acme", "state": "TEXAS", "naics": "332710",
            "hospitalized": 1, "amputation": 0, "loss_of_eye": 0, "narrative": "An employee was hurt.",
            "event_code": "6411", "event_title": "t", "source_code": "s", "source_title": "s"}  # fmt: skip
    return Report(**{**base, **fields})


def intake(**fields) -> IntakeResult:
    base = {"report_id": "1", "activity": "normal operation", "machine_or_hazard": "", "injury": "x", "event_code": "6411",
            "confidence": 0.9, "fatality_potential": False}  # fmt: skip
    return IntakeResult(**{**base, **fields})


def test_category_one_criteria_come_with_evidence():
    triggers = category_one(report(hospitalized=2), emphasis=["CPL 03-00-027"], repeats=["2025012345"])
    assert [t.criterion for t in triggers] == [
        "two or more hospitalized",
        "similar report from the employer within 12 months",
        "hazard under an emphasis program",
    ]
    assert triggers[1].evidence == "2025012345"
    assert category_one(report(), [], []) == []


def test_priority_adds_the_category_two_factors():
    narrative = "A temporary employee's hand was caught in an unguarded pulley and amputated."
    score, parts = priority(
        report(amputation=1, narrative=narrative), intake(fatality_potential=True), True, 0.5
    )
    assert set(parts) == {"amputation", "hospitalized", "fatality_potential", "failed_safeguard", "temporary_worker",
                          "specific_standard", "common_in_industry"}  # fmt: skip
    assert score == 3 + 2 + 2 + 2 + 1.5 + 1 + 0.5


def cases() -> list[Case]:
    return [
        Case("a", "Acme", 2.0, 9.0, {}, [Trigger("two or more hospitalized", "2")]),
        Case("b", "Beta", 2.0, 6.0, {}),
        Case("c", "Gamma", 2.0, 5.0, {}),
        Case("d", "Delta", 1.0, 1.0, {}),
    ]


def test_category_one_is_inspected_and_the_rest_fill_the_days():
    plan = plan_week(cases(), capacity=5.0)
    assert plan.feasible and plan.days_used <= 5.0
    assert plan.decisions == {"a": "inspection", "b": "inspection", "c": "rri_letter", "d": "inspection"}
    assert plan.reasons["a"].startswith("Category 1")


def test_area_director_rules_are_respected():
    rules = Rules(force_inspection={"c"}, force_letter={"b"}, notes={"c": "second report this month"})
    plan = plan_week(cases(), capacity=5.0, rules=rules)
    assert plan.decisions["c"] == "inspection" and plan.decisions["b"] == "rri_letter"
    assert "second report this month" in plan.reasons["c"]
    employer_rule = plan_week(cases(), capacity=10.0, rules=Rules(inspect_employers={"delta"}))
    assert "rule: inspect every report from Delta" in employer_rule.reasons["d"]


def test_too_few_days_for_category_one_reports_how_many_are_missing():
    two = [
        Case("a", "A", 3.0, 5.0, {}, [Trigger("x", "y")]),
        Case("b", "B", 2.5, 5.0, {}, [Trigger("x", "y")]),
    ]
    plan = plan_week(two, capacity=4.0)
    assert not plan.feasible and plan.shortfall_days == 1.5
    assert plan.inspections == ["a", "b"]


def test_more_days_never_cover_less_priority():
    rows = sensitivity(cases(), [1, 3, 5, 7, 9])
    covered = [r["priority_covered"] for r in rows]
    assert covered == sorted(covered) and rows[0]["shortfall_days"] == 1.0 and rows[-1]["shortfall_days"] == 0
