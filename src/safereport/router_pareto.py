"""Replay the retrieval router against the completed B7 evaluations.

The replay uses stored retrieval outcomes and historical evaluation costs.
It exercises the production routing policy without calling any model.
"""

from __future__ import annotations

import csv
import hashlib
from itertools import product
import json
import math
from pathlib import Path

from safereport.config import PROJECT_ROOT, load_model_settings
from safereport.router import Signals, difficulty, offline_router


DATASET = "data/labels/router_slice.csv"
MANIFEST = "data/labels/router_slice_manifest.json"
RESULTS = "eval/results/router_slice.json"
CONFIG = "config/models.toml"

FROZEN_SHA256 = "6a263fbc8ef1055cbd141659555a3660f197896870e380cbad01ae1a45ec20ed"

COMPLETED_MODELS = ("offline", "gpt_nano", "claude")
MODES = ("lowest_cost", "best_quality")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _wilson(hits: int, total: int) -> tuple[float, float]:
    """Wilson 95% interval for a binomial proportion."""
    z = 1.959963984540054
    share = hits / total
    denominator = 1 + z**2 / total
    center = (share + z**2 / (2 * total)) / denominator
    margin = z * math.sqrt(share * (1 - share) / total + z**2 / (4 * total**2)) / denominator
    return center - margin, center + margin


