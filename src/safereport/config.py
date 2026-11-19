"""Model and router settings, read from `config/models.toml`.

The file is validated when it is loaded, so a typo in a model name or a fallback chain that
points at a model nobody configured fails at start up instead of in the middle of a batch.
"""

from __future__ import annotations

import os
from pathlib import Path
import tomllib
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODELS_FILE = PROJECT_ROOT / "config" / "models.toml"

Provider = Literal["anthropic", "openai", "google", "local"]
StepType = Literal["code", "retrieve", "decide", "write"]
STEP_TYPES: tuple[StepType, ...] = ("code", "retrieve", "decide", "write")


class ModelSpec(BaseModel):
    name: str
    label: str
    provider: Provider
    model_id: str
    prices: tuple[float, float] | None = None
    context_window: int | None = None
    roles: list[str] = Field(default_factory=list)
    prior: dict[StepType, float] = Field(default_factory=dict)
    checked_on: str
    note: str = ""

    @field_validator("prior")
    @classmethod
    def _shares(cls, prior: dict[StepType, float]) -> dict[StepType, float]:
        for step, share in prior.items():
            if not 0 <= share <= 1:
                raise ValueError(f"prior for {step} must be a share between 0 and 1, got {share}")
        return prior

    @property
    def is_local(self) -> bool:
        return self.provider == "local"

    def cost(self, input_tokens: int, output_tokens: int) -> float | None:
        """Dollar cost of one call, or None when the price is not confirmed."""
        if self.prices is None:
            return None
        return (input_tokens * self.prices[0] + output_tokens * self.prices[1]) / 1_000_000


class RouterSettings(BaseModel):
    bar: dict[Literal["simple", "moderate", "hard"], float]
    fallback_order: list[str]
    min_confidence: float = Field(ge=0, le=1)
    min_retrieval_margin: float = Field(ge=0)
    retries_per_model: int = Field(ge=0)
    backoff_seconds: float = Field(ge=0)
    # After a model fails every retry with an outage (server error, timeout, rate limit), the
    # router skips it for this long, so one dead provider does not slow every later call.
    cooldown_seconds: float = Field(default=60.0, ge=0)


class ModelSettings(BaseModel):
    router: RouterSettings
    models: list[ModelSpec]

    @model_validator(mode="after")
    def _consistent(self) -> ModelSettings:
        names = [m.name for m in self.models]
        if len(names) != len(set(names)):
            raise ValueError(f"model names must be unique: {names}")
        unknown = [n for n in self.router.fallback_order if n not in names]
        if unknown:
            raise ValueError(f"fallback_order names models that are not configured: {unknown}")
        return self

    def model(self, name: str) -> ModelSpec:
        for spec in self.models:
            if spec.name == name:
                return spec
        raise KeyError(f"no model named {name!r} in the config")

    def fallback_after(self, name: str) -> list[ModelSpec]:
        """The models to try, in order, once `name` has failed."""
        order = self.router.fallback_order
        rest = order[order.index(name) + 1 :] if name in order else order
        return [self.model(n) for n in rest]


def load_model_settings(path: Path | str = MODELS_FILE) -> ModelSettings:
    with Path(path).open("rb") as handle:
        return ModelSettings.model_validate(tomllib.load(handle))


def load_env_file(path: Path = PROJECT_ROOT / ".env") -> list[str]:
    """Copy KEY=value lines from the project's .env into the environment (never over a set value).

    Returns the names it set, never the values. The file is gitignored.
    """
    if not path.exists():
        return []
    added = []
    for line in path.read_text().splitlines():
        name, sep, value = line.strip().partition("=")
        if sep and name and not name.startswith("#") and name not in os.environ:
            os.environ[name] = value.strip().strip('"').strip("'")
            added.append(name)
    return added
