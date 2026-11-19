"""The week's list: which reports get an on site inspection and which get an RRI letter.

It follows OSHA's procedure (memo of 4 March 2016). A report meeting any Category 1 criterion
must be inspected. Every other report is Category 2, ranked by a priority built from OSHA's
Category 2 factors, and an integer program spends the inspector days left after Category 1 on
the reports that give the most priority. When Category 1 alone needs more days than the week
has, a relaxed model with a penalized slack says how many more days are needed instead of
failing. Nothing is final until the Area Director approves.

Assumptions, shown to the user and editable in config/triage.toml: the priority weights, the
inspector days an inspection takes, and the days of a week when a request names none.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib
from typing import Literal

import pulp

from safereport.config import PROJECT_ROOT
from safereport.schemas import IntakeResult, Report
from safereport.signals import mentions_failed_safeguard, mentions_minor_worker, mentions_temporary_worker


Decision = Literal["inspection", "rri_letter"]

TRIAGE_FILE = PROJECT_ROOT / "config" / "triage.toml"
BUILT_IN = {
    "default_capacity": 40.0,
    "weights": {
        "amputation": 3.0, "loss_of_eye": 3.0, "hospitalized": 2.0, "fatality_potential": 2.0,
        "failed_safeguard": 2.0, "temporary_worker": 1.5, "specific_standard": 1.0, "common_in_industry": 1.0,
        "possible_emphasis_program": 1.0,
    },
    "inspection_days": {"machine": 2.5, "fall_height": 2.0, "chemical": 3.0, "fire": 3.0, "crane_load": 2.5, "other": 1.5},
}  # fmt: skip


def load_assumptions(path: Path = TRIAGE_FILE) -> dict:
    """The weights, inspection days and default capacity from config/triage.toml (built in if absent)."""
    if not path.exists():
        return BUILT_IN
    with path.open("rb") as handle:
        loaded = tomllib.load(handle)
    return {
        "default_capacity": float(loaded.get("default_capacity", BUILT_IN["default_capacity"])),
        "weights": {**BUILT_IN["weights"], **loaded.get("weights", {})},
        "inspection_days": {**BUILT_IN["inspection_days"], **loaded.get("inspection_days", {})},
    }


ASSUMPTIONS = load_assumptions()
DEFAULT_WEIGHTS = ASSUMPTIONS["weights"]
INSPECTION_DAYS = {k: v for k, v in ASSUMPTIONS["inspection_days"].items() if k != "other"}
DEFAULT_DAYS = ASSUMPTIONS["inspection_days"]["other"]
DEFAULT_CAPACITY = ASSUMPTIONS["default_capacity"]


@dataclass
class Trigger:
    criterion: str
    evidence: str


@dataclass
class Case:
    """One report, with everything the list needs."""

    report_id: str
    employer: str
    days: float
    priority: float
    parts: dict[str, float]
    category_one: list[Trigger] = field(default_factory=list)

    @property
    def must_inspect(self) -> bool:
        return bool(self.category_one)


@dataclass
class Rules:
    """What the Area Director adds before approving: forced rows and employer wide rules."""

    force_inspection: set[str] = field(default_factory=set)
    force_letter: set[str] = field(default_factory=set)
    inspect_employers: set[str] = field(default_factory=set)
    notes: dict[str, str] = field(default_factory=dict)


@dataclass
class Plan:
    decisions: dict[str, Decision]
    reasons: dict[str, str]
    capacity: float
    days_used: float
    priority_covered: float
    shortfall_days: float = 0.0

    @property
    def feasible(self) -> bool:
        return self.shortfall_days == 0

    @property
    def inspections(self) -> list[str]:
        return [r for r, d in self.decisions.items() if d == "inspection"]


def category_one(
    report: Report,
    emphasis: list[str],
    repeats: list[str],
    user_minor: bool = False,
    imminent_danger: bool = False,
) -> list[Trigger]:
    """OSHA's Category 1 criteria that the report meets, each with its evidence."""
    triggers = []
    if report.hospitalized >= 2:
        triggers.append(Trigger("two or more hospitalized", f"{report.hospitalized} hospitalized"))
    if user_minor or mentions_minor_worker(report.narrative):
        triggers.append(Trigger("worker under 18", "age stated in the narrative or by the user"))
    if repeats:
        triggers.append(Trigger("similar report from the employer within 12 months", ", ".join(repeats)))
    for program in emphasis:
        triggers.append(Trigger("hazard under an emphasis program", program))
    if imminent_danger:
        triggers.append(Trigger("imminent danger", "set by the user"))
    return triggers


