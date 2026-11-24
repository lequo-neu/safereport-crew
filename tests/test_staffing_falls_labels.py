"""Issue #37: the hand labels of the 20 reports the #30 work route adds, and the precision from them.

No data build, no model, nothing paid: the labels and results are committed files.
"""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest

from safereport.retrieval import reference_documents


SPEC = importlib.util.spec_from_file_location(
    "score_staffing_falls_labels", Path(__file__).parents[1] / "scripts" / "score_staffing_falls_labels.py"
)
labels_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(labels_mod)

HEADER = "id,slice,construction_fall,confidence,reason\n"


def write(tmp_path: Path, *lines: str) -> Path:
    path = tmp_path / "labels.csv"
    path.write_text(HEADER + "".join(line + "\n" for line in lines), encoding="utf-8")
    return path


def label(rid: str, answer: str, slice_: str = "test") -> dict[str, str]:
    return {"id": rid, "slice": slice_, "construction_fall": answer, "confidence": "high", "reason": "r"}


def test_committed_labels_cover_exactly_the_added_reports():
    labels = labels_mod.load_labels()
    _, listing = labels_mod.read_csv(labels_mod.LISTING)
    labels_mod.check_against_listing(labels, listing)
    assert len(labels) == 20
    assert sum(r["slice"] == "development" for r in labels) == 13
    assert sum(r["slice"] == "test" for r in labels) == 7


def test_listing_carries_the_labels_as_written():
    labels = {r["id"]: r for r in labels_mod.load_labels()}
    _, listing = labels_mod.read_csv(labels_mod.LISTING)
    for row in listing:
        for column in labels_mod.LABEL_COLUMNS:
            assert row[column] == labels[row["id"]][column]


def test_committed_results_match_the_labels():
    result = json.loads(labels_mod.RESULTS.read_text(encoding="utf-8"))
    assert result["hand_labels"] == json.loads(json.dumps(labels_mod.summary(labels_mod.load_labels())))
    test = result["hand_labels"]["test"]
    assert test["answers"] == {"yes": 4, "no": 1, "cannot_tell": 2}
    assert (test["precision_strict"]["k"], test["precision_strict"]["n"]) == (4, 7)
    assert (test["precision_decided"]["k"], test["precision_decided"]["n"]) == (4, 5)
    assert (test["precision_lenient"]["k"], test["precision_lenient"]["n"]) == (6, 7)
    assert result["hand_labels"]["development"]["answers"] == {"yes": 12, "no": 1, "cannot_tell": 0}


def test_rule_is_the_one_that_was_labelled():
    """The labels measure the rule in eval/results; changing it needs a new measurement (#37)."""
    result = json.loads(labels_mod.RESULTS.read_text(encoding="utf-8"))
    falls = next(d for d in reference_documents("emphasis_program") if d.citation == "CPL 03-00-025")
    assert falls.work_evidence == result["rule"]["work_evidence"]
    assert falls.work_exclusions == result["rule"]["work_exclusions"]
    assert falls.work_industries == result["rule"]["work_industries"]


def test_cannot_tell_is_neither_right_nor_wrong():
    rows = [label("1", "yes"), label("2", "yes"), label("3", "no"), label("4", "cannot_tell")]
    out = labels_mod.precision(rows)
    assert out["precision_strict"]["k"] == 2 and out["precision_strict"]["n"] == 4
    assert out["precision_decided"]["k"] == 2 and out["precision_decided"]["n"] == 3
    assert out["precision_lenient"]["k"] == 3 and out["precision_lenient"]["n"] == 4
    assert set(out["not_yes"]) == {"3", "4"}


def test_no_decided_answer_gives_no_rate():
    out = labels_mod.precision([label("1", "cannot_tell")])
    assert out["precision_decided"] == {"k": 0, "n": 0, "rate": None, "wilson_95": None}


@pytest.mark.parametrize(
    "line",
    [
        "1,test,maybe,high,r",
        "1,test,yes,sure,r",
        "1,test,yes,high,",
        "1,holdout,yes,high,r",
    ],
)
def test_invalid_labels_are_refused(tmp_path: Path, line: str):
    with pytest.raises(ValueError):
        labels_mod.load_labels(write(tmp_path, line))


def test_duplicate_label_is_refused(tmp_path: Path):
    with pytest.raises(ValueError, match="twice"):
        labels_mod.load_labels(write(tmp_path, "1,test,yes,high,r", "1,test,no,high,r"))


def test_labels_must_match_the_listing():
    listing = [{"id": "1", "slice": "test"}, {"id": "2", "slice": "development"}]
    labels_mod.check_against_listing([label("1", "yes"), label("2", "no", "development")], listing)
    with pytest.raises(ValueError, match="missing"):
        labels_mod.check_against_listing([label("1", "yes")], listing)
    with pytest.raises(ValueError, match="other slice"):
        labels_mod.check_against_listing([label("1", "yes"), label("2", "no", "test")], listing)


def test_relabelling_replaces_old_label_columns(tmp_path: Path):
    path = tmp_path / "added.csv"
    fields = ["id", "slice", "narrative", *labels_mod.LABEL_COLUMNS]
    listing = [
        {
            "id": "1",
            "slice": "test",
            "narrative": "n",
            "construction_fall": "no",
            "confidence": "low",
            "reason": "old",
        }
    ]
    labels_mod.write_listing(path, fields, listing, {"1": label("1", "yes")})
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0]) == ["id", "slice", "narrative", "construction_fall", "confidence", "reason"]
    assert rows[0]["construction_fall"] == "yes" and rows[0]["reason"] == "r"
