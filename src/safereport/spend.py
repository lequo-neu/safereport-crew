"""Paid model calls are cached and capped.

Every live reply is stored in SQLite under its model, task and prompt, so asking the same thing
again costs nothing. Every paid call adds its cost to a running total kept in the same file, and
a call that would start after the total reached the budget is refused. A model without a
confirmed price is charged at the highest configured price, so the cap errs on the safe side.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import threading

from safereport.backends import Backend, ModelError, Reply
from safereport.config import PROJECT_ROOT, ModelSettings, ModelSpec


CACHE_FILE = PROJECT_ROOT / "outputs" / "model_cache.sqlite"
BUDGET_USD = 1.50  # agreed by the team for the experiments before the final runs


class BudgetExceededError(RuntimeError):
    """The paid calls so far reached the budget; no new paid call starts."""


class SpendLedger:
    def __init__(self, path: Path | str = CACHE_FILE) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.con = sqlite3.connect(str(path), check_same_thread=False)
        self.con.execute("CREATE TABLE IF NOT EXISTS replies (key TEXT PRIMARY KEY, model TEXT, reply TEXT)")
        self.con.execute(
            "CREATE TABLE IF NOT EXISTS spend (at TEXT, model TEXT, task TEXT, input_tokens INTEGER, "
            "output_tokens INTEGER, cost REAL, priced INTEGER)"
        )
        self.con.commit()

    def get(self, key: str) -> Reply | None:
        with self.lock:
            row = self.con.execute("SELECT reply FROM replies WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        stored = json.loads(row[0])
        return Reply(**{**stored, "seconds": 0.0, "cached": True})

    def put(self, key: str, reply: Reply) -> None:
        stored = {"model": reply.model, "text": reply.text, "data": reply.data,
                  "input_tokens": reply.input_tokens, "output_tokens": reply.output_tokens}  # fmt: skip
        with self.lock:
            self.con.execute(
                "INSERT OR REPLACE INTO replies VALUES (?, ?, ?)", (key, reply.model, json.dumps(stored))
            )
            self.con.commit()

    def charge(self, model: str, task: str, reply: Reply, cost: float, priced: bool) -> None:
        with self.lock:
            self.con.execute(
                "INSERT INTO spend VALUES (?, ?, ?, ?, ?, ?, ?)",
                (datetime.now(UTC).isoformat(timespec="seconds"), model, task, reply.input_tokens,
                 reply.output_tokens, cost, int(priced)),
            )  # fmt: skip
            self.con.commit()

    def spent(self) -> float:
        with self.lock:
            return float(self.con.execute("SELECT coalesce(sum(cost), 0) FROM spend").fetchone()[0])

    def summary(self) -> list[dict]:
        with self.lock:
            rows = self.con.execute(
                "SELECT model, count(*), sum(input_tokens), sum(output_tokens), round(sum(cost), 4), min(priced) "
                "FROM spend GROUP BY model ORDER BY model"
            ).fetchall()
        return [{"model": m, "calls": c, "input_tokens": i, "output_tokens": o, "cost": cost, "priced": bool(p)}
                for m, c, i, o, cost, p in rows]  # fmt: skip


def ceiling_price(settings: ModelSettings) -> tuple[float, float]:
    priced = [m.prices for m in settings.models if m.prices is not None]
    return (max(p[0] for p in priced), max(p[1] for p in priced)) if priced else (10.0, 50.0)


@dataclass
class CachedBackend:
    """A live backend behind the cache and the budget."""

    inner: Backend
    spec: ModelSpec
    ledger: SpendLedger
    ceiling: tuple[float, float]
    budget: float = BUDGET_USD
    name: str = field(init=False)

    def __post_init__(self) -> None:
        self.name = self.inner.name

    def complete(self, step: str, prompt: str) -> Reply:
        key = hashlib.sha256(f"{self.spec.model_id}\n{step}\n{prompt}".encode()).hexdigest()
        cached = self.ledger.get(key)
        if cached is not None:
            return cached
        if self.ledger.spent() >= self.budget:
            raise BudgetExceededError(
                f"paid calls reached the ${self.budget:.2f} budget; no new call was made"
            )
        try:
            reply = self.inner.complete(step, prompt)
        except ModelError as error:
            # An unusable reply is charged too, so the cap counts every token paid for; it is
            # not cached, so asking again makes a new call.
            if error.reply is not None:
                self._charge(step, error.reply)
            raise
        self._charge(step, reply)
        self.ledger.put(key, reply)
        return reply

    def _charge(self, step: str, reply: Reply) -> None:
        priced = self.spec.prices is not None
        prices = self.spec.prices or self.ceiling
        cost = (reply.input_tokens * prices[0] + reply.output_tokens * prices[1]) / 1_000_000
        self.ledger.charge(self.name, step, reply, cost, priced)


def guarded(backends: dict[str, Backend], settings: ModelSettings, ledger: SpendLedger | None = None,
            budget: float = BUDGET_USD) -> dict[str, CachedBackend]:  # fmt: skip
    ledger = ledger or SpendLedger()
    ceiling = ceiling_price(settings)
    return {
        name: CachedBackend(b, settings.model(name), ledger, ceiling, budget) for name, b in backends.items()
    }
