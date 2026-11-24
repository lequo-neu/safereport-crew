"""Pick a model for each step, move up when the pipeline is unsure, fall back when a provider fails.

The router starts from the cheapest model whose accuracy for the step type clears the bar for
the case's difficulty. Signals from the pipeline itself move a step up to a stronger model: a
low Intake confidence, the baseline and the model disagreeing, two standards scoring close
together, or the critic rejecting a draft. A timeout, rate limit or server error moves the call
down the fallback chain from the config. Every call is logged with its tokens, cost and time.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import sqlite3
import threading
import time
from typing import Literal

from safereport.backends import Backend, ModelError, OfflineBackend, Reply
from safereport.config import ModelSettings, ModelSpec, StepType


Mode = Literal["best_quality", "lowest_cost", "private"]
Difficulty = Literal["simple", "moderate", "hard"]


@dataclass
class Signals:
    """What the pipeline knows about a case before a step runs."""

    intake_confidence: float | None = None
    disagreement: bool = False
    retrieval_margin: float | None = None
    critic_rejected: bool = False

    def reasons(self, settings: ModelSettings) -> list[str]:
        router = settings.router
        found = []
        if self.intake_confidence is not None and self.intake_confidence < router.min_confidence:
            found.append(f"Intake confidence {self.intake_confidence:.2f} below {router.min_confidence:.2f}")
        if self.disagreement:
            found.append("baseline and model disagree on the event group")
        if self.retrieval_margin is not None and self.retrieval_margin < router.min_retrieval_margin:
            found.append(f"top two standards {self.retrieval_margin:.2f} apart")
        if self.critic_rejected:
            found.append("the critic rejected the last draft")
        return found


@dataclass
class Choice:
    model: ModelSpec
    reason: str
    based_on_prior: bool


@dataclass
class CallRecord:
    run_id: str
    node: str
    step: StepType
    model: str
    reason: str
    fallback_from: str
    input_tokens: int
    output_tokens: int
    cost: float | None
    seconds: float
    error: str = ""


class UsageLog:
    """Every model call in SQLite: the evaluation page and the AI controls page read it."""

    def __init__(self, path: Path | str = ":memory:") -> None:
        # Parallel report branches call models from several threads; one lock keeps writes in order.
        self.lock = threading.Lock()
        self.con = sqlite3.connect(str(path), check_same_thread=False)
        self.con.execute(
            "CREATE TABLE IF NOT EXISTS calls (at TEXT, run_id TEXT, node TEXT, step TEXT, model TEXT, reason TEXT, "
            "fallback_from TEXT, input_tokens INTEGER, output_tokens INTEGER, cost REAL, seconds REAL, error TEXT)"
        )

    def add(self, record: CallRecord) -> None:
        with self.lock:
            self._insert(record)

    def _insert(self, record: CallRecord) -> None:
        self.con.execute(
            "INSERT INTO calls VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now(UTC).isoformat(timespec="seconds"),
                record.run_id,
                record.node,
                record.step,
                record.model,
                record.reason,
                record.fallback_from,
                record.input_tokens,
                record.output_tokens,
                record.cost,
                record.seconds,
                record.error,
            ),
        )
        self.con.commit()

    def rows(self, run_id: str | None = None) -> list[dict]:
        with self.lock:
            if run_id:
                cursor = self.con.execute("SELECT * FROM calls WHERE run_id = ? ORDER BY rowid", (run_id,))
            else:
                cursor = self.con.execute("SELECT * FROM calls ORDER BY rowid")
            names = [c[0] for c in cursor.description]
            return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def difficulty(signals: Signals, settings: ModelSettings) -> Difficulty:
    count = len(signals.reasons(settings))
    return "simple" if count == 0 else "moderate" if count == 1 else "hard"


OUTAGES = ("server_error", "timeout", "rate_limit")


@dataclass
class Router:
    settings: ModelSettings
    backends: dict[str, Backend]
    log: UsageLog = field(default_factory=UsageLog)
    measured: dict[tuple[str, str], float] = field(default_factory=dict)
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    # Models in an outage: name to (time it may be tried again, the error that put it there).
    down: dict[str, tuple[float, ModelError]] = field(default_factory=dict)

    def accuracy(self, model: ModelSpec, step: StepType) -> tuple[float, bool]:
        """Measured accuracy when the evaluation has one, else the config's prior (flagged)."""
        if (model.name, step) in self.measured:
            return self.measured[(model.name, step)], False
        return model.prior.get(step, 0.0), True

    def choose(self, step: StepType, signals: Signals, mode: Mode = "lowest_cost") -> Choice:
        models = [m for m in self.settings.models if m.name in self.backends]
        if mode == "private":
            models = [m for m in models if m.is_local]
            if not models:
                raise RuntimeError("private mode needs the local model")
            model = models[0]
            prior = self.accuracy(model, step)[1]
            return Choice(model, "private mode: every step stays on this machine", prior)
        level = difficulty(signals, self.settings)
        bar = self.settings.router.bar[level]
        scored = [(m, *self.accuracy(m, step)) for m in models]
        if mode == "best_quality":
            model, share, prior = max(scored, key=lambda s: s[1])
            return Choice(model, f"best quality: highest accuracy for {step} ({share:.2f})", prior)
        clearing = [s for s in scored if s[1] >= bar]
        reasons = signals.reasons(self.settings)
        why = f"{level} case" + (f" ({'; '.join(reasons)})" if reasons else "")
        if not clearing:
            model, share, prior = max(scored, key=lambda s: s[1])
            return Choice(
                model, f"{why}: no model clears {bar:.2f}, so the most accurate ({share:.2f})", prior
            )

        def price(spec: ModelSpec) -> float:
            # A model without a confirmed price is ranked after the priced ones.
            return sum(spec.prices) if spec.prices is not None else float("inf")

        model, share, prior = min(clearing, key=lambda s: (price(s[0]), -s[1]))
        return Choice(model, f"{why}: cheapest model clearing {bar:.2f} for {step} ({share:.2f})", prior)

    def call(
        self, step: StepType, prompt: str, *, signals: Signals | None = None, mode: Mode = "lowest_cost",
        node: str = "", run_id: str = "", task: str = "",
    ) -> tuple[Reply, CallRecord]:  # fmt: skip
        """Run one step on the chosen model, falling back along the chain when a provider fails.

        `task` is the backend's handler name (for example "intake"); it defaults to the step type.
        """
        choice = self.choose(step, signals or Signals(), mode)
        order = [choice.model]
        if mode != "private":
            order += [m for m in self.settings.fallback_after(choice.model.name) if m.name in self.backends]
        reason = choice.reason + (" [prior, not yet measured]" if choice.based_on_prior else "")
        failed_from, last_error = "", None
        for position, model in enumerate(order):
            until, error = self.down.get(model.name, (0.0, None))
            # A model in an outage is skipped until its cool down ends, unless it is the last hope.
            if error is not None and self.clock() < until and position < len(order) - 1:
                failed_from, last_error = model.name, error
                continue
            for attempt in range(self.settings.router.retries_per_model + 1):
                started = time.perf_counter()
                try:
                    reply = self.backends[model.name].complete(task or step, prompt)
                except ModelError as error:
                    last_error = error
                    self.log.add(
                        CallRecord(
                            run_id,
                            node,
                            step,
                            model.name,
                            reason,
                            failed_from,
                            0,
                            0,
                            0.0,
                            time.perf_counter() - started,
                            error.kind,
                        )
                    )
                    if attempt < self.settings.router.retries_per_model:
                        self.sleep(self.settings.router.backoff_seconds)
                    continue
                record = CallRecord(
                    run_id, node, step, model.name,
                    reason if not failed_from else f"fallback after {failed_from} failed ({last_error.kind})",
                    failed_from, reply.input_tokens, reply.output_tokens,
                    0.0 if reply.cached else model.cost(reply.input_tokens, reply.output_tokens),
                    reply.seconds or time.perf_counter() - started,
                )  # fmt: skip
                self.log.add(record)
                self.down.pop(model.name, None)
                return reply, record
            if last_error is not None and last_error.kind in OUTAGES:
                self.down[model.name] = (self.clock() + self.settings.router.cooldown_seconds, last_error)
            failed_from = model.name
        raise RuntimeError(f"every model failed for {step}: {last_error}")


def offline_router(
    settings: ModelSettings, handlers: dict[str, Callable], log: UsageLog | None = None
) -> Router:
    """A router whose every model answers from the same deterministic handlers, offline."""
    backends = {m.name: OfflineBackend(name=m.name, handlers=dict(handlers)) for m in settings.models}
    measured = {
        (model.name, step): accuracy for model in settings.models for step, accuracy in model.measured.items()
    }
    return Router(
        settings,
        backends,
        log or UsageLog(),
        measured=measured,
        sleep=lambda _: None,
    )
