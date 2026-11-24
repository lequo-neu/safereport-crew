"""Replay the retrieval router using the completed B7 evaluations."""

from __future__ import annotations

import json

from safereport.config import PROJECT_ROOT
from safereport.router_pareto import evaluate_router_pareto


RESULT_FILE = PROJECT_ROOT / "eval/results/router_pareto.json"


def main():
    result = evaluate_router_pareto()

    RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)

    temporary = RESULT_FILE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(RESULT_FILE)

    print("Router cost and accuracy comparison")
    print(f"Eligible reports: {result['eligible_reports']}")
    print(f"Selected model: {result['selected_model']}")
    print(f"Routing decisions: {len(result['routing_decisions'])}")
    print()

    print(f"{'Method':24s} {'Hits':>7s} {'Hit@3':>10s} {'Cost (USD)':>14s}")
    print("-" * 60)

    for point in result["points"]:
        hits = f"{point['hits']}/{point['cases']}"

        print(f"{point['label']:24s} {hits:>7s} {point['accuracy']:>10.2%} {point['cost']:>14.8f}")

    print()
    print("Additional API calls:", result["additional_api_calls"])
    print("Additional API cost:", result["additional_api_cost"])
    print("Saved:", RESULT_FILE.relative_to(PROJECT_ROOT))


if __name__ == "__main__":
    main()
