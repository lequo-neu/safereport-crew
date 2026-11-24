"""The prevention plan (N13): which controls a plant should fund first within a yearly budget.

The injuries come from severe injury reports in plants like the user's (same industry and state,
counted by OIICS 3 event group as on the Trends page). Each report gets the OSHA Safety Pays cost
of its injury type, direct plus indirect. The plant says how many severe injuries it has a year,
and the mix of those injuries is the mix of the reports. Each control's cost and effect are
planning assumptions (`config/prevention.toml`) the user can change; an integer program (PuLP,
as the Optimizer uses for the week) picks the set that prevents the most expected injury cost
within the budget, once at the low and once at the high end of every control's effect.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
import re
import tomllib
from typing import Any

import pandas as pd
import pulp

from safereport.config import PROJECT_ROOT
from safereport.data import Filters, ReportStore


CONTROLS_FILE = PROJECT_ROOT / "config" / "prevention.toml"
SAFETY_PAYS_FILE = PROJECT_ROOT / "data" / "reference" / "safety_pays.toml"
# Fewest reports the plan takes its injury mix from before it widens the scope, as the safety talk does.
MIN_REPORTS = 10
DEFAULT_SINCE = 2019


@dataclass(frozen=True)
class Control:
    name: str
    why: str
    yearly_cost: float
    effect: tuple[float, float]
    events: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        low, high = self.effect
        if not 0 <= low <= high <= 1:
            raise ValueError(f"{self.name}: the effect is a share range with low <= high, got {self.effect}")
        if self.yearly_cost < 0:
            raise ValueError(f"{self.name}: the yearly cost cannot be negative")


def load_controls(path: Path = CONTROLS_FILE) -> list[Control]:
    raw = tomllib.loads(Path(path).read_text())["controls"]
    return [
        Control(name=c["name"], why=c.get("why", ""), yearly_cost=float(c["yearly_cost"]),
                effect=(float(c["effect"][0]), float(c["effect"][1])),
                events=tuple(c.get("events", ())), sources=tuple(c.get("sources", ())))
        for c in raw
    ]  # fmt: skip


def with_changes(controls: list[Control], changes: list[dict[str, Any]] | None) -> list[Control]:
    """The controls with the user's own costs and effects, matched by name."""
    by_name = {str(c.get("name", "")).strip().lower(): c for c in changes or []}
    out = []
    for control in controls:
        change = by_name.get(control.name)
        if change is None:
            out.append(control)
            continue
        low = float(change.get("effect_low", control.effect[0]))
        high = float(change.get("effect_high", control.effect[1]))
        out.append(replace(control, yearly_cost=float(change.get("yearly_cost", control.yearly_cost)),
                           effect=(low, high)))  # fmt: skip
    return out


@dataclass(frozen=True)
class SafetyPays:
    direct: dict[str, float]
    scale: list[tuple[float, float]]
    nature_map: list[tuple[re.Pattern[str], str]]
    fallback: str
    source: str
    years: str
    url: str

    def injury_type(self, nature: str) -> str:
        text = (nature or "").strip().lower()
        return next((kind for pattern, kind in self.nature_map if pattern.search(text)), self.fallback)

    def ratio(self, direct: float) -> float:
        return next(r for upper, r in self.scale if direct < upper)

    def total_cost(self, injury_type: str) -> float:
        """Direct plus indirect cost, as Safety Pays adds them."""
        direct = self.direct[injury_type]
        return direct * (1 + self.ratio(direct))


def load_safety_pays(path: Path = SAFETY_PAYS_FILE) -> SafetyPays:
    raw = tomllib.loads(Path(path).read_text())
    pays = SafetyPays(
        direct={k: float(v) for k, v in raw["direct_cost"].items()},
        scale=[(float(u), float(r)) for u, r in raw["indirect_scale"]],
        nature_map=[(re.compile(p), kind) for p, kind in raw["nature_map"]],
        fallback=raw["fallback"], source=raw["source"], years=raw["years"], url=raw["url"],
    )  # fmt: skip
    unknown = {kind for _, kind in pays.nature_map} - set(pays.direct) | ({pays.fallback} - set(pays.direct))
    if unknown:
        raise ValueError(f"injury types with no Safety Pays cost: {sorted(unknown)}")
    return pays


def assign(frame: pd.DataFrame, controls: list[Control]) -> pd.Series:
    """The control that addresses each report ("" for none): event controls first, in order, then
    source controls for the reports left, so every report counts once."""
    chosen = pd.Series("", index=frame.index, dtype=object)
    events = frame["event_code_v3"].fillna("").astype(str)
    sources = frame["source_code"].fillna("").astype(str)
    for control in [c for c in controls if c.events] + [c for c in controls if not c.events]:
        hit = pd.Series(False, index=frame.index)
        for prefix in control.events:
            hit |= events.str.startswith(prefix)
        for prefix in control.sources:
            hit |= sources.str.startswith(prefix)
        chosen[(chosen == "") & hit] = control.name
    return chosen


