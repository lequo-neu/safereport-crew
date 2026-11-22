"""Inspection priority against OSHA's own choices: ROC AUC on the 2025 holdout (task B2, issue #3).

Each report of the 2025 holdout gets the score the crew gives it in stage 1 of the weekly list,
offline and with no model: Category 1 first, then the Category 2 priority. The score is set
beside "severity alone" (amputation, loss of an eye, the people hospitalized), and both are
compared with whether OSHA opened an inspection. OSHA's choices reflect its own staffing and
past practice, so the AUC says how far the crew ranks like past practice, not whether an
inspection was needed.

Nothing is fitted here: the weights are read from config/triage.toml as they are, and the
inspection column is blanked before a report is scored, so the score never sees the outcome.

Run it with `python -I scripts/eval_inspection_auc.py` (add `--no-dense` for BM25 retrieval
only). It writes eval/results/inspection_auc.json and, report by report, inspection_auc.csv.
"""

from __future__ import annotations

from collections.abc import Sequence
import hashlib
import json
import math
from pathlib import Path
import tomllib
from typing import Any

import numpy as np
import pandas as pd

from safereport import offline
from safereport.config import PROJECT_ROOT
from safereport.evaluation import wilson
from safereport.schemas import IntakeResult, Report
from safereport.triage import DEFAULT_WEIGHTS, TRIAGE_FILE, category_one, priority


RESULTS_DIR = PROJECT_ROOT / "eval" / "results"
# Above any Category 2 priority (the weights add up to about 16), so Category 1 ranks first.
CATEGORY_ONE_RANK = 100.0
Z95 = 1.959964

# What the AUC does not say, written into the result file.
LIMITATIONS = [
    "OSHA's choices reflect its staffing, area office practice and the reports' timing, so the AUC measures agreement with past practice, not whether an inspection was needed.",
    "The score is stage 1 only (offline rules, no model); a stage 2 model branch can change a report's facts and so its priority.",
    "The crew plans inspections within inspector days by an integer program; the AUC ranks reports by score and ignores the days an inspection takes.",
    "Imminent danger and repeat offenders (SVEP) are not in the score: a person flags the first, and the data cannot show the second.",
    "The priority factors were chosen with inspection rates the proposal quotes for all reports from 2015 to 2025, the holdout included; no weight was fitted to them.",
    "Late 2025 reports may not have their inspection recorded yet; see the rate by quarter.",
    "Federal OSHA states only; most State Plan states are missing.",
    "Ranking Category 1 first lowers the AUC below the priority alone, because OSHA inspected many Category 1 reports less often than the rule implies; the employer history criterion (a confirmed similar report within 12 months) is inspected below the overall rate (see category_one.by_criterion). This is a finding about agreement with past practice; the rules were not changed for it.",
]


# ---- The scores ----


def severity(report: Report, weights: dict[str, float] = DEFAULT_WEIGHTS) -> float:
    """Severity alone: the injury fields of the priority, with the same weights, and nothing else."""
    return float(
        weights["amputation"] * (report.amputation > 0)
        + weights["loss_of_eye"] * (report.loss_of_eye > 0)
        + weights["hospitalized"] * min(report.hospitalized, 2)
    )


def industry_share(store, report: Report) -> float:
    """As the Analyst computes it in stage 1 (graph.py): the hazard's share of the industry's reports."""
    group = (report.event_code if report.event_date.year >= 2024 else "")[:2]
    if not group:
        return 0.0
    rows = store.frame(
        "SELECT avg(CASE WHEN starts_with(event_code_v3, ?) THEN 1.0 ELSE 0.0 END) AS share FROM reports "
        "WHERE starts_with(naics, ?) AND year >= 2022",
        [group, report.naics[:3]],
    )
    value = rows["share"].iloc[0]
    return float(value) if pd.notna(value) else 0.0


