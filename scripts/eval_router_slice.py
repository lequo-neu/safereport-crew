"""Evaluate model-assisted retrieval on the frozen B7 reference slice."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json

from safereport.backends import ModelError
from safereport.config import load_model_settings
from safereport.evaluation import RESULTS_DIR
from safereport.live_eval import _terms
from safereport.providers import live_backends
from safereport.retrieval import IndexRegistry, dense_ready
from safereport.router_slice import (
    SLICE_FILE,
    evaluate_slice,
    load_router_slice,
)
from safereport.spend import (
    BUDGET_USD,
    BudgetExceededError,
    SpendLedger,
    guarded,
)


EXPECTED_SHA256 = "6a263fbc8ef1055cbd141659555a3660f197896870e380cbad01ae1a45ec20ed"

MODELS = ("gpt_nano", "claude", "gemini_flash")
RESULT_FILE = RESULTS_DIR / "router_slice.json"


def frozen_cases():
    """Reject any change to the reference labels."""
    digest = hashlib.sha256(SLICE_FILE.read_bytes()).hexdigest()

    if digest != EXPECTED_SHA256:
        raise ValueError("Frozen B7 fingerprint mismatch")

    cases = load_router_slice()

    if len(cases) != 50 or sum(c.has_standard for c in cases) != 35:
        raise ValueError("Unexpected B7 evaluation denominator")

    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        required=True,
        choices=("offline", *MODELS),
    )
    parser.add_argument(
        "--previous-team-spend",
        type=float,
        default=None,
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Explicitly authorize paid model requests",
    )
    args = parser.parse_args()

    cases = frozen_cases()

    if not dense_ready():
        raise RuntimeError("B7 requires the hybrid retrieval index")

    registry = IndexRegistry.load(dense=True)

    if RESULT_FILE.exists():
        report = json.loads(RESULT_FILE.read_text())

        if report["dataset_sha256"] != EXPECTED_SHA256:
            raise ValueError("Existing result uses different labels")
    else:
        report = {
            "dataset_sha256": EXPECTED_SHA256,
            "total_reports": 50,
            "eligible_reports": 35,
            "excluded_no_standard": 15,
            "retrieval": "hybrid",
            "models": {},
        }

    if report["models"].get(args.model, {}).get("status") == "complete":
        print("Completed result already exists. No new calls.")
        return

    if args.model == "offline":
        result = evaluate_slice(registry, cases)
        result.update(
            {
                "status": "complete",
                "model": "offline",
                "recorded_cost": 0.0,
            }
        )
    else:
        if not args.live:
            parser.error("Live evaluation requires --live")

        prior = args.previous_team_spend

        if prior is None or not 0 <= prior < BUDGET_USD:
            parser.error("Provide confirmed previous team spending")

        ledger = SpendLedger()
        settings = load_model_settings()
        backends = live_backends(settings)
        before = ledger.spent()

        # Reserve a buffer because the existing ledger charges
        # requests after they complete.
        local_cap = BUDGET_USD - prior - 0.10

        if before >= local_cap:
            raise BudgetExceededError("Insufficient remaining budget")

        result = {
            "model": args.model,
            "model_id": settings.model(args.model).model_id,
            "status": "unavailable",
            "previous_team_spend": prior,
            "local_budget_cap": local_cap,
        }

        if args.model not in backends:
            result["reason"] = "Missing credentials or backend"
        else:
            inner = backends[args.model]

            if args.model == "gemini_flash":
                from google import genai
                from google.genai import types

                from safereport.providers import REQUEST_TIMEOUT

                inner.client = genai.Client(
                    http_options=types.HttpOptions(
                        timeout=int(REQUEST_TIMEOUT * 1000),
                        retry_options=types.HttpRetryOptions(attempts=1),
                    )
                )

            backend = guarded(
                {args.model: inner},
                settings,
                ledger,
                budget=local_cap,
            )[args.model]

            terms = {}

            def terms_for(case):
                print(
                    f"{args.model}: {case.case} ({len(terms) + 1}/35)",
                    flush=True,
                )
                terms[case.case] = _terms(
                    backend,
                    case.narrative,
                    attempts=2 if args.model == "gemini_flash" else 4,
                )
                return terms[case.case]

            try:
                scores = evaluate_slice(
                    registry,
                    cases,
                    terms_for=terms_for,
                )
                result.update(scores)
                result["status"] = "complete"

            except ModelError as error:
                result["reason"] = error.kind
                result["completed_cases"] = len(terms)

            except BudgetExceededError:
                result["status"] = "budget_stopped"
                result["completed_cases"] = len(terms)

            result["terms"] = terms

        result["recorded_cost"] = round(ledger.spent() - before, 8)
        result["spend_ledger"] = ledger.summary()
        result["local_spent_total"] = ledger.spent()
        result["estimated_team_spent"] = prior + ledger.spent()
        result["price_confirmed"] = settings.model(args.model).prices is not None

    result["evaluated_at"] = datetime.now(UTC).isoformat()
    report["models"][args.model] = result

    RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)

    temporary = RESULT_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    temporary.replace(RESULT_FILE)

    print(
        json.dumps(
            {key: value for key, value in result.items() if key not in {"per_case", "terms"}}, indent=2
        )
    )

    print("Saved:", RESULT_FILE)


if __name__ == "__main__":
    main()
