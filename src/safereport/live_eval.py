"""The live standards experiment: does a model's wording of the hazard help retrieval?

The answer key is the final test set, so nothing is tuned on it. The prompt is checked for
format on a few reports outside the key (`smoke`), then each model runs once over the key
(`score`); every reply is cached, so a second run costs nothing, and the team's budget caps the
paid calls.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import time

from safereport import offline
from safereport.backends import ModelError
from safereport.config import load_model_settings
from safereport.data import ReportStore
from safereport.evaluation import RESULTS_DIR, score_retrieval
from safereport.labels import load_answer_key
from safereport.providers import live_backends
from safereport.redaction import redact
from safereport.retrieval import IndexRegistry, dense_ready
from safereport.spend import SpendLedger, guarded


def _backend(model: str, ledger: SpendLedger):
    settings = load_model_settings()
    backends = guarded(live_backends(settings), settings, ledger)
    if model not in backends:
        raise SystemExit(f"{model} has no key or server here; available: {sorted(backends)}")
    return backends[model]


def _terms(backend, narrative: str, *, attempts: int = 4) -> list[str]:
    if attempts < 1:
        raise ValueError("At least one attempt is required")
    material = offline.intake({"report_id": "x", "narrative": narrative})["material"]
    prompt = json.dumps({"narrative": redact(narrative).text, "material": material})
    for attempt in range(attempts):
        try:
            reply = backend.complete("standards_terms", prompt)
            break
        except ModelError as error:
            # A busy provider answers 5xx or 429 now and then; this experiment wants this model's
            # answer, so it waits and asks again instead of falling back to another model.
            if error.kind not in ("server_error", "rate_limit") or attempt == attempts - 1:
                raise
            time.sleep(2 * (attempt + 1))
    return [str(t) for t in (reply.data or {}).get("terms", [])][:8]


def smoke(model: str, count: int = 5) -> list[dict]:
    """Terms for a few 2025 reports that are in neither the answer key nor the holdout."""
    ledger = SpendLedger()
    backend = _backend(model, ledger)
    key_ids = [c.sir_id for c in load_answer_key()]
    rows = ReportStore().frame(
        "SELECT id, narrative FROM reports WHERE split = 'recent' AND NOT list_contains(?, id) ORDER BY id LIMIT ?",
        [key_ids, count],
    )
    return [
        {"id": r.id, "narrative": r.narrative[:160], "terms": _terms(backend, r.narrative)}
        for r in rows.itertuples()
    ]


def score(model: str, out: Path = RESULTS_DIR) -> dict:
    """One run of the model's terms over the answer key, scored like the baselines."""
    ledger = SpendLedger()
    backend = _backend(model, ledger)
    registry = IndexRegistry.load(dense=dense_ready())
    key = load_answer_key()
    terms: dict[str, list[str]] = {}

    def terms_for(case):
        terms[case.case] = _terms(backend, case.narrative)
        return terms[case.case]

    scores = score_retrieval(registry, key, with_codes=True, terms_for=terms_for)
    result = {
        "model": model,
        "retrieval": "hybrid" if dense_ready() else "bm25",
        "scores": scores.as_dict(),
        "spend": ledger.summary(),
        "spent_total": round(ledger.spent(), 4),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / f"live_terms_{model}.json").write_text(json.dumps({**result, "terms": terms}, indent=2))
    scores.per_case.to_csv(out / f"live_terms_{model}.csv", index=False)
    return result


def mcnemar_exact(gained: int, lost: int) -> float:
    """Two sided exact McNemar p value: the cases one setup gets and the other misses."""
    n = gained + lost
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(gained, lost) + 1)) / 2**n
    return min(1.0, 2 * tail)


def summary(out: Path = RESULTS_DIR, baseline: str = "retrieval_hybrid_narrative_and_codes") -> dict:
    """Every scored model against the retrieval baseline, case by case on the same answer key."""
    import pandas as pd

    base = pd.read_csv(out / f"{baseline}.csv").set_index("case")
    rows = {}
    for path in sorted(out.glob("live_terms_*.csv")):
        model = path.stem.removeprefix("live_terms_")
        if model == "summary":
            continue
        run = pd.read_csv(path).set_index("case").loc[base.index]
        result = json.loads((out / f"live_terms_{model}.json").read_text())
        rows[model] = {"cases": len(run)}
        for column in ("strict_at_1", "strict_at_3", "lenient_at_3"):
            gained = int((~base[column] & run[column]).sum())
            lost = int((base[column] & ~run[column]).sum())
            rows[model][column] = {
                "baseline": int(base[column].sum()), "with_terms": int(run[column].sum()),
                "rate": result["scores"][column], "ci95": result["scores"][f"{column}_ci95"],
                "gained": gained, "lost": lost, "mcnemar_p": round(mcnemar_exact(gained, lost), 4),
            }  # fmt: skip
    report = {"baseline": baseline, "models": rows}
    (out / "live_terms_summary.json").write_text(json.dumps(report, indent=2))
    return report
