from __future__ import annotations

import pytest

from safereport.baseline import MODEL_PATH, EventBaseline, Prediction, accuracy_by_level, coverage_curve
from safereport.data import REPORTS_PARQUET, ReportStore


TEXTS = [
    "hand caught in the rollers while cleaning",
    "finger caught in the conveyor belt",
    "arm pulled into the auger",
    "fell from a ladder to the floor",
    "fell from the roof edge",
    "fell off a platform",
    "slipped on a wet floor",
    "tripped over a pallet and fell",
    "slipped on ice in the lot",
]
CODES = ["6411", "6411", "6411", "4330", "4330", "4330", "4220", "4220", "4220"]


def test_baseline_learns_and_predicts_with_a_confidence():
    baseline = EventBaseline(max_features=500, alpha=1e-4).fit(TEXTS, CODES)
    predictions = baseline.predict(["glove caught in the rollers", "worker fell from a ladder"])
    assert [p.code for p in predictions] == ["6411", "4330"]
    assert all(0 < p.confidence <= 1 for p in predictions)


def test_accuracy_by_level_compares_code_prefixes():
    scores = accuracy_by_level(["6411", "6420", "4330"], ["6411", "6411", "5111"])
    assert scores == {"full_code": 1 / 3, "group_2_digit": 2 / 3, "division_1_digit": 2 / 3}


def test_coverage_falls_and_accuracy_rises_with_the_threshold():
    predictions = [Prediction("a", 0.9), Prediction("b", 0.8), Prediction("c", 0.4), Prediction("d", 0.2)]
    curve = coverage_curve(predictions, ["a", "b", "x", "y"], [0.0, 0.5, 0.95])
    assert curve["coverage"].tolist() == [1.0, 0.5, 0.0]
    assert curve["accuracy"].iloc[0] == 0.5 and curve["accuracy"].iloc[1] == 1.0


def test_saved_baseline_loads(tmp_path):
    path = tmp_path / "model.joblib"
    EventBaseline(max_features=500, alpha=1e-4).fit(TEXTS, CODES).save(path)
    assert EventBaseline.load(path).predict(["fell from a ladder"])[0].code == "4330"


@pytest.mark.skipif(
    not (MODEL_PATH.exists() and REPORTS_PARQUET.exists()), reason="run `safereport train-baseline` first"
)
def test_trained_baseline_holds_its_holdout_accuracy():
    holdout = ReportStore().frame("SELECT narrative, event_code FROM reports WHERE split = 'holdout'")
    predictions = EventBaseline.load().predict(holdout["narrative"].tolist())
    scores = accuracy_by_level([p.code for p in predictions], holdout["event_code"].tolist())
    # Measured on 19 November 2026: full code 0.596, two digit group 0.787. The floors sit below
    # that to catch a regression; nothing was tuned on the holdout.
    assert scores["group_2_digit"] >= GROUP_FLOOR
    assert scores["full_code"] >= CODE_FLOOR


@pytest.mark.skipif(
    not (MODEL_PATH.exists() and REPORTS_PARQUET.exists()), reason="run `safereport train-baseline` first"
)
def test_confident_codes_are_more_accurate_as_bls_reports():
    holdout = ReportStore().frame("SELECT narrative, event_code FROM reports WHERE split = 'holdout'")
    predictions = EventBaseline.load().predict(holdout["narrative"].tolist())
    curve = coverage_curve(predictions, holdout["event_code"].tolist(), [0.0, 0.7]).set_index("threshold")
    assert curve.loc[0.7, "accuracy"] > curve.loc[0.0, "accuracy"] + 0.1
    assert curve.loc[0.7, "coverage"] >= 0.4


GROUP_FLOOR = 0.75
CODE_FLOOR = 0.55
