"""B4: the two stage batch against every report through stage 2, on the small file (offline)."""

from __future__ import annotations

import json
import math

import pytest

from safereport import batch_eval


REQUEST = "Plan this week's inspections in Texas."


@pytest.fixture
def result(small_services):
    return batch_eval.compare(small_services, REQUEST)


def test_the_counterfactual_sends_every_report_and_keeps_the_router_as_it_is(small_services):
    full = batch_eval.everything_through_stage2(small_services)
    assert full.settings.router.min_confidence == math.inf
    # The router, its settings and its log are the app's own: models are picked as in the app.
    assert full.router is small_services.router
    assert full.router.settings.router.min_confidence == small_services.settings.router.min_confidence < 1
    # The services the app uses are not changed.
    assert small_services.settings.router.min_retrieval_margin != math.inf


def test_every_report_goes_through_stage2_and_costs_at_least_as_many_calls(result):
    two, full = result["two_stages"], result["every_report_through_stage2"]
    assert full["reports_through_stage2"] == full["reports"] == two["reports"] == 5
    assert two["reports_through_stage2"] <= full["reports_through_stage2"]
    assert full["measured"]["model_calls"] >= two["measured"]["model_calls"]
    saved = result["saving"]["measured_model_calls"]
    assert saved["saved"] == full["measured"]["model_calls"] - two["measured"]["model_calls"]
    # Each extra report takes the two branch steps: intake coding and standards terms.
    extra = full["reports_through_stage2"] - two["reports_through_stage2"]
    branch = full["measured"]["calls_by_agent"]["branch"] - two["measured"]["calls_by_agent"].get("branch", 0)
    assert branch == 2 * extra
    assert set(result["reports_skipped_by_two_stages"]) <= {"1", "2", "3", "4", "5"}
    assert len(result["reports_skipped_by_two_stages"]) == extra


def test_the_planner_call_is_counted(result):
    assert result["two_stages"]["measured"]["calls_by_agent"].get("planner") == 1


def test_estimates_are_kept_apart_from_measurements(result):
    for run in (result["two_stages"], result["every_report_through_stage2"]):
        log, system = run["estimated"]["offline_log"], run["estimated"]["with_system_prompts"]
        assert system["input_tokens"] > log["input_tokens"] > 0
        assert system["cost_usd"] >= log["cost_usd"] >= 0
        assert "model_calls" in run["measured"] and "model_calls" not in run["estimated"]


def test_the_result_lists_each_change_and_is_plain_json(result):
    changes = result["changes"]
    for kind in ("decisions", "category_one", "cited_standard", "priority"):
        count = changes["decisions_changed" if kind == "decisions" else f"{kind}_changed"]
        assert len(changes["by_report"][kind]) == count
        for change in changes["by_report"][kind]:
            assert change["two_stages"] != change["every_report"]
    assert len(result["limitations"]) >= 5
    json.dumps(result)


def test_the_same_week_gives_the_same_numbers_twice(small_services):
    first = batch_eval.compare(small_services, REQUEST)
    again = batch_eval.compare(small_services, REQUEST)
    assert first["saving"] == again["saving"] and first["changes"] == again["changes"]


def test_the_approved_lists_cover_every_report_and_match_the_changes(result):
    lists = result["approved_lists"]
    two, full = lists["two_stages"], lists["every_report_through_stage2"]
    assert set(two) == set(full) and len(two) == result["two_stages"]["reports"]
    differ = {
        (rid, f)
        for rid in two
        for f in ("decision", "category_one", "priority", "standard")
        if two[rid][f] != full[rid][f]
    }
    listed = {(c["report_id"], f) for f, key in (("decision", "decisions"), ("category_one", "category_one"),
              ("priority", "priority"), ("standard", "cited_standard")) for c in result["changes"]["by_report"][key]}  # fmt: skip
    assert differ == listed
    assert (
        result["earlier_estimate"]["measured_calls_every_report"]
        == (result["every_report_through_stage2"]["measured"]["model_calls"])
    )
