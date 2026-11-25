"""The prevention plan (N13, #41): the solver, the Safety Pays costs, the counts and the ledger."""

from __future__ import annotations

from datetime import date

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
import pandas as pd
import pytest

from safereport.data import CODES_V3_PARQUET, REPORTS_PARQUET, Filters, ReportStore
from safereport.graph import build_graph, run_config
from safereport.ledger import FactLedger
from safereport.prevention import (
    Control,
    assign,
    choose,
    load_controls,
    load_safety_pays,
    make_plan,
    with_changes,
)
from safereport.writer import draft


def row(name: str, cost: float, low: float, high: float | None = None) -> dict:
    return {"control": name, "yearly_cost": cost, "prevented": (low, low if high is None else high)}


class FakeStore:
    """A store that answers every query with the same reports, so the plan runs with no data."""

    def __init__(self, frame: pd.DataFrame) -> None:
        self.data = frame

    def frame(self, sql: str, params: list) -> pd.DataFrame:
        return self.data.copy()


def reports(counts: dict[tuple[str, str], int], nature: str = "Amputations") -> pd.DataFrame:
    rows = []
    for (event, source), n in counts.items():
        rows += [{"id": str(len(rows) + i), "event_code_v3": event, "source_code": source, "nature_title": nature}
                 for i in range(n)]  # fmt: skip
    return pd.DataFrame(rows)


# ---- The solver ----


def test_a_hand_solved_case_matches_the_solver():
    # Budget 7: A alone prevents 10; B and C together cost 7 and prevent 13, which is the best.
    rows = [row("a", 5, 10), row("b", 4, 7), row("c", 3, 6)]
    assert sorted(choose(rows, 7, 0)) == ["b", "c"]
    # Budget 5: A (10) beats B (7), C (6) and nothing fits two of them.
    assert choose(rows, 5, 0) == ["a"]


def test_a_zero_budget_funds_nothing_and_a_large_one_funds_everything():
    rows = [row("a", 5, 10), row("b", 4, 7), row("c", 3, 6)]
    assert choose(rows, 0, 0) == []
    assert sorted(choose(rows, 12, 0)) == ["a", "b", "c"]
    assert sorted(choose(rows, 1e9, 0)) == ["a", "b", "c"]


def test_a_control_that_prevents_nothing_is_never_funded():
    assert choose([row("a", 5, 10), row("empty", 0, 0)], 100, 0) == ["a"]


def test_the_high_end_never_prevents_less_than_the_low_end():
    controls = load_controls()
    frame = reports(
        {("652", ""): 30, ("653", ""): 20, ("41", ""): 8, ("43", ""): 5, ("25", "8621"): 6, ("99", ""): 9}
    )
    store = FakeStore(frame)
    for budget in (0, 3000, 9000, 20000, 40000, 60000, 1e6):
        plan = make_plan(store, budget=budget, controls=controls)
        low, high = plan["plans"]["low"], plan["plans"]["high"]
        assert high["prevented"] >= low["prevented"] - 1e-6
        assert low["cost"] <= budget and high["cost"] <= budget


# ---- Matching injuries to controls and costing them ----


def test_each_report_goes_to_one_control_events_first_then_sources():
    controls = load_controls()
    frame = reports(
        {("652", "8621"): 2, ("653", ""): 1, ("41", ""): 1, ("43", ""): 1, ("25", "8621"): 3, ("99", ""): 4}
    )
    chosen = assign(frame, controls).value_counts().to_dict()
    # A forklift injury coded 652 counts for the lockout program, not twice.
    assert chosen == {"lockout program": 2, "machine guarding": 1, "fall protection": 1, "housekeeping": 1,
                      "forklift training": 3, "": 4}  # fmt: skip


def test_safety_pays_costs_follow_osha_direct_cost_and_sliding_scale():
    pays = load_safety_pays()
    assert pays.injury_type(" Amputations, avulsions, enucleations  unspecified") == "AMPUTATION"
    assert pays.injury_type("Fractures") == "FRACTURE"
    assert pays.injury_type("Heat (thermal) burns, unspecified") == "BURN"
    assert pays.injury_type("Soreness, pain, hurt-nonspecified injury") == "ALL OTHER SPECIFIC INJURIES, NOC"
    # Direct 96,003 is $10,000 or more, so indirect is 1.1 times it: total 2.1 times.
    assert pays.total_cost("AMPUTATION") == pytest.approx(96003 * 2.1)
    assert pays.ratio(2000) == 4.5 and pays.ratio(4000) == 1.6 and pays.ratio(9000) == 1.2


