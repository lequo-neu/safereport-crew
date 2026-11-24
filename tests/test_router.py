from __future__ import annotations

import pytest

from safereport.backends import OfflineBackend
from safereport.config import load_model_settings
from safereport.router import Router, Signals, UsageLog, difficulty, offline_router


@pytest.fixture
def router() -> Router:
    return offline_router(load_model_settings(), {"code": lambda prompt: "ok", "write": lambda prompt: "ok"})


def test_the_cheapest_model_that_clears_the_bar_is_chosen(router: Router):
    choice = router.choose("code", Signals())
    assert choice.model.name == "gpt_nano" and choice.based_on_prior
    assert "cheapest" in choice.reason


def test_pipeline_signals_move_a_step_up(router: Router):
    unsure = Signals(intake_confidence=0.4, retrieval_margin=0.01)
    assert difficulty(unsure, router.settings) == "hard"
    choice = router.choose("code", unsure)
    assert choice.model.name != "gpt_nano"
    assert "confidence 0.40" in choice.reason and "apart" in choice.reason


def test_a_critic_rejection_escalates_the_writer(router: Router):
    assert router.choose("write", Signals()).model.name == "gpt_nano"
    assert router.choose("write", Signals(critic_rejected=True)).model.name == "claude"


def test_measured_accuracy_replaces_the_prior(router: Router):
    router.measured[("gpt_nano", "code")] = 0.5
    choice = router.choose("code", Signals())
    assert choice.model.name == "gpt_nano"
    assert not choice.based_on_prior
    assert router.accuracy(router.settings.model("gpt_nano"), "code") == (0.5, False)


def test_modes(router: Router):
    assert router.choose("code", Signals(), mode="private").model.name == "gemma_local"
    assert router.choose("write", Signals(), mode="best_quality").model.name in {"claude", "gemini_flash"}


def test_a_failing_provider_falls_back_along_the_chain():
    settings = load_model_settings()
    router = offline_router(settings, {"decide": lambda prompt: "plan"})
    router.backends["claude"] = OfflineBackend(name="claude", handlers={"decide": lambda p: "plan"},
                                               failures={"decide": ["rate_limit", "timeout"]})  # fmt: skip
    _, record = router.call("decide", "{}", node="planner", run_id="r1")
    assert router.choose("decide", Signals()).model.name == "claude"
    assert record.model == "gemini_flash" and record.fallback_from == "claude"
    assert "fallback after claude failed (timeout)" in record.reason
    errors = [row["error"] for row in router.log.rows("r1")]
    assert errors == ["rate_limit", "timeout", ""]


def test_every_model_failing_is_an_error():
    settings = load_model_settings()
    backends = {
        m.name: OfflineBackend(name=m.name, failures={"code": ["server_error"] * 4}) for m in settings.models
    }
    router = Router(settings, backends, UsageLog(), sleep=lambda _: None)
    with pytest.raises(RuntimeError, match="every model failed"):
        router.call("code", "{}")


def test_usage_is_logged_with_cost(router: Router):
    _, record = router.call("code", "x" * 4000, run_id="r2", node="intake")
    row = router.log.rows("r2")[0]
    assert row["model"] == "gpt_nano" and row["input_tokens"] == 1000
    assert row["cost"] == pytest.approx(record.cost) and row["cost"] > 0


def test_a_model_in_an_outage_is_skipped_until_its_cool_down_ends():
    settings = load_model_settings()
    router = offline_router(settings, {"decide": lambda prompt: "plan"})
    router.backends["claude"] = OfflineBackend(name="claude", handlers={"decide": lambda p: "plan"},
                                               failures={"decide": ["server_error"] * 2})  # fmt: skip
    waits, now = [], [0.0]
    router.sleep, router.clock = waits.append, lambda: now[0]
    router.call("decide", "{}", run_id="first")
    assert waits == [settings.router.backoff_seconds], "the first outage is retried once"
    _, record = router.call("decide", "{}", run_id="second")
    assert record.model == "gemini_flash" and record.fallback_from == "claude"
    assert len(waits) == 1 and not router.log.rows("second")[0]["error"], "no wait, no call to claude"
    now[0] = settings.router.cooldown_seconds + 1
    _, record = router.call("decide", "{}", run_id="third")
    assert record.model == "claude" and "claude" not in router.down, (
        "after the cool down claude answers again"
    )


@pytest.mark.parametrize("mode", ["lowest_cost", "best_quality"])
@pytest.mark.parametrize(
    "signals",
    [
        Signals(),
        Signals(intake_confidence=0.4),
        Signals(
            intake_confidence=0.4,
            retrieval_margin=0.01,
        ),
    ],
)
def test_retrieval_prefers_measured_models(router, mode, signals):
    choice = router.choose("retrieve", signals, mode=mode)

    assert choice.model.name == "claude"
    assert not choice.based_on_prior

    if mode == "lowest_cost":
        assert "no model clears" in choice.reason
        assert "measured" in choice.reason


@pytest.mark.parametrize("mode", ["lowest_cost", "best_quality"])
def test_retrieval_uses_nano_when_claude_is_unregistered(router, mode):
    router.backends.pop("claude")

    choice = router.choose("retrieve", Signals(), mode=mode)

    assert choice.model.name == "gpt_nano"
    assert not choice.based_on_prior


@pytest.mark.parametrize("mode", ["lowest_cost", "best_quality"])
def test_retrieval_uses_priors_without_measured_backends(router, mode):
    router.backends.pop("claude")
    router.backends.pop("gpt_nano")

    choice = router.choose("retrieve", Signals(), mode=mode)

    assert choice.model.name == "gemini_flash"
    assert choice.based_on_prior


@pytest.mark.parametrize(
    ("step", "expected"),
    [
        ("code", "gpt_nano"),
        ("decide", "claude"),
        ("write", "gpt_nano"),
    ],
)
def test_unmeasured_steps_keep_existing_policy(router, step, expected):
    choice = router.choose("retrieve" if step == "retrieve" else step, Signals())

    assert choice.model.name == expected
    assert choice.based_on_prior


def test_private_retrieval_stays_local(router):
    choice = router.choose("retrieve", Signals(), mode="private")

    assert choice.model.name == "gemma_local"
    assert choice.based_on_prior
