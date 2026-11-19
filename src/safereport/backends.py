"""Model backends: the one interface every agent calls, and a deterministic offline backend.

The offline backend answers from scripted handlers, so the graph, the router and the critic
can be tested end to end in seconds with no API key, no GPU and no model download. It can
also be told to fail in the ways real providers fail, which is how the fallback chain is tested.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import json
import math
from typing import Any, Literal, Protocol


FailureKind = Literal["timeout", "rate_limit", "server_error", "bad_request", "refusal", "bad_output"]
Handler = Callable[[str], "str | dict[str, Any]"]


class ModelError(RuntimeError):
    """A provider failed in a way that should move the call to the next model."""

    def __init__(self, kind: FailureKind, model: str, reply: Reply | None = None) -> None:
        super().__init__(f"{model}: {kind}")
        self.kind = kind
        self.model = model
        # A reply that came back but could not be used still used tokens, which are paid for.
        self.reply = reply


@dataclass
class Reply:
    """One model answer, with what the cost logger and the trace need."""

    model: str
    text: str
    data: dict[str, Any] | None
    input_tokens: int
    output_tokens: int
    seconds: float
    cached: bool = False


class Backend(Protocol):
    name: str

    def complete(self, step: str, prompt: str) -> Reply: ...


def estimate_tokens(text: str) -> int:
    """About four characters per token, close enough for offline cost estimates."""
    return max(1, math.ceil(len(text) / 4))


@dataclass
class OfflineBackend:
    """Answers each step with a scripted handler; unscripted steps get a fixed reply.

    `failures` maps a step to the failures to raise, one per call, before it answers normally.
    """

    name: str = "offline"
    handlers: dict[str, Handler] = field(default_factory=dict)
    failures: dict[str, list[FailureKind]] = field(default_factory=dict)
    calls: list[tuple[str, str]] = field(default_factory=list)

    def script(self, step: str, handler: Handler) -> None:
        self.handlers[step] = handler

    def complete(self, step: str, prompt: str) -> Reply:
        self.calls.append((step, prompt))
        pending = self.failures.get(step)
        if pending:
            raise ModelError(pending.pop(0), self.name)
        handler = self.handlers.get(step)
        answer = handler(prompt) if handler else f"Offline reply for the {step} step."
        data = answer if isinstance(answer, dict) else None
        text = json.dumps(answer, sort_keys=True) if data is not None else str(answer)
        return Reply(
            model=self.name,
            text=text,
            data=data,
            input_tokens=estimate_tokens(prompt),
            output_tokens=estimate_tokens(text),
            seconds=0.0,
        )
