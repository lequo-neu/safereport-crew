"""Regression tests for the retrospective B7/B8 router comparison."""

from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import shutil

from PIL import Image
import pytest

from safereport import views
from safereport.backends import OfflineBackend
from safereport.outputs import pareto_front, router_pareto_chart
from safereport.router import Router
from safereport.router_pareto import (
    CONFIG,
    DATASET,
    MANIFEST,
    RESULTS,
    evaluate_router_pareto,
)


ROOT = Path(__file__).resolve().parents[1]
RESULT_FILE = ROOT / "eval/results/router_pareto.json"


@pytest.fixture
def result():
    return evaluate_router_pareto()


@pytest.fixture
def source_copy(tmp_path):
    """Copy only the frozen inputs, never the raw OSHA data."""
    for name in (DATASET, MANIFEST, RESULTS, CONFIG):
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)

    return tmp_path


def test_saved_result_is_reproducible(result):
    saved = json.loads(RESULT_FILE.read_text())

    assert result == saved
    assert evaluate_router_pareto() == result


def test_source_fingerprints_match(result):
    for name, expected in result["source_sha256"].items():
        actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()

        assert actual == expected


def test_all_points_use_the_same_eligible_cases(result):
    assert result["total_reports"] == 50
    assert result["eligible_reports"] == 35
    assert result["excluded_reports"] == 15

    points = result["points"]

    assert [p["model"] for p in points] == ["offline", "gpt_nano", "claude", "router"]

    assert all(p["cases"] == 35 for p in points)


def test_individual_points_match_b7_evidence(result):
    original = json.loads((ROOT / RESULTS).read_text())

    for point in result["points"]:
        name = point["model"]

        if name == "router":
            continue

        measured = original["models"][name]

        assert point["hits"] == measured["strict_at_3_hits"]
        assert point["accuracy"] == measured["strict_at_3"]
        assert point["cost"] == measured["recorded_cost"]
        assert point["ci95"] == measured["strict_at_3_ci95"]


def test_router_uses_measured_models_in_both_modes(result):
    assert result["configured_models"] == ["claude", "gemini_flash", "gemma_local", "gpt_nano"]

    assert result["measured_models"] == ["claude", "gpt_nano"]

    assert result["unmeasured_models"] == ["gemini_flash", "gemma_local"]

    decisions = result["routing_decisions"]

    assert len(decisions) == 32

    assert Counter((row["mode"], row["selected_model"]) for row in decisions) == {
        ("lowest_cost", "claude"): 16,
        ("best_quality", "claude"): 16,
    }

    assert all(row["based_on_prior"] is False for row in decisions)


@pytest.mark.parametrize("mode", ["lowest_cost", "best_quality"])
def test_signal_grid_covers_every_difficulty(result, mode):
    decisions = [row for row in result["routing_decisions"] if row["mode"] == mode]

    assert Counter(row["difficulty"] for row in decisions) == {
        "simple": 1,
        "moderate": 4,
        "hard": 11,
    }

    combinations = {
        (
            row["signals"]["intake_confidence"],
            row["signals"]["disagreement"],
            row["signals"]["retrieval_margin"],
            row["signals"]["critic_rejected"],
        )
        for row in decisions
    }

    assert len(combinations) == 16


def test_router_point_matches_selected_model(result):
    points = {point["model"]: point for point in result["points"]}

    selected = result["selected_model"]

    assert selected == "claude"

    replay = points["router"]
    measured = points[selected]

    assert replay["selected_model"] == selected

    for key in ("hits", "cases", "accuracy", "ci95", "cost"):
        assert replay[key] == measured[key]

    assert replay["hits"] == 22
    assert replay["accuracy"] == pytest.approx(22 / 35)
    assert replay["cost"] == pytest.approx(0.061832)


def test_replay_never_calls_a_backend(monkeypatch):
    """Fail immediately if evaluation attempts model inference."""

    def forbidden(*args, **kwargs):
        pytest.fail("B8 must not call a model backend")

    monkeypatch.setattr(Router, "call", forbidden)
    monkeypatch.setattr(OfflineBackend, "complete", forbidden)

    result = evaluate_router_pareto()

    assert result["additional_api_calls"] == 0
    assert result["additional_api_cost"] == 0


