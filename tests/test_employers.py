from __future__ import annotations

from datetime import date

import pytest

from safereport.data import REPORTS_PARQUET, ReportStore
from safereport.employers import EmployerIndex, initials, normalize_name


@pytest.fixture
def index(small_store: ReportStore) -> EmployerIndex:
    return EmployerIndex(small_store.frame("SELECT * FROM reports"))


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("Tyson Foods, Inc.", "tyson foods"),
        ("U.S. Postal Service", "us postal service"),
        ("United States Postal Service", "us postal service"),
        ("AMAZON.COM SERVICES LLC", "amazon com services"),
        ("Smith & Sons Co.", "smith and sons"),
    ],
)
def test_normalize_name(raw: str, normalized: str):
    assert normalize_name(raw) == normalized


def test_initials_keep_two_letter_words():
    assert initials("us postal service") == "usps"


def test_spellings_of_one_name_are_the_same_employer(index: EmployerIndex):
    found = {
        m.report_id: m
        for m in index.history("US Postal Service", "Texas", city="Dallas", naics="491110", exclude_id="3")
    }
    assert found["4"].status == "same" and found["4"].level == "company"
    # "USPS" is only an acronym of the name, so a person has to confirm it.
    assert found["5"].status == "possible" and found["5"].level == "site"


def test_away_from_the_site_the_industry_must_confirm_a_name(index: EmployerIndex):
    found = {
        m.report_id: m.status
        for m in index.history("US Postal Service", "Texas", city="Dallas", exclude_id="3")
    }
    assert found["4"] == "possible"


def test_near_spellings_are_only_possible(small_store: ReportStore):
    rows = small_store.frame("SELECT * FROM reports")
    rows.loc[rows["id"] == "2", "employer"] = "Basic Energy Services"
    rows.loc[rows["id"] == "1", "employer"] = "Bass Energy Services, LLC"
    index = EmployerIndex(rows)
    found = {m.report_id: m.status for m in index.history("Bass Energy Services", "Texas", zip_code="78701")}
    assert found["2"] == "possible" and found["1"] == "same"


def test_a_longer_name_is_only_a_possible_match(index: EmployerIndex):
    found = {m.report_id: m.status for m in index.history("Walmart", "TEXAS", zip_code="78701")}
    assert found == {"1": "same", "2": "possible"}


def test_matching_stays_within_the_state(index: EmployerIndex):
    assert {m.report_id for m in index.history("Walmart", "Ohio")} == {"9"}


def test_a_shared_word_alone_is_never_more_than_possible(index: EmployerIndex):
    # "Smith" and "Smith Construction" may be different firms, so a person decides.
    found = [(m.report_id, m.status) for m in index.history("Smith", "Ohio", exclude_id="8")]
    assert found == [("7", "possible")]
    assert index.repeats_within("Smith", "Ohio", date(2025, 12, 31), exclude_id="8") == []


def test_possible_matches_do_not_count_as_repeats_until_confirmed(index: EmployerIndex):
    on = date(2024, 12, 31)
    assert [m.report_id for m in index.repeats_within("Walmart", "Texas", on, zip_code="78701")] == ["1"]
    index.decide("Walmart", "Walmart Supercenter", same=True)
    assert [m.report_id for m in index.repeats_within("Walmart", "Texas", on, zip_code="78701")] == ["2", "1"]
    index.decide("Walmart", "Walmart Supercenter", same=False)
    assert [m.report_id for m in index.history("Walmart", "Texas")] == ["1"]


def test_repeats_look_back_only_one_year(index: EmployerIndex):
    assert index.repeats_within("US Postal Service", "Texas", date(2026, 3, 1), city="Dallas") == []


@pytest.mark.skipif(not REPORTS_PARQUET.exists(), reason="run `safereport build-data` first")
def test_real_postal_service_spellings_are_found_together():
    store = ReportStore()
    texas = store.frame("SELECT * FROM reports WHERE state = 'TEXAS'")
    index = EmployerIndex(texas)
    matches = index.history("U.S. Postal Service", "Texas", naics="491110")
    exact = (texas["employer"] == "U.S. Postal Service").sum()
    same = [m for m in matches if m.status == "same"]
    assert len(same) > exact, "spellings beyond the exact name must be found"
    assert {m.employer for m in same} >= {"U.S. Postal Service", "United States Postal Service"}


def test_pair_check_scores_only_labelled_pairs(tmp_path):
    from safereport.employer_check import FIELDS, score, write_pairs

    rows = [dict.fromkeys(FIELDS, "") | {"pair": f"P{n}", "rule": rule, "same_employer": label}
            for n, (rule, label) in enumerate([("same", "yes"), ("same", "no"), ("same", ""), ("possible", "yes")])]  # fmt: skip
    path = tmp_path / "pairs.csv"
    write_pairs(rows, path)
    result = score(path)
    assert result["labelled"] == 3
    assert result["same"] == {"labelled": 2, "really_same": 1, "share": 0.5}
    assert result["possible"]["share"] == 1.0


def test_a_decision_settles_every_report_of_the_pair_and_survives_a_restart(
    small_store: ReportStore, tmp_path
):
    from safereport.employers import DecisionStore

    rows = small_store.frame("SELECT * FROM reports")
    first = EmployerIndex(rows, store=DecisionStore(tmp_path / "decisions.sqlite"))
    first.decide("Walmart", "Walmart Supercenter", same=True, by="triage officer")
    again = EmployerIndex(rows, store=DecisionStore(tmp_path / "decisions.sqlite"))
    assert {m.report_id: m.status for m in again.history("Walmart", "Texas", zip_code="78701")} == {
        "1": "same",
        "2": "same",
    }
