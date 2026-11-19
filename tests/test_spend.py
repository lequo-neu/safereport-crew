from __future__ import annotations

import pytest

from safereport.backends import OfflineBackend
from safereport.config import load_model_settings
from safereport.spend import BudgetExceededError, CachedBackend, SpendLedger, ceiling_price


SETTINGS = load_model_settings()


def backend(tmp_path, name="claude", budget=1.5):
    inner = OfflineBackend(name=name, handlers={"write": lambda p: {"template": "x" * 4000}})
    ledger = SpendLedger(tmp_path / "cache.sqlite")
    return CachedBackend(inner, SETTINGS.model(name), ledger, ceiling_price(SETTINGS), budget), inner, ledger


def test_a_repeated_call_is_answered_from_the_cache_for_free(tmp_path):
    guarded, inner, ledger = backend(tmp_path)
    first = guarded.complete("write", "same prompt")
    second = guarded.complete("write", "same prompt")
    assert not first.cached and second.cached and second.data == first.data
    assert len(inner.calls) == 1 and len(ledger.summary()) == 1 and ledger.summary()[0]["calls"] == 1


def test_the_cap_stops_new_paid_calls_but_not_cached_ones(tmp_path):
    guarded, _, ledger = backend(tmp_path, budget=0.005)
    guarded.complete("write", "a")  # about 1,000 output tokens at $10 per million: $0.01
    assert ledger.spent() > 0.005
    with pytest.raises(BudgetExceededError):
        guarded.complete("write", "b")
    assert guarded.complete("write", "a").cached


def test_an_unpriced_model_is_charged_at_the_ceiling(tmp_path):
    guarded, _, ledger = backend(tmp_path, name="gemini_flash")
    guarded.complete("write", "a")
    row = ledger.summary()[0]
    assert row["priced"] is False and row["cost"] > 0
    assert ceiling_price(SETTINGS) == (2.0, 10.0)


def test_exact_mcnemar_matches_the_binomial_tail():
    from safereport.live_eval import mcnemar_exact

    assert mcnemar_exact(0, 0) == 1.0
    assert round(mcnemar_exact(13, 3), 4) == 0.0213  # the GPT 5 nano strict at 3 run
    assert mcnemar_exact(5, 5) == 1.0


def test_an_unusable_reply_is_charged_but_not_cached(tmp_path):
    from safereport.backends import ModelError, Reply

    class Garbled:
        name = "claude"
        calls = 0

        def complete(self, step, prompt):
            self.calls += 1
            raise ModelError("bad_output", "claude", Reply("claude", "not json", None, 100, 1000, 0.1))

    inner = Garbled()
    ledger = SpendLedger(tmp_path / "cache.sqlite")
    guarded = CachedBackend(inner, SETTINGS.model("claude"), ledger, ceiling_price(SETTINGS))
    for _ in range(2):
        with pytest.raises(ModelError):
            guarded.complete("write", "a")
    assert inner.calls == 2 and ledger.summary()[0]["calls"] == 2 and ledger.spent() > 0
