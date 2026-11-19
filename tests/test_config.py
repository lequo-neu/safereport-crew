from __future__ import annotations

from pathlib import Path
import tomllib

from pydantic import ValidationError
import pytest

from safereport.config import MODELS_FILE, ModelSettings, load_model_settings


@pytest.fixture
def raw() -> dict:
    with MODELS_FILE.open("rb") as handle:
        return tomllib.load(handle)


def test_config_has_four_models_from_four_providers():
    settings = load_model_settings()
    assert len(settings.models) == 4
    assert {m.provider for m in settings.models} == {"anthropic", "openai", "google", "local"}
    hosted = [m for m in settings.models if not m.is_local]
    assert len(hosted) >= 3, "the course asks for at least three LLMs"


def test_every_model_records_when_its_id_was_checked():
    for spec in load_model_settings().models:
        assert spec.model_id and spec.checked_on


def test_fallback_chain_ends_on_the_local_model():
    settings = load_model_settings()
    assert settings.router.fallback_order[-1] == "gemma_local"
    assert [m.name for m in settings.fallback_after("claude")] == ["gemini_flash", "gpt_nano", "gemma_local"]
    assert settings.fallback_after("gemma_local") == []


def test_cost_uses_the_configured_price_or_says_unknown():
    settings = load_model_settings()
    assert settings.model("claude").cost(1_000_000, 100_000) == pytest.approx(3.0)
    assert settings.model("gemini_flash").cost(1000, 1000) is None
    assert settings.model("gemma_local").cost(5000, 5000) == 0.0


def test_a_fallback_to_an_unknown_model_is_rejected(raw: dict):
    raw["router"]["fallback_order"].append("gpt_9")
    with pytest.raises(ValidationError, match="gpt_9"):
        ModelSettings.model_validate(raw)


def test_a_prior_outside_zero_and_one_is_rejected(raw: dict):
    raw["models"][0]["prior"]["code"] = 1.4
    with pytest.raises(ValidationError, match="between 0 and 1"):
        ModelSettings.model_validate(raw)


def test_duplicate_model_names_are_rejected(raw: dict):
    raw["models"][1]["name"] = raw["models"][0]["name"]
    with pytest.raises(ValidationError, match="unique"):
        ModelSettings.model_validate(raw)


def test_loading_from_another_path(tmp_path: Path):
    copy = tmp_path / "models.toml"
    copy.write_bytes(MODELS_FILE.read_bytes())
    assert load_model_settings(copy).model("gpt_nano").model_id == "gpt-5-nano"