def test_the_expected_cost_scales_with_the_plant_and_the_share():
    pays = load_safety_pays()
    frame = reports({("652", ""): 3, ("99", ""): 1})
    plan = make_plan(FakeStore(frame), budget=0, plant_injuries=2.0, pays=pays)
    lockout = next(r for r in plan["rows"] if r["control"] == "lockout program")
    assert lockout["share"] == 0.75 and lockout["expected_injuries"] == 1.5
    assert lockout["expected_cost"] == pytest.approx(1.5 * pays.total_cost("AMPUTATION"))
    assert lockout["prevented"] == pytest.approx(
        (0.4 * lockout["expected_cost"], 0.8 * lockout["expected_cost"])
    )
    assert plan["uncovered"] == 1


def test_the_users_costs_and_effects_replace_the_assumptions():
    changed = with_changes(
        load_controls(), [{"name": "Housekeeping", "yearly_cost": 1, "effect_low": 0.1, "effect_high": 0.2}]
    )
    housekeeping = next(c for c in changed if c.name == "housekeeping")
    assert housekeeping.yearly_cost == 1 and housekeeping.effect == (0.1, 0.2)
    with pytest.raises(ValueError):
        Control("bad", "", 1, (0.8, 0.2))


# ---- The answer and the crew ----


def test_the_answer_template_has_no_number_the_ledger_did_not_record():
    template = draft({"kind": "prevention_plan", "widened": True})["template"]
    assert FactLedger().untraced(template) == []


def test_the_crew_writes_the_plan_with_every_number_traced(small_services):
    graph = build_graph(small_services, InMemorySaver())
    out = graph.invoke({"request": "Make a $40,000 prevention plan for a plastics plant in Ohio.", "params": {}},
                       run_config())  # fmt: skip
    assert "yearly budget of $40,000" in out["answer"]
    assert out["trace"][-1]["summary"] == "every citation, number and rule checks out"
    assert {"Planner", "Analyst", "Optimizer", "Writer", "Decision critic"} <= {
        t["agent"] for t in out["trace"]
    }


def test_a_plan_with_no_budget_asks_for_it(small_services):
    graph = build_graph(small_services, InMemorySaver())
    config = run_config()
    out = graph.invoke({"request": "Make a prevention plan for my plant."}, config)
    assert out["__interrupt__"][0].value["missing"] == ["budget"]
    out = graph.invoke(Command(resume={"budget": "$25,000"}), config)
    assert "yearly budget of $25,000" in out["answer"]


# ---- On the real file ----

needs_data = pytest.mark.skipif(
    not (REPORTS_PARQUET.exists() and CODES_V3_PARQUET.exists()),
    reason="build the data and baseline first (see README)",
)


@needs_data
def test_the_counts_match_the_trends_page_for_the_same_industry_and_state():
    store = ReportStore()
    plan = make_plan(store, budget=40000, naics_prefix="326", state="TEXAS", since=2019)
    assert not plan["widened"]
    counts = {r["control"]: r["reports"] for r in plan["rows"]}
    for control in load_controls():
        for event in control.events:
            trend = store.yearly_trend(Filters(state="TEXAS", naics_prefix="326", event_group_v3=event,
                                               start=date(2019, 1, 1)))  # fmt: skip
            assert counts[control.name] == int(trend[trend["year"] >= 2019]["reports"].sum())
    all_reports = store.yearly_trend(Filters(state="TEXAS", naics_prefix="326", start=date(2019, 1, 1)))
    assert plan["reports"] == int(all_reports[all_reports["year"] >= 2019]["reports"].sum())


def test_the_net_value_says_when_a_plan_costs_more_than_it_prevents():
    from safereport.prevention import money

    plan = make_plan(FakeStore(reports({("43", ""): 1, ("99", ""): 99})), budget=5000)
    low = plan["plans"]["low"]
    assert low["funded"] == ["housekeeping"] and low["net"] == pytest.approx(low["prevented"] - low["cost"])
    assert low["net"] < 0 and money(low["net"]).startswith("-$")
    assert money(-3134.4) == "-$3,134" and money(0.2) == "$0"
