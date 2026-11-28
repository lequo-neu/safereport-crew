"""Issue #27: the trenching and excavation program, read from CPL 02-00-161 (2018).

The directive applies OSHA-wide to trenching and excavation operations (II), with no NAICS list,
and assigns inspections for incidents (IX.A). A report forces an inspection when OSHA coded the
event as a trench or excavation collapse (OIICS 3 event 632, OIICS 2 event 651), or the narrative
puts the worker in a trench or excavation or describes one collapsing. Source 611 (ditches,
channels, trenches, excavations) and a bare mention only raise the priority; a trench drain does
not bring the program in.

The narratives are written for these tests, except 20251111409 (Everflow Plumbing, Arlington),
quoted from docs/reviews/hamad.md as a regression case: it is a Texas week report, not in the B3
sample or the 2025 holdout, and no count is measured on it. The tests run against the rule in
data/reference/emphasis_programs.toml, so a change to it is tested.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
import importlib.util
from pathlib import Path

import pandas as pd
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


TRENCHING = "CPL 02-00-161"
PLUMBING = "238220"
NO_CODES = OshaFields(employer="Acme Utilities")


@pytest.fixture(scope="module")
def trenching() -> Document:
    return next(d for d in reference_documents("emphasis_program") if d.citation == TRENCHING)


def test_the_scope_was_read_from_the_directive(trenching: Document):
    assert trenching.verified and trenching.industries == []
    assert trenching.scope_event_codes == ["3:632", "2:651"] and trenching.source_codes == ["611"]


def test_20251111409_is_forced_by_osha_event_code():
    """Texas week: dirt and rock fell from the wall of an underground tunnel onto a worker's legs.

    The narrative never says trench or excavation; OSHA coded the event 632 and the source 611.
    """
    trenching = next(d for d in reference_documents("emphasis_program") if d.citation == TRENCHING)
    narrative = (
        "An employee was using a hammer to break away old existing sewer pipe from underneath a "
        "building. A section of dirt/rock fell from the side of the underground tunnel wall onto "
        "the employee's legs. The employee sustained two broken legs."
    )
    fields = OshaFields(
        employer="Everflow Plumbing, Heating & Air", event_code="632", source_code="611", oiics_version=3
    )
    found = trenching.match(narrative, PLUMBING, fields)
    assert found is not None and found.forces and found.route == "scope"
    assert found.evidence == "trenching or excavation operation: OSHA event code 632 (OIICS 3)"


@pytest.mark.parametrize(
    ("event_code", "version", "forces"),
    [("632", 3, True), ("651", 2, True), ("651", 3, False), ("632", 2, False), ("", None, False)],
)
def test_the_event_code_is_read_with_its_oiics_version(trenching: Document, event_code, version, forces):
    found = trenching.match("An employee was hurt.", PLUMBING, OshaFields("X", event_code, "", version))
    assert (found is not None and found.forces) == forces


@pytest.mark.parametrize(
    "narrative",
    [
        "An employee was working in a 6-foot-deep trench when a section of pipe rolled and struck him.",
        "An employee fell into an excavation that was 7 feet deep.",
        "An employee was climbing a ladder out of the trench when the walls caved in.",
        "The trench collapsed on two employees who were laying conduit.",
        "The side of the excavation suddenly gave way, burying his legs.",
        "The wall of the 10-foot trench collapsed onto the worker.",
        "An employee was standing at the edge of a benched trench when the soil moved.",
    ],
)
def test_a_worker_in_a_trench_or_a_collapse_forces(trenching: Document, narrative: str):
    found = trenching.match(narrative, PLUMBING, NO_CODES)
    assert found is not None and found.forces and found.route == "scope"


@pytest.mark.parametrize(
    "narrative",
    [
        "Hot water backed up from the trench drain and burned an employee's feet.",
        "An employee stepped on a trench grate and his leg went through.",
        "An employee slipped near the floor trench in the wash bay.",
        "An excavator bucket struck an employee walking behind the machine.",
        "A trencher ran over the employee's foot.",
        "An employee was struck by a forklift in the warehouse.",
    ],
)
def test_unrelated_contexts_do_not_bring_the_program_in(trenching: Document, narrative: str):
    assert trenching.match(narrative, PLUMBING, NO_CODES) is None


@pytest.mark.parametrize(
    ("narrative", "fields"),
    [
        ("An employee was assembling trench boxes in the yard when a chain slipped.", NO_CODES),
        ("An employee was washing out a hydro excavation truck when his finger was caught.", NO_CODES),
        ("An employee was walking to deliver mail and fell into a grass-covered ditch.",
         OshaFields("United States Postal Service", "4140", "611", 3)),
        ("The crew was excavating for a footing when a worker tripped over a hose.", NO_CODES),
    ],
)  # fmt: skip
def test_ambiguous_evidence_only_raises_the_priority(trenching: Document, narrative: str, fields: OshaFields):
    found = trenching.match(narrative, "561730", fields)
    assert found is not None and not found.forces


def test_the_rule_applies_in_any_industry(trenching: Document):
    for naics in ("237110", "221310", "311999", "491110", ""):
        found = trenching.match("The trench collapsed on the worker.", naics, NO_CODES)
        assert found is not None and found.forces, naics


def test_a_pasted_report_is_read_from_its_narrative(trenching: Document):
    assert trenching.match("The trench collapsed on the worker.", PLUMBING).forces
    assert trenching.match("A worker was hurt near a ditch.", PLUMBING) is None


def test_oshafields_of_a_report_reads_the_codes_and_their_version():
    def report(year: int) -> Report:
        return Report(id="1", event_date=date(year, 5, 1), employer="Acme", state="TEXAS", naics=PLUMBING,
                      hospitalized=1, amputation=0, loss_of_eye=0, narrative="n", event_code=" 632 ",
                      event_title="t", source_code=" 611", source_title="s")  # fmt: skip

    assert OshaFields.of(report(2025)) == OshaFields("Acme", "632", "611", 3)
    assert OshaFields.of(report(2023)).oiics_version == 2


def test_search_forces_the_program_and_category_one_shows_the_code(trenching: Document):
    part = [
        Document("1", "1926", "1926.651", "1926.651", "Specific excavation requirements", "(k) Inspections.")
    ]
    registry = IndexRegistry({"1910": Retriever(part), "emphasis_program": Retriever([trenching])})
    fields = OshaFields("Everflow Plumbing", "632", "611", 3)
    found = registry.search("Dirt fell from the tunnel wall onto his legs.", naics=PLUMBING, fields=fields)
    assert found.forced == [TRENCHING] and found.possible == []
    report = Report(id="20251111409", event_date=date(2025, 11, 17), employer="Everflow Plumbing", state="TEXAS",
                    naics=PLUMBING, hospitalized=1, amputation=0, loss_of_eye=0, narrative="n", event_code="632",
                    event_title="t", source_code="611", source_title="s")  # fmt: skip
    trigger = category_one(report, found.forced, [], emphasis_evidence=found.work_evidence())[0]
    assert (
        trigger.evidence == f"{TRENCHING}: trenching or excavation operation: OSHA event code 632 (OIICS 3)"
    )
    drain = registry.search("Water from the trench drain burned his feet.", naics=PLUMBING, fields=NO_CODES)
    assert drain.emphasis == []


def test_a_loaded_index_takes_the_codes_from_the_reference_file(trenching: Document):
    stale = replace(trenching, verified=False, scope_event_codes=[], source_codes=[], text="old index")
    refreshed = with_current_rules([stale])[0]
    assert {"scope_event_codes", "source_codes"} <= set(RULE_FIELDS)
    assert all(getattr(refreshed, name) == getattr(trenching, name) for name in RULE_FIELDS)


def test_the_evaluation_script_counts_each_change():
    spec = importlib.util.spec_from_file_location(
        "eval_trenching_scope", Path(__file__).parents[1] / "scripts" / "eval_trenching_scope.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    old, new = module.rules()
    frame = pd.DataFrame(
        {
            "query": [
                "Dirt fell from the tunnel wall onto his legs.",
                "An employee was working in a trench when a pipe struck him.",
                "He fell into a ditch.",
                "An excavator struck a worker.",
                "A worker tripped in the office.",
            ],
            "naics": ["238220", "237110", "491110", "237310", "541110"],
            "employer": ["A", "B", "C", "D", "E"],
            "event_code": ["632", "6", "4140", "6", "4"],
            "source_code": ["611", "1", "611", "3", "1"],
            "oiics_version": [3, 3, 3, 3, 2],
        }
    )
    scored = module.score(frame, old, new)
    # Before issue #27 the program was unverified (never forced) and matched "excavator".
    assert scored["before"].tolist() == ["none", "possible", "none", "possible", "none"]
    assert scored["after"].tolist() == ["forced", "forced", "possible", "none", "none"]