def priority(
    report: Report,
    intake: IntakeResult,
    has_specific_standard: bool,
    industry_share: float = 0.0,
    weights: dict[str, float] | None = None,
    possible_emphasis: bool = False,
) -> tuple[float, dict[str, float]]:
    """Category 2 priority from OSHA's factors; `industry_share` is how common the hazard is (0 to 1)."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    parts = {
        "amputation": w["amputation"] * (report.amputation > 0),
        "loss_of_eye": w["loss_of_eye"] * (report.loss_of_eye > 0),
        "hospitalized": w["hospitalized"] * min(report.hospitalized, 2),
        "fatality_potential": w["fatality_potential"] * intake.fatality_potential,
        "failed_safeguard": w["failed_safeguard"] * mentions_failed_safeguard(report.narrative),
        "temporary_worker": w["temporary_worker"] * mentions_temporary_worker(report.narrative),
        "specific_standard": w["specific_standard"] * has_specific_standard,
        "common_in_industry": w["common_in_industry"] * max(0.0, min(1.0, industry_share)),
        # An emphasis program whose scope we have not read from the directive: a factor, not a rule.
        "possible_emphasis_program": w["possible_emphasis_program"] * possible_emphasis,
    }
    parts = {k: float(v) for k, v in parts.items() if v}
    return round(sum(parts.values()), 3), parts


def inspection_days(intake: IntakeResult) -> float:
    return INSPECTION_DAYS.get(intake.hazard_type, DEFAULT_DAYS)


def plan_week(cases: list[Case], capacity: float, rules: Rules | None = None) -> Plan:
    """Assign every case an inspection or a letter within `capacity` inspector days."""
    rules = rules or Rules()
    problem = pulp.LpProblem("inspections", pulp.LpMaximize)
    pick = {c.report_id: pulp.LpVariable(f"x_{n}", cat="Binary") for n, c in enumerate(cases)}
    slack = pulp.LpVariable("missing_days", lowBound=0)
    penalty = sum(c.priority for c in cases) + 1.0
    problem += pulp.lpSum(c.priority * pick[c.report_id] for c in cases) - penalty * slack
    problem += pulp.lpSum(c.days * pick[c.report_id] for c in cases) <= capacity + slack
    forced = {}
    for case in cases:
        if case.must_inspect:
            forced[case.report_id] = "Category 1: " + "; ".join(t.criterion for t in case.category_one)
        elif case.report_id in rules.force_inspection:
            forced[case.report_id] = "set to inspection by the Area Director"
        elif case.employer.lower() in {e.lower() for e in rules.inspect_employers}:
            forced[case.report_id] = f"rule: inspect every report from {case.employer}"
        if case.report_id in forced:
            problem += pick[case.report_id] == 1
        elif case.report_id in rules.force_letter:
            problem += pick[case.report_id] == 0
    problem.solve(pulp.PULP_CBC_CMD(msg=False))

    decisions: dict[str, Decision] = {}
    reasons: dict[str, str] = {}
    for case in cases:
        chosen = (pick[case.report_id].value() or 0) > 0.5
        decisions[case.report_id] = "inspection" if chosen else "rri_letter"
        if case.report_id in forced:
            reasons[case.report_id] = forced[case.report_id]
        elif case.report_id in rules.force_letter:
            reasons[case.report_id] = "set to a letter by the Area Director"
        elif chosen:
            reasons[case.report_id] = f"Category 2, priority {case.priority:g} for {case.days:g} days"
        else:
            reasons[case.report_id] = (
                f"Category 2, priority {case.priority:g}: below the cut for the days left"
            )
        if case.report_id in rules.notes:
            reasons[case.report_id] += f" (note: {rules.notes[case.report_id]})"
    used = sum(c.days for c in cases if decisions[c.report_id] == "inspection")
    covered = sum(c.priority for c in cases if decisions[c.report_id] == "inspection")
    shortfall = round(max(0.0, slack.value() or 0.0), 3)
    return Plan(decisions, reasons, capacity, round(used, 3), round(covered, 3), shortfall)


def sensitivity(cases: list[Case], capacities: list[float], rules: Rules | None = None) -> list[dict]:
    """The plan's priority covered and inspections for each number of inspector days."""
    rows = []
    for capacity in capacities:
        plan = plan_week(cases, capacity, rules)
        rows.append(
            {
                "capacity": capacity,
                "inspections": len(plan.inspections),
                "priority_covered": plan.priority_covered,
                "shortfall_days": plan.shortfall_days,
            }
        )
    return rows