def score_reports(services, rows: pd.DataFrame) -> pd.DataFrame:
    """Stage 1 of the weekly list for each row, as `triage_stage1` in graph.py does it, offline.

    A test checks this against the graph, so the two cannot drift apart unnoticed.
    """
    records = rows.to_dict("records")
    predictions = services.baseline.predict([r["narrative"] for r in records]) if records else []
    out = []
    for row, predicted in zip(records, predictions, strict=True):
        fields = {name: row[name] for name in Report.model_fields if name in row}
        # The outcome is blanked, so no part of the score can read it.
        report = Report(**{**fields, "inspection": ""})
        facts = IntakeResult.model_validate(
            offline.intake(
                {
                    "report_id": report.id,
                    "narrative": report.narrative,
                    "event_title": report.event_title,
                    "nature_title": report.nature_title,
                    "baseline_code": predicted.code,
                    "baseline_confidence": predicted.confidence,
                }
            )
        )
        found = services.registry.search(f"{report.narrative} {report.event_title}", naics=report.naics, k=3)
        division = str(row.get("event_code_v3") or report.event_code)[:1]
        repeats = [
            m.report_id
            for m in services.employers(report.state).repeats_within(
                report.employer, report.state, report.event_date, division=division, city=report.city,
                zip_code=report.zip, naics=report.naics, exclude_id=report.id,
            )
        ]  # fmt: skip
        emphasis = [h.document.citation for h in found.emphasis if h.document.verified]
        possible = [h.document.citation for h in found.emphasis if not h.document.verified]
        score, _parts = priority(
            report, facts, bool(found.sections), industry_share(services.store, report),
            possible_emphasis=bool(possible),
        )  # fmt: skip
        triggers = category_one(report, emphasis, repeats)
        out.append(
            {
                "id": report.id,
                "event_date": report.event_date.isoformat(),
                "state": report.state,
                "category_one": bool(triggers),
                "category_one_criteria": "; ".join(dict.fromkeys(t.criterion for t in triggers)),
                "priority": score,
                "crew_score": score + CATEGORY_ONE_RANK * bool(triggers),
                "severity": severity(report),
            }
        )
    return pd.DataFrame(out)


# ---- ROC AUC with DeLong's interval ----


def _midranks(values: np.ndarray) -> np.ndarray:
    return pd.Series(values).rank(method="average").to_numpy()


def delong(scores: Sequence[Sequence[float]], labels: Sequence[bool]) -> tuple[np.ndarray, np.ndarray]:
    """The AUC of each score and their covariance, by DeLong's method (Sun and Xu's fast form).

    Ties count half, as in the usual AUC. The covariance gives each AUC its interval and, for two
    scores on the same reports, the interval of their difference.
    """
    y = np.asarray(labels, dtype=bool)
    m, n = int(y.sum()), int((~y).sum())
    if m == 0 or n == 0:
        raise ValueError("the AUC needs at least one inspected and one not inspected report")
    x = np.asarray(scores, dtype=float).reshape(len(scores), -1)
    aucs, v01, v10 = [], [], []
    for row in x:
        pos, neg = row[y], row[~y]
        tz = _midranks(np.concatenate([pos, neg]))
        tx, ty = _midranks(pos), _midranks(neg)
        aucs.append((tz[:m].sum() - m * (m + 1) / 2) / (m * n))
        v01.append((tz[:m] - tx) / n)
        v10.append(1.0 - (tz[m:] - ty) / m)
    s01 = np.atleast_2d(np.cov(np.array(v01))) if m > 1 else np.zeros((len(x), len(x)))
    s10 = np.atleast_2d(np.cov(np.array(v10))) if n > 1 else np.zeros((len(x), len(x)))
    return np.array(aucs), s01 / m + s10 / n


def _interval(value: float, variance: float, low: float, high: float) -> list[float]:
    half = Z95 * math.sqrt(max(variance, 0.0))
    return [round(max(low, value - half), 3), round(min(high, value + half), 3)]


def compare(
    named: dict[str, Sequence[float]], labels: Sequence[bool], first: str, second: str
) -> dict[str, Any]:
    """Each score's AUC with its 95% interval, and the paired difference of `first` minus `second`."""
    names = list(named)
    aucs, cov = delong([named[k] for k in names], labels)
    result: dict[str, Any] = {
        name: {"auc": round(float(aucs[i]), 3), "auc_ci95": _interval(aucs[i], cov[i, i], 0.0, 1.0)}
        for i, name in enumerate(names)
    }
    a, b = names.index(first), names.index(second)
    diff = float(aucs[a] - aucs[b])
    var = float(cov[a, a] + cov[b, b] - 2 * cov[a, b])
    p = math.erfc(abs(diff) / math.sqrt(2 * var)) if var > 0 else (1.0 if diff == 0 else 0.0)
    result[f"{first}_minus_{second}"] = {
        "auc_difference": round(diff, 3),
        "ci95": _interval(diff, var, -1.0, 1.0),
        "p_value": float(f"{p:.2g}"),
    }
    return result


# ---- The evaluation ----


def _rate(hits: int, cases: int) -> dict[str, Any]:
    rate = hits / cases if cases else 0.0
    return {"cases": cases, "inspected": hits, "rate": round(rate, 3), "rate_ci95": wilson(rate, cases)}


