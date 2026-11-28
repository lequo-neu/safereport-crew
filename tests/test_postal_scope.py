"""Issue #26: the warehousing program covers postal processing and distribution centers only.

NAICS 491110 (Postal Service) holds post offices as well as processing and distribution centers.
CPL 03-00-026 lists 491110 as "Postal Service (Processing & Distribution Centers only)" (Table 2),
excludes post offices that are not one (XII.B.3) and delivery to residences and businesses (XII.A).

The narratives are written for these tests, except the Crystal City report (20251111619), quoted
from docs/reviews/hamad.md as a regression case: it is a Texas week report, not in the B3 sample
or the 2025 holdout, and no count is measured on it. The tests run against the rule in
data/reference/emphasis_programs.toml, so a change to it is tested.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from safereport.retrieval import (
    RULE_FIELDS,
    Document,
    IndexRegistry,
    OshaFields,
    Retriever,
    reference_documents,
    with_current_rules,
)
from safereport.schemas import Report
from safereport.triage import category_one


WAREHOUSING = "CPL 03-00-026"
POSTAL = "491110"
USPS = OshaFields(employer="United States Postal Service")


@pytest.fixture(scope="module")
def warehousing() -> Document:
    return next(d for d in reference_documents("emphasis_program") if d.citation == WAREHOUSING)


@pytest.fixture(scope="module")
def before(warehousing: Document) -> Document:
    """The rule as it was before issue #26: every 491110 report with a trigger forced Category 1."""
    return replace(warehousing, scope_industries=[], scope_evidence=[], scope_exclusions=[], scope_label="")


@pytest.mark.parametrize(
    ("narrative", "employer"),
    [
        ("A walkie rider struck the back of an employee's ankle.", "U.S. Postal Service - Oakland P&DC"),
        ("An employee fell from a pallet mover to the floor.", "U.S. Postal Service - St. Paul Processing & Distribution Center"),
        ("An employee was struck by a powered industrial truck on the dock.", "USPS Denver NDC"),
        ("An employee fell from a trailer door to the ground.", "U. S. Postal Service - SFNDC, Richmond"),
        ("An employee tripped over a pallet jack at the mail distribution facility.", "U.S. Postal Service"),
        ("While operating a mail-processing machine, an employee's hand was caught.", "USPS"),
    ],
)  # fmt: skip
def test_a_processing_or_distribution_center_forces(warehousing: Document, narrative: str, employer: str):
    found = warehousing.match(narrative, POSTAL, OshaFields(employer=employer))
    assert found is not None and found.forces and found.route == "scope"
    assert found.evidence.startswith("postal processing and distribution center: ")


@pytest.mark.parametrize(
    "narrative",
    [
        "A letter carrier slipped on an icy driveway and fell, breaking her wrist.",
        "An employee was returning to her vehicle while delivering mail when she fell in a pothole.",
        "An employee was walking on his route when he tripped on a curb and fell.",
        "An employee reached into a mailbox and strained her shoulder lifting a package.",
        "A window clerk lifted a heavy box at the retail counter and strained his back.",
    ],
)
def test_delivery_or_a_retail_counter_is_outside_the_program(warehousing: Document, narrative: str):
    assert warehousing.match(narrative, POSTAL, USPS) is None


def test_delivery_is_outside_even_with_a_plant_in_the_employer_name(warehousing: Document):
    # The employer field names a P&DC, the narrative a delivery: the evidence conflicts, so the
    # program raises the priority and forces nothing.
    found = warehousing.match(
        "An employee was returning to her vehicle while delivering mail when she fell.",
        POSTAL,
        OshaFields(employer="U.S. Postal Service, Process Distribution Center"),
    )
    assert found is not None and not found.forces


def test_an_unknown_postal_facility_is_only_possible(warehousing: Document):
    found = warehousing.match("An employee slipped on a wet floor and fell, breaking a hip.", POSTAL, USPS)
    assert found is not None and not found.forces and found.route == "industry"


def test_crystal_city_is_no_longer_forced(warehousing: Document, before: Document):
    """20251111619 (Texas week): a ladder fall hanging a display, no facility named."""
    narrative = (
        "An employee was using a ladder to hang a display. While coming back down the ladder, she "
        "missed the last step and fell to the floor, fracturing her left knee."
    )
    assert before.match(narrative, POSTAL).forces
    found = warehousing.match(narrative, POSTAL, USPS)
    assert found is not None and not found.forces


