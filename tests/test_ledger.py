from __future__ import annotations

import pytest

from safereport.ledger import FactLedger, percent


def test_facts_fill_placeholders_with_readable_values():
    ledger = FactLedger()
    ledger.add("reports", 8712, "store")
    ledger.add("change", percent(0.0446), "store")
    ledger.add("days", 1.0, "request")
    assert ledger.render("{{reports}} reports, {{change}} more") == "8,712 reports, 4.5% more"
    assert ledger.render("{{days}} inspector days") == "1.0 inspector days", "a small number is not a share"
    assert percent(1.5) == "150.0%"


def test_only_hand_written_numbers_are_untraced():
    ledger = FactLedger()
    text = "{{reports}} reports cite 1910.147(c)(4)(i) and CPL 03-00-027 under Category 1 of OIICS 3; 37 were inspected."
    assert ledger.untraced(text) == ["37"]


def test_unknown_facts_and_unequal_periods_are_found():
    ledger = FactLedger()
    ledger.add("full_year", 9034, "store", same_months=False)
    assert ledger.unknown("{{missing}} and {{full_year}}") == ["missing"]
    assert ledger.unequal_periods("{{full_year}}") == ["full_year"]
    with pytest.raises(KeyError):
        ledger.render("{{missing}}")


def test_fact_keys_are_plain_words():
    with pytest.raises(ValueError):
        FactLedger().add("Bad Key", 1, "x")
