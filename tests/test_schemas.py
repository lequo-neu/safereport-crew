from __future__ import annotations

import csv
from datetime import date
from itertools import islice

from pydantic import ValidationError
import pytest

from safereport.config import PROJECT_ROOT
from safereport.schemas import GENERAL_DUTY, AnswerKeyCase, Citation, IntakeResult, Report, Span, cfr_section


SIR_CSV = PROJECT_ROOT / "data" / "raw" / "January2015toNovember2025.csv"

ROW = {
    "ID": "2022021032",
    "UPA": "1",
    "EventDate": "3/14/2022 0:00",
    "Employer": "Acme Laminates, Inc.",
    "Address1": "12 Mill Road",
    "Address2": "",
    "City": "DAYTON",
    "State": "OHIO",
    "Zip": "45402",
    "Primary NAICS": "326130",
    "Hospitalized": "0",
    "Amputation": "1.0",
    "Loss of Eye": "",
    "Inspection": "",
    "Final Narrative": "An employee's hand was pulled into the rollers   of a laminator during a cleaning cycle.",
    "Event": "6411",
    "EventTitle": "Caught in running equipment or machinery during maintenance, cleaning",
    "Source": "3500",
    "SourceTitle": "Special process machinery, n.e.c.",
    "NatureTitle": "Amputations",
    "Part of Body Title": "Fingertip(s)",
}


def test_report_maps_osha_columns():
    report = Report.from_csv_row(ROW)
    assert report.event_date == date(2022, 3, 14)
    assert report.amputation == 1 and report.loss_of_eye == 0
    assert report.narrative.count("  ") == 0
    assert report.is_manufacturing and not report.inspected
    assert report.address == "12 Mill Road"


@pytest.mark.skipif(not SIR_CSV.exists(), reason="the OSHA file is not downloaded (see data/raw/README.md)")
def test_report_parses_the_real_file():
    with SIR_CSV.open(newline="", encoding="utf-8", errors="replace") as handle:
        reports = [Report.from_csv_row(row) for row in islice(csv.DictReader(handle), 2000)]
    assert len(reports) == 2000
    assert all(r.narrative and r.state for r in reports)


@pytest.mark.parametrize("text", ["1910.212(a)(1)", "1910.147", "1926.501(b)(1)", "1910.212(a)(3)(ii)"])
def test_valid_citations(text: str):
    assert Citation(citation=text, source=text[:4]).citation == text


@pytest.mark.parametrize(
    "text", ["1910", "29 CFR 1910.212", "1910.212 (a)", "1904.39", "OSH Act", "1926.501"]
)
def test_invalid_citations_are_rejected(text: str):
    with pytest.raises(ValidationError):
        Citation(citation=text, source="1910")


def test_emphasis_programs_are_cited_by_directive():
    assert Citation(citation="CPL 03-00-027", source="emphasis_program").section == "CPL 03-00-027"
    with pytest.raises(ValidationError):
        Citation(citation="1910.212", source="emphasis_program")


def test_general_duty_clause_is_a_citation_of_its_own():
    assert Citation(citation=GENERAL_DUTY, source="general_duty").section == GENERAL_DUTY
    assert cfr_section("1910.212(a)(1)") == "1910.212"


def test_spans_that_run_past_the_narrative_are_found():
    narrative = "Hand caught in rollers while cleaning."
    result = IntakeResult(
        report_id="1",
        activity="cleaning",
        machine_or_hazard="rollers",
        injury="crush",
        event_code="6411",
        confidence=0.9,
        fatality_potential=False,
        spans=[Span(label="machine", start=15, end=22), Span(label="activity", start=29, end=80)],
    )
    assert result.spans[0].text_in(narrative) == "rollers"
    assert [s.label for s in result.spans_outside(narrative)] == ["activity"]


def test_a_span_must_end_after_it_starts():
    with pytest.raises(ValidationError):
        Span(label="x", start=5, end=5)


def test_answer_key_case_needs_a_reason_without_a_standard():
    base = {
        "case": "C99",
        "sir_id": "1",
        "narrative": "n",
        "event": "e",
        "source": "s",
        "primary_section": "",
        "accepted_sections": "",
        "confidence": "low",
        "labelers": "Kevin",
        "status": "single labeler",
    }
    with pytest.raises(ValidationError, match="needs a reason"):
        AnswerKeyCase.model_validate({**base, "primary_standard": "", "no_standard_reason": ""})
    ok = AnswerKeyCase.model_validate(
        {**base, "primary_standard": "", "no_standard_reason": "vague narrative"}
    )
    assert not ok.has_standard


def test_a_small_model_reply_is_read_as_meant():
    # Gemma 4 E4B in private mode: nulls, a number for the code, labels outside the lists.
    result = IntakeResult.model_validate(
        {"report_id": "1", "activity": "clearing a jam", "hazard_type": "rollers", "machine_or_hazard": "laminator",
         "material": None, "injury": "crush", "event_code": 6411, "source_code": None, "confidence": 1.4,
         "fatality_potential": None, "missing_facts": None}
    )  # fmt: skip
    assert (result.activity, result.hazard_type, result.event_code) == ("unknown", "other", "6411")
    assert (result.material, result.source_code, result.confidence) == ("", "", 1.0)
    assert result.fatality_potential is False and result.missing_facts == []
