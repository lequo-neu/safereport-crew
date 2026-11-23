"""The guide's employer history procedure on hand-made rows: no OSHA file needed."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    "category1_history_by_guide", Path(__file__).parents[1] / "scripts" / "category1_history_by_guide.py"
)
hist = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hist)

CASE = {"case": "K1", "sir_id": "9", "event_date": "6/1/2025", "employer": "US Postal Service",
        "city": "ROCHESTER", "naics": "491110"}  # fmt: skip


def earlier(id_, when, employer, city="DETROIT", naics="491110", event="4312"):
    return {
        "ID": id_,
        "EventDate": when,
        "Employer": employer,
        "City": city,
        "Primary NAICS": naics,
        "Event": event,
    }


def test_names_are_normalised_as_the_guide_says():
    assert hist.norm("Tyson Foods, Inc.") == "tyson foods"
    assert hist.norm("U.S. Postal Service") == hist.norm("US Postal Service") == "us postal service"
    assert hist.norm("R&L Carriers LLC") == "r and l carriers"
    assert hist.norm("Wal-Mart") == "walmart"


def test_possible_matches_say_why():
    assert hist.possible("wal mart", "walmart") == "same letters, different spacing"
    assert hist.possible("amazon", "amazon fulfillment center") == "one name inside the other"
    assert hist.possible("abc", "american building contractors") == "acronym"
    assert hist.possible("acme roofing", "zenith steel") == ""


def test_a_confirmed_similar_report_inside_the_year_is_yes():
    rows = [earlier("1", "12/23/2024", "U.S. Postal Service")]  # same 3-digit NAICS, another city
    result = hist.history(CASE, "4310", rows)
    assert result["label"] == "yes" and result["evidence"].startswith("1 12/23/2024")


def test_outside_the_year_another_hazard_or_the_report_itself_do_not_count():
    rows = [
        earlier("1", "5/31/2024", "US Postal Service"),  # 366 days before
        earlier("2", "1/5/2025", "US Postal Service", event="6213"),  # another event division
        earlier("9", "6/1/2025", "US Postal Service"),  # the report itself
    ]
    result = hist.history(CASE, "4310", rows)
    assert result["label"] == "no"
    assert [i["id"] for i in result["same_employer_other_hazard"]] == ["2"]


def test_only_a_possible_match_is_cannot_tell():
    rows = [earlier("1", "1/5/2025", "US Postal Service", city="DETROIT", naics="492110")]
    assert hist.history(CASE, "4310", rows)["label"] == "cannot_tell"
    rows = [earlier("1", "1/5/2025", "United States Postal Service Rochester")]
    assert hist.history(CASE, "4310", rows)["label"] == "no", (
        "a different spelling that is not near is not searched"
    )


def test_an_earlier_report_without_an_event_code_counts():
    rows = [earlier("1", "1/5/2025", "US Postal Service", event="")]
    assert hist.history(CASE, "4310", rows)["label"] == "yes"