def test_without_a_trigger_nothing_changes(warehousing: Document):
    assert (
        warehousing.match("An employee felt dizzy at a desk.", POSTAL, OshaFields("USPS Oakland P&DC"))
        is None
    )


@pytest.mark.parametrize(
    ("narrative", "naics"),
    [
        ("A forklift struck a worker in the aisle.", "493110"),
        ("A courier fell from the back of a delivery truck.", "492110"),
        ("A driver delivering packages slipped on a porch.", "492210"),
        ("A worker lifting boxes strained his back.", "493190"),
        ("A forklift struck a worker in the aisle.", "311612"),
    ],
)
def test_other_industries_keep_the_rule_as_before(
    warehousing: Document, before: Document, narrative: str, naics: str
):
    new, old = warehousing.match(narrative, naics, USPS), before.match(narrative, naics)
    assert new == old


def test_only_the_warehousing_program_is_narrowed_to_491110():
    narrowed = [d.citation for d in reference_documents("emphasis_program") if d.scope_industries]
    assert narrowed == [WAREHOUSING]


def test_search_splits_forced_and_possible_programs_and_category_one_shows_why(warehousing: Document):
    part = [Document("1", "1910", "1910.178", "1910.178", "Powered industrial trucks", "(a) General.")]
    registry = IndexRegistry({"1910": Retriever(part), "emphasis_program": Retriever([warehousing])})
    narrative = "An employee was struck by a forklift on the loading dock."

    plant = registry.search(narrative, naics=POSTAL, fields=OshaFields("U.S. Postal Service - Oakland P&DC"))
    assert plant.forced == [WAREHOUSING] and plant.possible == []
    evidence = plant.work_evidence()
    assert evidence[WAREHOUSING].startswith('postal processing and distribution center: "P&DC"')

    report = Report(id="1", event_date=date(2025, 3, 1), employer="U.S. Postal Service - Oakland P&DC",
                    state="CALIFORNIA", naics=POSTAL, hospitalized=1, amputation=0, loss_of_eye=0,
                    narrative=narrative, event_code="6", event_title="t", source_code="s", source_title="s")  # fmt: skip
    assert OshaFields.of(report).employer == report.employer
    trigger = category_one(report, plant.forced, [], emphasis_evidence=evidence)[0]
    assert trigger.evidence.startswith(f'{WAREHOUSING}: postal processing and distribution center: "P&DC"')

    unknown = registry.search(narrative, naics=POSTAL, fields=USPS)
    assert unknown.forced == [] and unknown.possible == [WAREHOUSING] and unknown.work_evidence() == {}
    # A pasted report has no employer field: the narrative alone decides.
    assert registry.search(narrative, naics=POSTAL).possible == [WAREHOUSING]


def test_an_unverified_program_never_forces(warehousing: Document):
    part = [Document("1", "1910", "1910.178", "1910.178", "Powered industrial trucks", "(a) General.")]
    unread = replace(warehousing, verified=False)
    registry = IndexRegistry({"1910": Retriever(part), "emphasis_program": Retriever([unread])})
    found = registry.search("A forklift struck a worker.", naics="493110")
    assert found.forced == [] and found.possible == [WAREHOUSING]


def test_a_loaded_index_takes_the_scope_from_the_reference_file(warehousing: Document, before: Document):
    stale = replace(before, text="as stored in an old index")
    refreshed = with_current_rules([stale])[0]
    assert {"scope_industries", "scope_evidence", "scope_exclusions", "scope_label"} <= set(RULE_FIELDS)
    assert all(getattr(refreshed, name) == getattr(warehousing, name) for name in RULE_FIELDS)
    assert refreshed.text == "as stored in an old index"


def test_the_evaluation_script_counts_each_change():
    import importlib.util
    from pathlib import Path

    import pandas as pd

    spec = importlib.util.spec_from_file_location(
        "eval_postal_scope", Path(__file__).parents[1] / "scripts" / "eval_postal_scope.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    old, new = module.rules()
    frame = pd.DataFrame(
        {
            "query": [
                "A forklift struck a worker on the dock.",
                "A letter carrier slipped on ice and fell.",
                "An employee slipped and fell on a wet floor.",
                "An employee felt dizzy at a desk.",
            ],
            "naics": [POSTAL] * 4,
            "employer": ["USPS Oakland P&DC", "USPS", "USPS", "USPS"],
        }
    )
    scored = module.score(frame, old, new)
    assert scored["before"].tolist() == ["forced", "forced", "forced", "none"]
    assert scored["after"].tolist() == ["forced", "none", "possible", "none"]
