"""The live adapters with fake SDK clients: no network, no key, no cost."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from safereport.backends import ModelError
from safereport.config import load_model_settings
from safereport.providers import (
    AnthropicBackend,
    GoogleBackend,
    OpenAIBackend,
    evidence_to_spans,
    live_backends,
    parse_json,
    prepare,
)


SETTINGS = load_model_settings()
NARRATIVE = "An employee's hand was pulled into the rollers while clearing a jam."
INTAKE = json.dumps(
    {"report_id": "1", "narrative": NARRATIVE, "baseline_code": "6411", "baseline_confidence": 0.8}
)
INTAKE_REPLY = {
    "report_id": "1", "activity": "unjamming", "hazard_type": "machine", "machine_or_hazard": "rollers",
    "material": "", "injury": "crush", "event_code": "6411", "source_code": "", "confidence": 0.8,
    "fatality_potential": False, "missing_facts": ["Was the machine locked out?"],
    "evidence": [{"label": "activity", "text": "clearing a jam"}, {"label": "made up", "text": "not in the text"}],
}  # fmt: skip


class FakeAnthropic:
    def __init__(self, text="", error=None, stop="end_turn"):
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))
        self.text, self.error, self.stop = text, error, stop

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(
            stop_reason=self.stop,
            content=[
                SimpleNamespace(type="thinking", thinking=""),
                SimpleNamespace(type="text", text=self.text),
            ],
            usage=SimpleNamespace(input_tokens=120, output_tokens=40),
        )


def test_claude_intake_reply_becomes_spans_from_quoted_evidence():
    fake = FakeAnthropic(text="```json\n" + json.dumps(INTAKE_REPLY) + "\n```")
    reply = AnthropicBackend(SETTINGS.model("claude"), client=fake).complete("intake", INTAKE)
    assert reply.data["spans"] == [
        {"label": "activity", "start": NARRATIVE.find("clearing"), "end": NARRATIVE.find("clearing") + 14}
    ]
    assert (reply.input_tokens, reply.output_tokens) == (120, 40)
    sent = fake.calls[0]
    assert sent["model"] == "claude-sonnet-5-5" and sent["fallbacks"] == "default"
    assert sent["betas"] == ["server-side-fallback-2026-07-01"] and "OSHA" in sent["system"]


def test_claude_errors_become_fallback_signals():
    import anthropic
    import httpx2

    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    limited = anthropic.RateLimitError("slow down", response=httpx2.Response(429, request=request), body=None)
    with pytest.raises(ModelError) as caught:
        AnthropicBackend(SETTINGS.model("claude"), client=FakeAnthropic(error=limited)).complete(
            "intake", INTAKE
        )
    assert caught.value.kind == "rate_limit"
    with pytest.raises(ModelError) as caught:
        AnthropicBackend(SETTINGS.model("claude"), client=FakeAnthropic(text="{}", stop="refusal")).complete(
            "intake", INTAKE
        )
    assert caught.value.kind == "refusal"


def test_a_reply_that_is_not_json_is_bad_output():
    with pytest.raises(ModelError) as caught:
        AnthropicBackend(
            SETTINGS.model("claude"), client=FakeAnthropic(text="Sorry, no JSON here.")
        ).complete("intake", INTAKE)
    assert caught.value.kind == "bad_output"


def test_openai_and_lm_studio_use_json_mode():
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        message = SimpleNamespace(content=json.dumps({"terms": ["powered industrial truck"]}))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)],
                               usage=SimpleNamespace(prompt_tokens=50, completion_tokens=10))  # fmt: skip

    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    reply = OpenAIBackend(SETTINGS.model("gpt_nano"), client=fake).complete(
        "standards_terms", json.dumps({"narrative": "forklift"})
    )
    assert reply.data == {"terms": ["powered industrial truck"]}
    assert calls[0]["response_format"] == {"type": "json_object"} and calls[0]["model"] == "gpt-5-nano"


def test_gemini_reads_usage_metadata():
    def generate_content(**kwargs):
        return SimpleNamespace(text=json.dumps({"terms": ["ladder"]}),
                               usage_metadata=SimpleNamespace(prompt_token_count=30, candidates_token_count=5))  # fmt: skip

    fake = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    reply = GoogleBackend(SETTINGS.model("gemini_flash"), client=fake).complete(
        "standards_terms", json.dumps({"narrative": "x"})
    )
    assert reply.data == {"terms": ["ladder"]} and reply.input_tokens == 30


def test_the_writer_polishes_the_rule_based_draft():
    sent = json.loads(prepare("writer", json.dumps({"kind": "repeat_answer"})))
    assert "{{repeat_employers}}" in sent["base_template"]


def test_helpers():
    assert parse_json('Here you go: {"a": 1} thanks') == {"a": 1}
    assert parse_json('{"a": {"b": 2}}') == {"a": {"b": 2}}
    # Claude Sonnet 5.5 on case C32: an answer, a correction, then the final answer.
    assert parse_json('{"terms": ["a", "b"]}\n\nCorrection: fewer. Final answer:\n\n{"terms": ["a"]}') == {
        "terms": ["a"]
    }
    with pytest.raises(ValueError):
        parse_json("no object here")
    assert evidence_to_spans({"evidence": [{"label": "x", "text": "jam"}]}, "a jam") == {
        "spans": [{"label": "x", "start": 2, "end": 5}]
    }


def test_only_models_with_keys_get_a_live_backend(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("safereport.providers.lm_studio_running", lambda url="": False)
    assert live_backends(SETTINGS, environ={}) == {}
    found = live_backends(SETTINGS, environ={"OPENAI_API_KEY": "test-key"})
    assert list(found) == ["gpt_nano"] and isinstance(found["gpt_nano"], OpenAIBackend)