def _weights_file(path: Path = TRIAGE_FILE) -> str:
    """A fingerprint of the values in config/triage.toml, so a change of weights shows in the result file.

    Only the values count: a comment, the layout or a Windows line ending leaves it the same, so
    writing down why a weight is what it is does not read as a change of weights.
    """
    if not path.exists():
        return "built in"
    values = tomllib.loads(path.read_text(encoding="utf-8"))
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def evaluate(services, rows: pd.DataFrame, retrieval: str) -> tuple[dict[str, Any], pd.DataFrame]:
    """Score `rows` (reports with an `inspected` column) and compare the scores with OSHA's choices."""
    scored = score_reports(services, rows.drop(columns=["inspection", "inspected"], errors="ignore"))
    scored["inspected"] = rows["inspected"].astype(bool).to_numpy()
    return summarize(scored, retrieval), scored


def summarize(scored: pd.DataFrame, retrieval: str) -> dict[str, Any]:
    """The result file from the scored reports (the rows of inspection_auc.csv)."""
    scored = scored.assign(category_one_criteria=scored["category_one_criteria"].fillna(""))
    labels = scored["inspected"].to_numpy()
    month = pd.to_datetime(scored["event_date"]).dt.month
    quarter = ((month - 1) // 3 + 1).map(lambda q: f"Q{q}")

    result: dict[str, Any] = {
        "task": "B2, issue #3",
        "question": "How far does the crew's stage 1 ranking agree with OSHA's own inspection choices?",
        "reports": len(scored),
        "class_balance": _rate(int(labels.sum()), len(scored)),
        "all_reports": compare(
            {
                "crew_score": scored["crew_score"],
                "priority_alone": scored["priority"],
                "severity_alone": scored["severity"],
            },
            labels,
            "crew_score",
            "severity_alone",
        ),
    }
    two = scored[~scored["category_one"]]
    if two["inspected"].nunique() == 2:
        result["category_two_only"] = {
            "reports": len(two),
            "class_balance": _rate(int(two["inspected"].sum()), len(two)),
            **compare(
                {"priority": two["priority"], "severity_alone": two["severity"]},
                two["inspected"].to_numpy(),
                "priority",
                "severity_alone",
            ),
        }
    one = scored[scored["category_one"]]
    result["category_one"] = {
        **_rate(int(one["inspected"].sum()), len(one)),
        "by_criterion": {
            criterion: _rate(int(group["inspected"].sum()), len(group))
            for criterion, group in one.assign(c=one["category_one_criteria"].str.split("; "))
            .explode("c")
            .groupby("c")
        },
    }
    result["inspection_rate_by_quarter"] = {
        q: _rate(int(g["inspected"].sum()), len(g)) for q, g in scored.groupby(quarter.to_numpy())
    }
    result["method"] = {
        "data": "the 1,000 reports of the 2025 holdout (data/splits/holdout_2025.csv), which no rule, "
        "weight or threshold was tuned on",
        "label": "inspected = OSHA's Inspection field is filled in; past practice, not ground truth",
        "crew_score": f"stage 1 of the weekly list, offline: Category 1 reports first (+{CATEGORY_ONE_RANK:g}), "
        "then the Category 2 priority",
        "priority_alone": "the Category 2 priority, ignoring Category 1",
        "severity_alone": "amputation, loss of an eye and people hospitalized (at most two), with the "
        "priority's own weights",
        "interval": "DeLong's 95% interval for each AUC and for the paired difference; ties count half",
        "retrieval": retrieval,
        "weights": dict(DEFAULT_WEIGHTS),
        "triage_values_sha256": _weights_file(),
    }
    result["limitations"] = list(LIMITATIONS)
    result["command"] = "python -I scripts/eval_inspection_auc.py" + (
        " --no-dense" if retrieval == "bm25" else ""
    )
    return result


def run(dense: bool = True, out: Path = RESULTS_DIR / "inspection_auc.json") -> dict[str, Any]:
    """Score the 2025 holdout on the built data and write the result files next to `out`."""
    from safereport.graph import load_services
    from safereport.retrieval import dense_ready

    dense = dense and dense_ready()
    services = load_services(dense=dense)
    rows = services.store.frame("SELECT * FROM reports WHERE split = 'holdout' ORDER BY id")
    result, scored = evaluate(services, rows, "hybrid" if dense else "bm25")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    scored.to_csv(out.with_suffix(".csv"), index=False, lineterminator="\n")
    return result
