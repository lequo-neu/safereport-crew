"""The non LLM baseline for event coding: TF IDF features and logistic regression.

It codes every report in stage 1 in seconds, and it is the bar the Intake agent must beat.
Like the BLS autocoder, it assigns a code only when its confidence clears a threshold; the
coverage curve shows how accuracy rises as fewer reports are coded automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.pipeline import Pipeline

from safereport.config import PROJECT_ROOT


MODEL_PATH = PROJECT_ROOT / "indexes" / "event_baseline.joblib"
CODES_V3_PATH = PROJECT_ROOT / "data" / "processed" / "event_codes_v3.parquet"


@dataclass
class Prediction:
    code: str
    confidence: float


class EventBaseline:
    """Predicts the full OIICS event code; its first two digits give the event group."""

    def __init__(self, max_features: int = 60_000, alpha: float = 1e-6, max_iter: int = 30) -> None:
        self.pipeline = Pipeline(
            [
                (
                    "tfidf",
                    TfidfVectorizer(
                        ngram_range=(1, 2), min_df=2, max_features=max_features, sublinear_tf=True
                    ),
                ),
                # Logistic regression (log loss) fitted by stochastic gradient descent, one model
                # per code in parallel. A single multinomial lbfgs fit over about 470 codes ran
                # for more than eight minutes and 8 GB without finishing.
                (
                    "model",
                    SGDClassifier(
                        loss="log_loss", alpha=alpha, max_iter=max_iter, tol=1e-4, n_jobs=-1, random_state=42
                    ),
                ),
            ]
        )

    def fit(self, texts: list[str], codes: list[str]) -> EventBaseline:
        self.pipeline.fit(texts, codes)
        return self

    def predict(self, texts: list[str]) -> list[Prediction]:
        # The per code scores are normalized to sum to one, so the top share reads as a confidence.
        probabilities = self.pipeline.predict_proba(texts)
        classes = self.pipeline.classes_
        best = probabilities.argmax(axis=1)
        return [Prediction(str(classes[i]), float(probabilities[row, i])) for row, i in enumerate(best)]

    def save(self, path: Path = MODEL_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.pipeline, path)

    @classmethod
    def load(cls, path: Path = MODEL_PATH) -> EventBaseline:
        baseline = cls()
        baseline.pipeline = joblib.load(path)
        return baseline


def accuracy_by_level(predicted: list[str], actual: list[str]) -> dict[str, float]:
    """Accuracy on the full code, the two digit group and the one digit division."""
    pairs = list(zip(predicted, actual, strict=True))
    return {
        level: float(np.mean([p[:width] == a[:width] for p, a in pairs]))
        for level, width in (("full_code", 6), ("group_2_digit", 2), ("division_1_digit", 1))
    }


def coverage_curve(predictions: list[Prediction], actual: list[str], thresholds: list[float]) -> pd.DataFrame:
    """For each threshold: the share coded automatically and the accuracy on that share."""
    confidence = np.array([p.confidence for p in predictions])
    correct = np.array([p.code == a for p, a in zip(predictions, actual, strict=True)])
    rows = []
    for threshold in thresholds:
        coded = confidence >= threshold
        rows.append(
            {
                "threshold": threshold,
                "coverage": float(coded.mean()),
                "accuracy": float(correct[coded].mean()) if coded.any() else float("nan"),
            }
        )
    return pd.DataFrame(rows)


def recode_to_oiics_3(reports: pd.DataFrame, baseline: EventBaseline) -> pd.DataFrame:
    """An OIICS 3 event code for every report, so hazard trends can run across January 2024.

    Reports from 2024 on keep OSHA's own code. Older ones get the code the OIICS 3 baseline
    predicts from the narrative, marked as estimated; the recoded 2023 groups differ from the
    real 2024 groups by about as much as 2024 differs from 2025.
    """
    old = reports["oiics_version"] == 2
    predictions = baseline.predict(reports.loc[old, "narrative"].tolist())
    codes = reports[["id"]].copy()
    codes["event_code_v3"] = reports["event_code"]
    codes["event_v3_confidence"] = 1.0
    codes.loc[old, "event_code_v3"] = [p.code for p in predictions]
    codes.loc[old, "event_v3_confidence"] = [p.confidence for p in predictions]
    codes["event_v3_estimated"] = old.to_numpy()
    return codes
