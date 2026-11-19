"""Scores against ground truth: standards retrieval on the answer key, and the event baseline
on the 2025 holdout, including how well its recoding of pre 2024 reports matches OIICS 3."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import math
from pathlib import Path

import pandas as pd

from safereport.baseline import EventBaseline, accuracy_by_level, coverage_curve
from safereport.config import PROJECT_ROOT
from safereport.data import ReportStore
from safereport.retrieval import IndexRegistry, dense_ready
from safereport.schemas import AnswerKeyCase


@dataclass
class RetrievalScores:
    cases: int
    strict_at_1: float
    strict_at_3: float
    lenient_at_1: float
    lenient_at_3: float
    per_case: pd.DataFrame

    def as_dict(self) -> dict[str, object]:
        rates = {
            "strict_at_1": self.strict_at_1,
            "strict_at_3": self.strict_at_3,
            "lenient_at_1": self.lenient_at_1,
            "lenient_at_3": self.lenient_at_3,
        }
        result: dict[str, object] = {"cases": self.cases}
        for name, rate in rates.items():
            result[name] = round(float(rate), 3)
            result[f"{name}_ci95"] = wilson(float(rate), self.cases)
        return result


def wilson(rate: float, n: int, z: float = 1.96) -> list[float]:
    """The 95% Wilson interval of a rate over `n` cases; with about 50 cases it spans 27 points."""
    if n == 0:
        return [0.0, 0.0]
    centre = (rate + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(rate * (1 - rate) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3)]


def query_for(case: AnswerKeyCase, with_codes: bool = True) -> str:
    """The narrative, plus OSHA's event and source titles, which every report carries."""
    return f"{case.narrative} {case.event} {case.source}" if with_codes else case.narrative


def score_retrieval(
    registry: IndexRegistry,
    key: list[AnswerKeyCase],
    with_codes: bool = True,
    terms_for: Callable[[AnswerKeyCase], list[str]] | None = None,
) -> RetrievalScores:
    """Hit rates at 1 and 3 by CFR section, on the cases that have a standard.

    Strict counts only the primary section; lenient also accepts the secondary one.
    """
    rows = []
    for case in key:
        if not case.has_standard:
            continue
        # Every case in the key is a manufacturing report, so Part 1910 applies.
        terms = terms_for(case) if terms_for else []
        found = [
            s.section
            for s in registry.search(query_for(case, with_codes), naics="31", k=3, terms=terms).sections
        ]
        rows.append(
            {
                "case": case.case,
                "primary": case.primary_section,
                "found": ";".join(found),
                "strict_at_1": found[:1] == [case.primary_section],
                "strict_at_3": case.primary_section in found[:3],
                "lenient_at_1": bool(set(found[:1]) & set(case.accepted_sections)),
                "lenient_at_3": bool(set(found[:3]) & set(case.accepted_sections)),
            }
        )
    frame = pd.DataFrame(rows)
    return RetrievalScores(
        cases=len(frame),
        strict_at_1=frame["strict_at_1"].mean(),
        strict_at_3=frame["strict_at_3"].mean(),
        lenient_at_1=frame["lenient_at_1"].mean(),
        lenient_at_3=frame["lenient_at_3"].mean(),
        per_case=frame,
    )


RESULTS_DIR = PROJECT_ROOT / "eval" / "results"


def score_event_baseline(store: ReportStore, baseline: EventBaseline) -> dict:
    """Holdout accuracy by code level, and accuracy against the share coded automatically."""
    holdout = store.frame("SELECT narrative, event_code FROM reports WHERE split = 'holdout'")
    predictions = baseline.predict(holdout["narrative"].tolist())
    actual = holdout["event_code"].tolist()
    curve = coverage_curve(predictions, actual, [0.0, 0.3, 0.5, 0.7, 0.9])
    accuracy = accuracy_by_level([p.code for p in predictions], actual)
    return {
        "holdout_reports": len(holdout),
        "accuracy": {k: round(v, 3) for k, v in accuracy.items()},
        "accuracy_ci95": {k: wilson(v, len(holdout)) for k, v in accuracy.items()},
        "coverage_curve": curve.round(3).to_dict("records"),
    }


def recode_check(store: ReportStore) -> dict:
    """How far the recoded 2023 event groups are from the real 2024 ones (total variation).

    For scale, the same distance between the real 2024 and 2025 groups is reported too.
    """
    groups = store.frame(
        "SELECT year, left(event_code_v3, 2) AS grp, count(*) AS n FROM reports "
        "WHERE year IN (2023, 2024, 2025) AND event_code_v3 IS NOT NULL GROUP BY year, grp"
    )
    shares = groups.pivot_table(index="grp", columns="year", values="n", fill_value=0)
    shares = shares / shares.sum()

    def distance(a: int, b: int) -> float:
        return round(float((shares[a] - shares[b]).abs().sum() / 2), 3)

    return {"recoded_2023_vs_real_2024": distance(2023, 2024), "real_2024_vs_real_2025": distance(2024, 2025)}


def write_phase1_results(dense: bool = True, out: Path = RESULTS_DIR) -> dict:
    """Run every Phase 1 baseline and write the numbers to eval/results."""
    from safereport.labels import load_answer_key  # imported here to keep the module light

    store = ReportStore()
    key = load_answer_key()
    results: dict = {
        "event_baseline": score_event_baseline(store, EventBaseline.load()),
        "oiics_recode": recode_check(store),
        "retrieval": {},
    }
    out.mkdir(parents=True, exist_ok=True)
    for name, use_dense in (("bm25", False), ("hybrid", True)):
        if use_dense and not dense:
            continue
        if use_dense and not dense_ready():
            results["retrieval"]["hybrid"] = "skipped: the embedding model is not cached on this machine"
            continue
        registry = IndexRegistry.load(dense=use_dense)
        for with_codes in (False, True):
            scores = score_retrieval(registry, key, with_codes=with_codes)
            label = f"{name}_{'narrative_and_codes' if with_codes else 'narrative_only'}"
            results["retrieval"][label] = scores.as_dict()
            scores.per_case.to_csv(out / f"retrieval_{label}.csv", index=False)
    (out / "phase1_baselines.json").write_text(json.dumps(results, indent=2))
    return results
