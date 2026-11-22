"""What the two stage batch saves on the Texas week (task B4, issue #5).

Usage:
    python -I scripts/eval_batch_savings.py [--no-dense] [--out eval/results/batch_savings.json]

Needs the built data, indexes and event baseline (README quick start). Offline: no model is
called and nothing is paid.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from safereport.batch_eval import RESULTS_DIR, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-dense", action="store_true", help="BM25 only, without embeddings")
    parser.add_argument("--out", type=Path, default=RESULTS_DIR / "batch_savings.json")
    args = parser.parse_args(argv)
    result = run(dense=not args.no_dense, out=args.out)
    print(json.dumps({k: result[k] for k in ("saving", "changes")}, indent=2))
    print(f"Written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