def choose(rows: list[dict[str, Any]], budget: float, end: int) -> list[str]:
    """The controls that prevent the most expected cost within the budget (0 = low end, 1 = high end).

    Between two plans that prevent the same, the cheaper one wins; a control that prevents nothing
    is never funded."""
    useful = [r for r in rows if r["prevented"][end] > 0]
    if not useful or budget <= 0:
        return []
    problem = pulp.LpProblem("prevention", pulp.LpMaximize)
    pick = {r["control"]: pulp.LpVariable(f"x_{n}", cat="Binary") for n, r in enumerate(useful)}
    tie = 1e-6 / (1 + sum(r["yearly_cost"] for r in useful))
    problem += pulp.lpSum((r["prevented"][end] - tie * r["yearly_cost"]) * pick[r["control"]] for r in useful)
    problem += pulp.lpSum(r["yearly_cost"] * pick[r["control"]] for r in useful) <= budget
    problem.solve(pulp.PULP_CBC_CMD(msg=False))
    return [r["control"] for r in useful if (pick[r["control"]].value() or 0) > 0.5]


def plan_rows(frame: pd.DataFrame, controls: list[Control], pays: SafetyPays, plant_injuries: float):
    """One row per control: its reports, their share and cost, and the expected cost it prevents."""
    frame = frame.assign(control=assign(frame, controls))
    frame["cost"] = [pays.total_cost(pays.injury_type(n)) for n in frame["nature_title"].fillna("")]
    total = len(frame)
    rows = []
    for control in controls:
        part = frame[frame["control"] == control.name]
        share = len(part) / total if total else 0.0
        per_injury = float(part["cost"].mean()) if len(part) else 0.0
        expected = plant_injuries * share * per_injury
        rows.append({
            "control": control.name, "why": control.why, "reports": len(part), "share": share,
            "cost_per_injury": per_injury, "expected_injuries": plant_injuries * share,
            "expected_cost": expected, "yearly_cost": control.yearly_cost, "effect": control.effect,
            "prevented": (expected * control.effect[0], expected * control.effect[1]),
        })  # fmt: skip
    return rows, total, int((frame["control"] == "").sum())


def make_plan(
    store: ReportStore,
    *,
    budget: float,
    naics_prefix: str = "3",
    state: str = "",
    since: int = DEFAULT_SINCE,
    plant_injuries: float = 1.0,
    controls: list[Control] | None = None,
    pays: SafetyPays | None = None,
) -> dict[str, Any]:
    controls = controls if controls is not None else load_controls()
    pays = pays or load_safety_pays()
    wanted = (naics_prefix, state.upper())
    for prefix, place in dict.fromkeys([wanted, (naics_prefix, ""), ("", "")]):
        where, params = Filters(state=place, naics_prefix=prefix, start=date(since, 1, 1)).where()
        frame = store.frame(
            f"SELECT id, event_code_v3, source_code, nature_title FROM reports WHERE {where}",  # noqa: S608 (fixed fragments, parameter values)
            params,
        )
        if len(frame) >= MIN_REPORTS:
            break
    rows, total, uncovered = plan_rows(frame, controls, pays, plant_injuries)
    plans = {}
    for end, label in ((0, "low"), (1, "high")):
        funded = choose(rows, budget, end)
        plans[label] = {
            "funded": funded,
            "cost": sum(r["yearly_cost"] for r in rows if r["control"] in funded),
            "prevented": sum(r["prevented"][end] for r in rows if r["control"] in funded),
        }
        plans[label]["net"] = plans[label]["prevented"] - plans[label]["cost"]
    scope = (f"NAICS {prefix}" if prefix else "all industries") + (
        f" in {place.title()}" if place else " nationwide"
    )
    return {"rows": rows, "plans": plans, "reports": total, "uncovered": uncovered, "scope": scope,
            "widened": (prefix, place) != wanted, "since": since, "budget": budget,
            "plant_injuries": plant_injuries, "pays": {"source": pays.source, "years": pays.years, "url": pays.url}}  # fmt: skip


def money(value: float) -> str:
    return f"-${-value:,.0f}" if round(value) < 0 else f"${value:,.0f}"


def names(funded: list[str]) -> str:
    if not funded:
        return "nothing"
    return funded[0] if len(funded) == 1 else ", ".join(funded[:-1]) + " and " + funded[-1]