def evaluate_router_pareto(root: Path = PROJECT_ROOT) -> dict:
    """Build a reproducible comparison from the frozen B7 evidence."""
    manifest = json.loads((root / MANIFEST).read_text())
    results = json.loads((root / RESULTS).read_text())
    settings = load_model_settings(root / CONFIG)

    hashes = {name: _sha256(root / name) for name in (DATASET, MANIFEST, RESULTS, CONFIG)}

    _require(
        hashes[DATASET] == manifest["sha256"] == results["dataset_sha256"] == FROZEN_SHA256,
        "B7 dataset checksum does not match the frozen dataset",
    )

    _require(
        manifest["dataset"] == DATASET,
        "Unexpected dataset in the B7 manifest",
    )

    with (root / DATASET).open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    _require(
        len(rows) == 50,
        "Expected 50 frozen B7 reports",
    )

    _require(
        len({row["case"] for row in rows}) == len(rows),
        "Duplicate case IDs in the frozen B7 dataset",
    )

    labels = {row["case"]: row["primary_section"].strip() for row in rows if row["primary_section"].strip()}

    eligible = len(labels)
    excluded = len(rows) - eligible

    _require(
        (eligible, excluded) == (35, 15),
        "Unexpected eligible and excluded report counts",
    )

    for source in (manifest, results):
        _require(
            source["total_reports"] == len(rows)
            and source["eligible_reports"] == eligible
            and source["excluded_no_standard"] == excluded,
            "B7 metadata counts do not match the dataset",
        )

    _require(
        results["retrieval"] == "hybrid",
        "B7 results must use the hybrid retrieval index",
    )

    points = []

    for name in COMPLETED_MODELS:
        model = results["models"][name]

        _require(
            model["status"] == "complete",
            f"{name}: evaluation is not complete",
        )

        _require(
            model["total_reports"] == len(rows)
            and model["eligible_reports"] == eligible
            and model["excluded_no_standard"] == excluded,
            f"{name}: evaluation counts do not match B7",
        )

        cases = model["per_case"]
        case_labels = {case["case"]: case["primary"] for case in cases}

        _require(
            len(cases) == len(case_labels) == eligible,
            f"{name}: missing or duplicate evaluated cases",
        )

        _require(
            case_labels == labels,
            f"{name}: reference labels do not match the frozen CSV",
        )

        for case in cases:
            _require(
                type(case["strict_at_3"]) is bool,
                f"{name}: strict Hit@3 must be Boolean",
            )

        hits = sum(case["strict_at_3"] for case in cases)
        accuracy = hits / eligible

        _require(
            hits == model["strict_at_3_hits"] and math.isclose(accuracy, model["strict_at_3"], abs_tol=1e-12),
            f"{name}: stored accuracy does not match case outcomes",
        )

        ci95 = model["strict_at_3_ci95"]
        expected_ci = _wilson(hits, eligible)

        _require(
            len(ci95) == 2
            and all(
                math.isclose(saved, expected, abs_tol=0.00051)
                for saved, expected in zip(ci95, expected_ci, strict=True)
            ),
            f"{name}: invalid Wilson confidence interval",
        )

        cost = model["recorded_cost"]

        _require(
            type(cost) in (int, float) and math.isfinite(cost) and cost >= 0,
            f"{name}: invalid historical evaluation cost",
        )

        if name == "offline":
            _require(cost == 0, "Offline evaluation must cost zero")
            label = "Offline hybrid"
        else:
            spec = settings.model(name)

            _require(
                model["price_confirmed"] is True and spec.prices is not None,
                f"{name}: historical cost is not confirmed",
            )

            _require(
                model["model_id"] == spec.model_id,
                f"{name}: configured model ID differs from B7",
            )

            _require(
                spec.measured_source == RESULTS
                and "retrieve" in spec.measured
                and math.isclose(
                    spec.measured["retrieve"],
                    accuracy,
                    abs_tol=1e-12,
                ),
                f"{name}: configured accuracy differs from B7",
            )

            label = spec.label

        points.append(
            {
                "model": name,
                "label": label,
                "cases": eligible,
                "hits": hits,
                "accuracy": accuracy,
                "ci95": ci95,
                "cost": cost,
            }
        )

    router = offline_router(settings, {})
    configured = {spec.name for spec in settings.models}

    _require(
        set(router.backends) == configured,
        "Offline router must register every configured backend",
    )

    measured_models = {spec.name for spec in settings.models if "retrieve" in spec.measured}

    _require(
        measured_models == set(COMPLETED_MODELS) - {"offline"},
        "Measured retrieval models differ from completed B7 runs",
    )

    decisions = []

    for mode in MODES:
        for confidence, disagreement, margin, rejected in product(
            (0.4, 0.9),
            (False, True),
            (0.01, 0.10),
            (False, True),
        ):
            signals = Signals(
                intake_confidence=confidence,
                disagreement=disagreement,
                retrieval_margin=margin,
                critic_rejected=rejected,
            )

            choice = router.choose("retrieve", signals, mode)

            _require(
                not choice.based_on_prior,
                "Retrieval replay selected an unmeasured prior",
            )

            decisions.append(
                {
                    "mode": mode,
                    "signals": {
                        "intake_confidence": confidence,
                        "disagreement": disagreement,
                        "retrieval_margin": margin,
                        "critic_rejected": rejected,
                    },
                    "difficulty": difficulty(signals, settings),
                    "selected_model": choice.model.name,
                    "based_on_prior": choice.based_on_prior,
                    "reason": choice.reason,
                }
            )

    selected = {row["selected_model"] for row in decisions}

    _require(
        len(selected) == 1,
        "Router selection varies by signals or mode; a mixed replay requires real per-case signals and costs",
    )

    selected_model = next(iter(selected))

    _require(
        selected_model in measured_models,
        "Router selected a model without completed B7 results",
    )

    selected_point = next(point for point in points if point["model"] == selected_model)

    points.append(
        {
            **selected_point,
            "model": "router",
            "label": "Router replay",
            "selected_model": selected_model,
        }
    )

    return {
        "method": "retrospective invariant-selection replay",
        "measure": "strict standards retrieval Hit@3",
        "total_reports": len(rows),
        "eligible_reports": eligible,
        "excluded_reports": excluded,
        "source_sha256": hashes,
        "configured_models": sorted(configured),
        "measured_models": sorted(measured_models),
        "unmeasured_models": sorted(configured - measured_models),
        "accuracy_bars": dict(settings.router.bar),
        "routing_decisions": decisions,
        "selected_model": selected_model,
        "points": points,
        "additional_api_calls": 0,
        "additional_api_cost": 0.0,
        "limitations": [
            "Retrospective replay on the same B7 slice used to populate measured routing accuracies.",
            "Not an independent evaluation of router generalization.",
            "Synthetic uncertainty combinations are not observed per-report signals.",
            "Historical evaluation costs are reused; no new inference is performed.",
            "Only standards retrieval Hit@3 is evaluated, not end-to-end decision accuracy.",
            "Provider failures, retries, availability, latency and private mode are outside the replay.",
            "Unmeasured Gemini and Gemma are excluded from the cost-accuracy points.",
            "Claude's result is for the configured backend; server-side fallback may be enabled.",
        ],
    }
