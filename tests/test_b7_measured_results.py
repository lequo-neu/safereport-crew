"""Check B7 routing values against recorded evaluation evidence."""

import hashlib
import json
from pathlib import Path

from safereport.config import load_model_settings
from safereport.router import offline_router


ROOT = Path(__file__).resolve().parents[1]


def test_measured_accuracy_matches_b7_results():
    settings = load_model_settings()
    router = offline_router(settings, {})

    model = settings.model("gpt_nano")
    assert model.measured_source == "eval/results/router_slice.json"

    report = json.loads((ROOT / model.measured_source).read_text())

    result = report["models"]["gpt_nano"]

    assert result["status"] == "complete"
    assert result["eligible_reports"] == 35
    assert result["strict_at_3_hits"] == 17

    expected = 17 / 35

    assert result["strict_at_3"] == expected
    assert router.accuracy(model, "retrieve") == (expected, False)

    for step in ("code", "decide", "write"):
        assert router.accuracy(model, step) == (model.prior[step], True)


def test_unavailable_models_keep_unmeasured_priors():
    settings = load_model_settings()
    router = offline_router(settings, {})

    for name in ("claude", "gemini_flash", "gemma_local"):
        model = settings.model(name)
        assert not model.measured

        for step in ("code", "retrieve", "decide", "write"):
            assert router.accuracy(model, step) == (model.prior[step], True)


def test_frozen_b7_labels_unchanged():
    manifest = json.loads((ROOT / "data/labels/router_slice_manifest.json").read_text())

    dataset = ROOT / manifest["dataset"]
    digest = hashlib.sha256(dataset.read_bytes()).hexdigest()

    assert digest == manifest["sha256"]
    assert manifest["total_reports"] == 50
    assert manifest["eligible_reports"] == 35
    assert manifest["excluded_no_standard"] == 15


def test_paired_comparison_reconciles():
    report = json.loads((ROOT / "eval/results/router_slice.json").read_text())

    comparison = report["paired_comparisons"]["gpt_nano_vs_offline"]

    assert len(comparison["gained"]) == 5
    assert len(comparison["lost"]) == 0
    assert len(comparison["both_correct"]) == 12
    assert len(comparison["both_wrong"]) == 18
    assert comparison["paired_cases"] == 35
    assert comparison["mcnemar_exact_p"] == 0.0625
