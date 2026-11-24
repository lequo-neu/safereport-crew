"""OSHA domain checks: does the cited standard fit the facts of the injury?

A citation can exist in eCFR and still be wrong for the case: a jam cleared on a running machine
points to lockout (1910.147), not only to guarding (1910.212); 1910.213 covers woodworking
machines, so a band saw cutting fish is a general guarding case. These rules come from our
labelling guide (docs/LABELING_GUIDE.md), and the critic applies them to every draft.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from safereport.schemas import GENERAL_DUTY, IntakeResult, cfr_section


SERVICING = {"cleaning", "unjamming", "servicing", "setup"}
WOOD = re.compile(r"\b(wood|lumber|timber|plywood|board|log|pallet wood)\b", re.IGNORECASE)
MECHANICAL_PRESS = re.compile(
    r"\b(mechanical (power )?press|punch press|stamping press|power press)\b", re.IGNORECASE
)
NO_SPECIFIC_STANDARD = {"overexertion", "violence", "bite", "heat"}
FALL_SECTION = {"ladder": "1910.23", "fall_height": "1910.28", "same_level": "1910.22"}
# Walking working surfaces and fall protection: they fit only an injury where the worker fell.
FALL_PROTECTION = {"1910.22", "1910.23", "1910.28", "1910.29", "1910.140"}
NOT_READ = {"other", "unknown", ""}


@dataclass
class DomainIssue:
    rule: str
    message: str
    suggestion: str
    # False for a rule that a person checks: the critic shows it but does not change the citation.
    fix: bool = True


def _section(citation: str) -> str:
    return GENERAL_DUTY if citation.strip() == GENERAL_DUTY else cfr_section(citation)


def check_citation(
    facts: IntakeResult, primary: str, secondary: str = "", naics: str = "", part_1926_available: bool = False
) -> list[DomainIssue]:
    """Every rule the cited standards break, given what the Intake agent read."""
    cited = {_section(c) for c in (primary, secondary) if c}
    first = _section(primary) if primary else ""
    issues: list[DomainIssue] = []

    if facts.activity in SERVICING and facts.hazard_type == "machine" and "1910.147" not in cited:
        issues.append(
            DomainIssue(
                "energy_control",
                f"the worker was {facts.activity} a machine, which points to control of hazardous energy",
                "cite 1910.147 as primary, with the guarding standard as secondary",
            )
        )
    if "1910.213" in cited and not WOOD.search(f"{facts.material} {facts.machine_or_hazard}"):
        issues.append(
            DomainIssue(
                "woodworking_only",
                f"1910.213 covers woodworking machines, but the material is {facts.material or 'not wood'}",
                "cite 1910.212 (general machine guarding)",
            )
        )
    if "1910.217" in cited and not MECHANICAL_PRESS.search(facts.machine_or_hazard):
        issues.append(
            DomainIssue(
                "mechanical_press_only",
                "1910.217 covers mechanical power presses, and the narrative does not say the press is one",
                "cite 1910.212(a)(3)(ii) as primary and 1910.217 as secondary",
            )
        )
    if "1910.178" in cited and facts.hazard_type != "powered_truck":
        issues.append(
            DomainIssue(
                "powered_truck_only",
                f"1910.178 covers powered industrial trucks, but the vehicle is {facts.machine_or_hazard or 'another kind'}",
                f"a front end loader or a road truck has no Part 1910 truck standard; cite {GENERAL_DUTY}",
            )
        )
    expected = FALL_SECTION.get(facts.hazard_type)
    if expected and first in FALL_SECTION.values() and first != expected:
        issues.append(
            DomainIssue(
                "fall_family",
                f"a {facts.hazard_type.replace('_', ' ')} fall is {expected}, not {first}",
                f"cite {expected}",
            )
        )
    if (
        first in FALL_PROTECTION
        and facts.hazard_type not in FALL_SECTION
        and facts.hazard_type not in NOT_READ
    ):
        # "Scale fell 7 feet off the caster onto his foot" is a struck by injury: the worker did not fall.
        issues.append(
            DomainIssue(
                "fall_only",
                f"{first} is about falls, but the worker was hurt by {facts.hazard_type.replace('_', ' ')}",
                "cite the standard for what hurt the worker",
                # Measured once on the answer key: 2 of the 10 fall cases were flagged, because the offline
                # Intake reads "heel caught on a cart" as a machine. So a person decides, not the critic.
                fix=False,
            )
        )
    if any(c.startswith("1926.") for c in cited) and not naics.startswith("23"):
        issues.append(
            DomainIssue("wrong_part", "Part 1926 is for construction only", "cite the Part 1910 standard")
        )
    if part_1926_available and naics.startswith("23") and any(c.startswith("1910.") for c in cited):
        issues.append(
            DomainIssue("wrong_part", "a construction report is covered by Part 1926", "cite Part 1926")
        )
    if facts.hazard_type in NO_SPECIFIC_STANDARD and first.startswith("19"):
        issues.append(
            DomainIssue(
                "general_duty",
                f"no Part 1910 standard covers {facts.hazard_type}; OSHA uses the General Duty Clause",
                f"cite {GENERAL_DUTY}",
            )
        )
    return issues
