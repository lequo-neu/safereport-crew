from __future__ import annotations

import re

import pytest

from safereport.data import REPORTS_PARQUET, ReportStore
from safereport.redaction import redact


def test_known_values_and_patterns_are_replaced_and_restored():
    text = (
        "An employee of Acme Laminates, Inc. at 12 Mill Road in Dayton was hurt. "
        "Acme said Mr. John Carter called 937-555-0142 and wrote to safety@acme.com."
    )
    result = redact(text, employer="Acme Laminates, Inc.", address="12 Mill Road", city="Dayton")
    for secret in ("Acme", "Mill Road", "Dayton", "John Carter", "555-0142", "safety@acme"):
        assert secret not in result.text
    assert "[EMPLOYER_1]" in result.text and "[PERSON_1]" in result.text and "[EMAIL_1]" in result.text
    assert result.restore(result.text) == text


def test_the_same_words_get_the_same_placeholder():
    result = redact(
        "Tyson called. TYSON FOODS replied. Tyson Foods agreed. Tyson paid.", employer="Tyson Foods, Inc."
    )
    assert result.text == "[EMPLOYER_1] called. [EMPLOYER_2] replied. [EMPLOYER_3] agreed. [EMPLOYER_1] paid."
    assert result.mapping["[EMPLOYER_3]"] == "Tyson Foods"


def test_single_words_keep_their_capital_so_common_words_survive():
    result = redact("A mobile crane tipped in Mobile.", city="MOBILE")
    assert result.text == "A mobile crane tipped in [CITY_1]."


def test_a_model_answer_is_restored_with_the_same_mapping():
    result = redact("A worker at Acme Laminates lost a fingertip.", employer="Acme Laminates LLC")
    answer = f"Send the RRI letter to {result.text.split()[3]} {result.text.split()[4]}"
    assert "Acme Laminates" in result.restore(answer)


def test_generic_first_words_are_not_redacted_alone():
    result = redact("The national team came. National Service Group paid.", employer="National Service Group")
    assert result.text.startswith("The national team came.")


@pytest.mark.parametrize(
    ("text", "kwargs", "expected"),
    [
        ("The worker at 3M in zip 45402 was hurt.", {"employer": "3M", "zip_code": "45402"}, "The worker at [EMPLOYER_1] in zip [ZIP_1] was hurt."),
        ("Dr. José Núñez treated him; MR. SMITH drove.", {}, "[PERSON_1] treated him; [PERSON_2] drove."),
        ("Employee Maria Lopez fell. An employee fell.", {}, "Employee [PERSON_1] fell. An employee fell."),
        ("At Skills Center, Building 1260.", {"address": "Skills Center", "address2": "Building 1260"}, "At [ADDRESS_1], [ADDRESS_2]."),
    ],
)  # fmt: skip
def test_review_cases_are_redacted_and_restored(text: str, kwargs: dict, expected: str):
    result = redact(text, **kwargs)
    assert result.text == expected
    assert result.restore(result.text) == text


def test_bare_names_are_found_through_the_word_list(monkeypatch: pytest.MonkeyPatch):
    from safereport import redaction

    monkeypatch.setattr(
        redaction, "common_words", lambda: frozenset({"fell", "from", "a", "ladder", "the", "employee"})
    )
    result = redact("Maria Lopez fell from a ladder. The Employee fell.")
    assert result.text == "[NAME_1] fell from a ladder. The Employee fell."
    assert result.restore(result.text) == "Maria Lopez fell from a ladder. The Employee fell."


def test_a_one_word_name_without_a_title_is_a_known_gap():
    assert redact("Lopez fell.").text == "Lopez fell."


def test_text_with_a_placeholder_already_is_refused():
    with pytest.raises(ValueError, match="placeholder"):
        redact("Report from [EMPLOYER_1].")


def test_nothing_to_redact_leaves_the_text_alone():
    result = redact("An employee fell from a ladder.")
    assert result.text == "An employee fell from a ladder." and result.mapping == {}


@pytest.mark.skipif(not REPORTS_PARQUET.exists(), reason="run `safereport build-data` first")
def test_real_narratives_that_name_their_employer_round_trip():
    store = ReportStore()
    rows = store.frame(
        "SELECT narrative, employer, address1, address2, city FROM reports "
        "WHERE length(employer) > 4 AND contains(lower(narrative), lower(split_part(employer, ',', 1)))"
    )
    assert len(rows) > 100
    for row in rows.itertuples():
        result = redact(
            row.narrative, employer=row.employer, address=row.address1, address2=row.address2, city=row.city
        )
        assert result.restore(result.text) == row.narrative
        name = row.employer.split(",")[0]
        # Whole words written as a name: "Blind, Inc" must go, while the common words "blinds",
        # "steel" or "strike" in lower case may stay.
        for match in re.finditer(rf"(?<!\w){re.escape(name)}(?!\w)", result.text, flags=re.IGNORECASE):
            assert not match.group(0)[0].isupper(), f"{row.employer!r} left in: {result.text}"


def test_words_to_keep_stay_visible():
    """A state name looks like a name pair to the pattern; the Planner needs it, so it is kept."""
    assert (
        redact("Plan inspections in Puerto Rico.", keep=("Puerto Rico",)).text
        == "Plan inspections in Puerto Rico."
    )