def test_router_rejects_changed_frozen_dataset(source_copy):
    path = source_copy / DATASET

    with path.open("ab") as handle:
        handle.write(b"\n")

    with pytest.raises(ValueError, match="checksum"):
        evaluate_router_pareto(source_copy)


def test_router_rejects_incomplete_evaluation(source_copy):
    path = source_copy / RESULTS
    data = json.loads(path.read_text())

    data["models"]["claude"]["status"] = "unavailable"
    path.write_text(json.dumps(data))

    with pytest.raises(ValueError, match="not complete"):
        evaluate_router_pareto(source_copy)


def test_router_rejects_duplicate_cases(source_copy):
    path = source_copy / RESULTS
    data = json.loads(path.read_text())

    cases = data["models"]["claude"]["per_case"]
    cases[-1] = cases[0].copy()

    path.write_text(json.dumps(data))

    with pytest.raises(ValueError, match="duplicate"):
        evaluate_router_pareto(source_copy)


def test_router_rejects_changed_reference_labels(source_copy):
    path = source_copy / RESULTS
    data = json.loads(path.read_text())

    data["models"]["claude"]["per_case"][0]["primary"] = "1910.999"

    path.write_text(json.dumps(data))

    with pytest.raises(ValueError, match="reference labels"):
        evaluate_router_pareto(source_copy)


def test_router_rejects_inconsistent_accuracy(source_copy):
    path = source_copy / RESULTS
    data = json.loads(path.read_text())

    data["models"]["claude"]["strict_at_3"] = 0.99
    path.write_text(json.dumps(data))

    with pytest.raises(ValueError, match="stored accuracy"):
        evaluate_router_pareto(source_copy)


def test_router_rejects_negative_cost(source_copy):
    path = source_copy / RESULTS
    data = json.loads(path.read_text())

    data["models"]["claude"]["recorded_cost"] = -1
    path.write_text(json.dumps(data))

    with pytest.raises(ValueError, match="historical evaluation cost"):
        evaluate_router_pareto(source_copy)


def test_router_rejects_unconfirmed_cost(source_copy):
    path = source_copy / RESULTS
    data = json.loads(path.read_text())

    data["models"]["claude"]["price_confirmed"] = False
    path.write_text(json.dumps(data))

    with pytest.raises(ValueError, match="not confirmed"):
        evaluate_router_pareto(source_copy)


def test_frontier_keeps_three_unique_coordinates(result):
    points = result["points"]

    frontier = pareto_front(points)

    actual = {(p["cost"], p["accuracy"]) for p in frontier}

    expected = {(p["cost"], p["accuracy"]) for p in points if p["model"] != "router"}

    assert len(frontier) == 3
    assert actual == expected


def test_router_chart_is_valid_png(result):
    png = router_pareto_chart(result["points"])

    assert png.startswith(b"\x89PNG")

    with Image.open(io.BytesIO(png)) as image:
        assert image.format == "PNG"
        assert image.size == (1350, 720)
        image.verify()


def test_router_evaluation_view_reads_saved_results():
    image, table, note = views.router_evaluation()

    assert image is not None
    assert len(table) == 4

    assert table["Hits"].tolist() == ["12/35", "17/35", "22/35", "22/35"]

    assert table["Historical cost (USD)"].tolist() == [
        "$0.00000",
        "$0.03328",
        "$0.06183",
        "$0.06183",
    ]

    assert "35 eligible of 50 reports" in note
    assert "32 synthetic" in note
    assert "not an independent test" in note
    assert "no new model calls" in note


def test_router_evaluation_handles_missing_results(tmp_path, monkeypatch):
    monkeypatch.setattr(views, "RESULTS_DIR", tmp_path)

    image, table, note = views.router_evaluation()

    assert image is None
    assert table.empty
    assert "eval_router_pareto.py" in note
