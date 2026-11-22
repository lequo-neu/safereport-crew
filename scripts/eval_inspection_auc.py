"""Inspection priority against OSHA's own choices: ROC AUC on the 2025 holdout (task B2, issue #3).

Usage:
    python -I scripts/eval_inspection_auc.py [--no-dense] [--out eval/results/inspection_auc.json]

Needs the built data, indexes and event baseline (README quick start). No model is called.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from safereport.inspection_eval import RESULTS_DIR, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-dense", action="store_true", help="BM25 only, without embeddings")
    parser.add_argument("--out", type=Path, default=RESULTS_DIR / "inspection_auc.json")
    args = parser.parse_args(argv)
    result = run(dense=not args.no_dense, out=args.out)
    print(json.dumps({k: result[k] for k in ("reports", "class_balance", "all_reports")}, indent=2))
    print(f"Written to {args.out} and {args.out.with_suffix('.csv').name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
