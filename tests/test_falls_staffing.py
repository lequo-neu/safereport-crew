"""Issue #30: the Falls program for staffing agencies (NAICS 5613) whose worker did construction work.

The narratives are written for these tests; none comes from the B3 sample or the 2025 holdout.
They run against the rule in data/reference/emphasis_programs.toml, so a change to it is tested.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from safereport.retrieval import (
    RULE_FIELDS,
    Document,
    IndexRegistry,
    Retriever,
    reference_documents,
    with_current_rules,
)
from safereport.schemas import Report
from safereport.triage import category_one


FALLS = "CPL 03-00-025"
TEMP_HELP = "561320"


@pytest.fixture(scope="module")
def falls() -> Document:
    return next(d for d in reference_documents("emphasis_program") if d.citation == FALLS)


@pytest.fixture(scope="module")
def basic_falls(falls: Document) -> Document:
    """The rule as it was in the Basic stage: no work route."""
    return replace(falls, work_industries=[], work_evidence=[], work_exclusions=[], work_label="")


@pytest.mark.parametrize(
    "narrative",
    [
        (
            "A temporary employee was laying insulation in the attic of a building under construction "
            "when he fell 12 feet through the ceiling joists to the floor below."
        ),
        "A temporary laborer fell approximately 18 feet from a scaffold while installing brick on a new school.",
        "A temporary employee on a framing crew fell 14 feet from the second floor of a house.",
        "A temporary worker was stripping concrete forms on the second deck when she fell 9 feet to the slab.",
        "A temporary worker at a commercial construction site fell 14 ft. through an unguarded floor opening.",
        "An employee was hanging drywall from a baker scaffold and fell off the platform onto the slab.",
    ],
)
def test_staffing_worker_doing_construction_work_at_height_is_covered(falls: Document, narrative: str):
    found = falls.match(narrative, TEMP_HELP)
    assert found is not None and found.route == "work", narrative
    assert found.evidence.startswith(f"NAICS {TEMP_HELP} employer doing construction work: ")


@pytest.mark.parametrize(
    "narrative",
    [
        # An ordinary warehouse fall: no construction work named.
        "A temporary employee was picking orders and fell 6 feet from a rolling ladder in the warehouse.",
        "An employee fell off the loading dock to the ground while unloading a trailer.",
        # Staffing work that is not construction.
        "A temporary employee fell from the back of a garbage truck while collecting trash.",
        "A worker cleaning a production line slipped and fell 4 feet off a platform.",
        # A thing fell, not the worker.
        "During demolition of the interior, a section of ceiling fell from the second floor onto the worker.",
        # Construction words, but a fall on the same level.
        "A temporary laborer at the construction site tripped over rebar and fell, breaking her wrist.",
    ],
)
def test_staffing_reports_without_construction_work_at_height_are_not_covered(
    falls: Document, narrative: str
):
    assert falls.match(narrative, TEMP_HELP) is None, narrative


@pytest.mark.parametrize(
    "narrative",
    [
        # Ambiguous: painting, light fixtures and an unnamed job site are often maintenance.
        "A temporary employee was painting a hallway and fell from a 6-foot ladder.",
        "An employee fell 8 feet from a ladder while replacing a light fixture.",
        "A temporary employee fell from a ladder at the job site and broke his leg.",
        # Construction work, but no fall to a lower level is stated.
        "A temporary employee on a framing crew was injured and hospitalized.",
    ],
)
def test_ambiguous_staffing_reports_are_left_for_a_person(falls: Document, narrative: str):
    assert falls.match(narrative, TEMP_HELP) is None, narrative


def test_osha_coding_a_falling_object_vetoes_the_work_route(falls: Document):
    # The query the crew searches is the narrative plus OSHA's event title.
    narrative = (
        "While dismantling a scaffold, a temporary employee was hit when an aluminum plank fell 10 feet."
    )
    assert falls.match(narrative, TEMP_HELP) is not None
    assert falls.match(f"{narrative} Struck by falling object or equipment, n.e.c.", TEMP_HELP) is None


def test_the_work_route_is_only_for_staffing_codes(falls: Document):
    narrative = "A temporary laborer fell approximately 18 feet from a scaffold while installing brick."
    for naics in ("561311", "561320", "561330", "5613"):
        assert falls.match(narrative, naics) is not None, naics
    # A manufacturer, a warehouse, a janitorial firm (5617) and a report with no code are unchanged.
    for naics in ("332710", "493110", "561720", ""):
        assert falls.match(narrative, naics) is None, naics


def test_existing_falls_behaviour_is_unchanged(falls: Document, basic_falls: Document):
    cases = [
        ("He fell 12 feet from a ladder.", "236118"),  # construction: any fall from height
        ("She slipped on a doormat and fell.", "236118"),  # construction, but not from height
        (
            "An employee working on the roof fell 10 feet while repairing the HVAC unit.",
            "311612",
        ),  # listed activity
        (
            "An employee working on the roof fell 10 feet while repairing the HVAC unit.",
            TEMP_HELP,
        ),  # listed, anywhere
        ("An employee fell 10 feet from a scaffold.", "332710"),  # outside construction, not listed
        ("A temporary worker fell from a ladder in the warehouse.", TEMP_HELP),
        ("A beam fell from the third floor onto the worker.", "238120"),
    ]
    for text, naics in cases:
        assert falls.applies_to(text, naics) == basic_falls.applies_to(text, naics), (text, naics)
    assert falls.match("He fell 12 feet from a ladder.", "236118").route == "industry"
    assert (
        falls.match(
            "An employee working on the roof fell 10 feet while repairing the HVAC unit.", TEMP_HELP
        ).route
        == "anywhere"
    )


def test_other_programs_have_no_work_route():
    others = [d for d in reference_documents("emphasis_program") if d.citation != FALLS]
    assert others and all(not d.work_industries and not d.work_evidence for d in others)


def test_search_reports_the_evidence_and_category_one_shows_it(falls: Document):
    part = [
        Document("1", "1910", "1910.28", "1910.28", "Duty to have fall protection", "(b) Fall protection.")
    ]
    registry = IndexRegistry({"1910": Retriever(part), "emphasis_program": Retriever([falls])})
    narrative = "A temporary laborer fell approximately 18 feet from a scaffold while installing brick."
    found = registry.search(narrative, naics=TEMP_HELP)
    evidence = found.work_evidence()
    assert (
        list(evidence) == [FALLS]
        and '"scaffold"' in evidence[FALLS]
        and "fell approximately 18 feet" in evidence[FALLS]
    )

    report = Report(id="1", event_date=date(2024, 5, 1), employer="Temp Co", state="TEXAS", naics=TEMP_HELP,
                    hospitalized=1, amputation=0, loss_of_eye=0, narrative=narrative, event_code="4332",
                    event_title="t", source_code="s", source_title="s")  # fmt: skip
    triggers = category_one(report, [FALLS], [], emphasis_evidence=evidence)
    assert [t.criterion for t in triggers] == ["hazard under an emphasis program"]
    assert triggers[0].evidence.startswith(f"{FALLS}: NAICS {TEMP_HELP} employer doing construction work")
    # A construction company's fall keeps the citation alone, as before.
    built = registry.search("He fell 12 feet from a ladder.", naics="236118")
    assert built.work_evidence() == {}
    assert category_one(report, [FALLS], [], emphasis_evidence=built.work_evidence())[0].evidence == FALLS


def test_a_loaded_index_takes_the_rules_from_the_reference_file(falls: Document, basic_falls: Document):
    # An index built before issue #30 stored the Falls program without its work route.
    stale = replace(basic_falls, text="as stored in an old index")
    refreshed = with_current_rules([stale])[0]
    assert all(getattr(refreshed, name) == getattr(falls, name) for name in RULE_FIELDS)
    assert refreshed.text == "as stored in an old index"
