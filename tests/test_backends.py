from __future__ import annotations

import pytest

from safereport.backends import ModelError, OfflineBackend, estimate_tokens


def test_scripted_handler_returns_structured_data():
    backend = OfflineBackend()
    backend.script("intake", lambda prompt: {"activity": "cleaning", "length": len(prompt)})
    reply = backend.complete("intake", "rollers during cleaning")
    assert reply.data == {"activity": "cleaning", "length": len("rollers during cleaning")}
    assert reply.model == "offline" and reply.seconds == 0.0
    assert reply.input_tokens == estimate_tokens("rollers during cleaning")


def test_same_prompt_gives_the_same_reply():
    backend = OfflineBackend()
    assert backend.complete("write", "brief").text == backend.complete("write", "brief").text


def test_unscripted_step_gets_a_fixed_reply():
    assert OfflineBackend().complete("planner", "hi").text == "Offline reply for the planner step."


def test_failures_are_raised_in_order_then_the_step_answers():
    backend = OfflineBackend(failures={"standards": ["rate_limit", "timeout"]})
    with pytest.raises(ModelError) as first:
        backend.complete("standards", "q")
    with pytest.raises(ModelError) as second:
        backend.complete("standards", "q")
    assert (first.value.kind, second.value.kind) == ("rate_limit", "timeout")
    assert backend.complete("standards", "q").text
    assert len(backend.calls) == 3


def test_token_estimate_never_returns_zero():
    assert estimate_tokens("") == 1
    assert estimate_tokens("x" * 400) == 100
