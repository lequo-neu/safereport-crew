"""B2: the inspection priority against OSHA's choices, on the small file (no download, no model)."""

from __future__ import annotations

import json

from langgraph.checkpoint.memory import InMemorySaver
import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import roc_auc_score

from safereport import inspection_eval
from safereport.graph import build_graph, run_config


def test_delong_auc_matches_sklearn_with_ties():
    rng = np.random.default_rng(0)
    labels = rng.random(300) < 0.3
    score = np.round(labels * 0.8 + rng.random(300), 1)  # rounded, so many ties
    other = rng.integers(0, 4, 300)
    aucs, cov = inspection_eval.delong([score, other], labels)
    assert aucs[0] == pytest.approx(roc_auc_score(labels, score))
    assert aucs[1] == pytest.approx(roc_auc_score(labels, other))
    assert cov.shape == (2, 2) and cov[0, 0] > 0


def test_intervals_hold_the_auc_and_a_score_against_itself_differs_by_nothing():
    labels = [True, True, False, False, True, False, False, False]
    score = [5, 3, 4, 1, 2, 0, 1, 0]
    result = inspection_eval.compare({"a": score, "b": list(score)}, labels, "a", "b")
    low, high = result["a"]["auc_ci95"]
    assert low <= result["a"]["auc"] <= high
    assert result["a_minus_b"]["auc_difference"] == 0 and result["a_minus_b"]["p_value"] == 1.0
    perfect = inspection_eval.compare({"a": [2, 2, 1], "b": [1, 1, 1]}, [True, True, False], "a", "b")
    assert perfect["a"]["auc"] == 1.0 and perfect["b"]["auc"] == 0.5


def test_one_class_alone_has_no_auc():
    with pytest.raises(ValueError, match="at least one inspected"):
        inspection_eval.delong([[1, 2]], [True, True])


def test_the_scores_are_the_ones_the_weekly_list_uses(small_services):
    """The evaluation re-scores stage 1 outside the graph; it must give the graph's own numbers."""
    graph = build_graph(small_services, InMemorySaver())
    config = run_config()
    graph.invoke({"request": "Plan this week's inspections in Ohio."}, config)
    stage1 = graph.get_state(config).values["stage1"]
    start, end = small_services.week
    rows = small_services.store.reports_between(start, end, "OHIO")
    scored = inspection_eval.score_reports(small_services, rows).set_index("id")
    assert set(scored.index) == set(stage1)
    for report_id, item in stage1.items():
        assert scored.loc[report_id, "priority"] == item["priority"]
        assert scored.loc[report_id, "category_one"] == bool(item["category_one"])


def test_the_score_never_sees_whether_osha_inspected(small_services):
    rows = small_services.store.frame("SELECT * FROM reports ORDER BY id")
    flipped = rows.assign(inspected=~rows["inspected"], inspection=np.where(rows["inspected"], "", "999"))
    first = inspection_eval.score_reports(small_services, rows)
    second = inspection_eval.score_reports(small_services, flipped)
    columns = ["priority", "crew_score", "severity", "category_one"]
    assert first[columns].equals(second[columns])


def test_the_evaluation_on_the_small_file(small_services, tmp_path):
    rows = small_services.store.frame("SELECT * FROM reports ORDER BY id")
    result, scored = inspection_eval.evaluate(small_services, rows, "bm25")
    assert result["reports"] == 9 and result["class_balance"]["inspected"] == 2
    assert set(result["all_reports"]) == {
        "crew_score", "priority_alone", "severity_alone", "crew_score_minus_severity_alone",
    }  # fmt: skip
    for name in ("crew_score", "priority_alone", "severity_alone"):
        assert 0.0 <= result["all_reports"][name]["auc"] <= 1.0
    # The amputation (report 6) is inspected and ranks above every report with one person hospitalized.
    assert scored.set_index("id").loc["6", "severity"] > scored.set_index("id").loc["1", "severity"]
    assert result["method"]["retrieval"] == "bm25" and result["command"].endswith(
        "eval_inspection_auc.py --no-dense"
    )
    assert len(result["limitations"]) >= 5
    json.dumps(result)  # the result file is plain JSON


def test_the_result_file_can_be_rebuilt_from_the_per_report_file(small_services, tmp_path):
    rows = small_services.store.frame("SELECT * FROM reports ORDER BY id")
    result, scored = inspection_eval.evaluate(small_services, rows, "bm25")
    scored.to_csv(tmp_path / "scored.csv", index=False)
    again = pd.read_csv(tmp_path / "scored.csv", dtype={"id": str})
    assert inspection_eval.summarize(again, "bm25") == result


def test_the_weights_fingerprint_counts_values_not_comments(tmp_path):
    """Writing down why a weight is what it is must not read as a change of weights (#28)."""
    plain = tmp_path / "plain.toml"
    plain.write_text("default_capacity = 40.0\n[weights]\namputation = 3.0\n", encoding="utf-8")
    commented = tmp_path / "commented.toml"
    commented.write_text(
        "# why\ndefault_capacity = 40.0\r\n\n[weights]\n# severity\namputation = 3.0  # per report\n",
        encoding="utf-8",
    )
    changed = tmp_path / "changed.toml"
    changed.write_text("default_capacity = 40.0\n[weights]\namputation = 2.0\n", encoding="utf-8")
    fingerprint = inspection_eval._weights_file
    assert fingerprint(plain) == fingerprint(commented) != fingerprint(changed)
    assert fingerprint(tmp_path / "missing.toml") == "built in"
