from __future__ import annotations

import csv
from pathlib import Path
import shutil

import pytest

from safereport.labels import LABEL_DIR, UnsettledLabelsError, load_answer_key, merge_labels


def test_merge_reproduces_the_committed_answer_key():
    rows, _ = merge_labels(LABEL_DIR)
    with (LABEL_DIR / "answer_key.csv").open(newline="", encoding="utf-8") as handle:
        committed = list(csv.DictReader(handle))
    assert rows == committed


def test_merge_summary_matches_what_the_proposal_reports():
    _, summary = merge_labels(LABEL_DIR)
    assert summary.cases == 60
    assert summary.with_standard == 51  # C20 corrected to no specific standard, pending the team
    assert summary.shared == 15
    assert summary.same_section == 13
    assert summary.settled == 2
    assert round(summary.agreement * 100, 1) == 86.7


def test_every_case_of_the_key_is_valid():
    key = load_answer_key()
    assert [c.case for c in key] == [f"C{n:02d}" for n in range(1, 61)]
    assert len({c.sir_id for c in key}) == 60
    for case in key:
        if case.has_standard:
            assert case.primary_section.startswith("1910.")
        else:
            assert case.no_standard_reason


def test_key_cases_come_from_the_drawn_sample():
    with (LABEL_DIR / "rag_label_sample.csv").open(newline="", encoding="utf-8") as handle:
        sample = {r["case"]: r for r in csv.DictReader(handle)}
    for case in load_answer_key():
        assert sample[case.case]["sir_id"] == case.sir_id
        assert sample[case.case]["narrative"] == case.narrative


def test_an_unsettled_disagreement_stops_the_merge(tmp_path: Path):
    for name in ("Kevin", "Hamad", "Khoa"):
        shutil.copy(LABEL_DIR / f"to_label_{name}.csv", tmp_path)
    with pytest.raises(UnsettledLabelsError, match="C05, C07"):
        merge_labels(tmp_path)


def test_c20_carries_the_label_hamad_confirmed():
    c20 = next(c for c in load_answer_key() if c.case == "C20")
    assert c20.status == "single labeler" and c20.labelers == ["Hamad"]
    assert not c20.has_standard and "general duty" in c20.no_standard_reason


def test_a_correction_is_applied_last_and_marked_pending(tmp_path: Path):
    for name in ("Kevin", "Hamad", "Khoa", "settlements", "corrections"):
        source = LABEL_DIR / (f"to_label_{name}.csv" if name in ("Kevin", "Hamad", "Khoa") else f"{name}.csv")
        shutil.copy(source, tmp_path)
    with (tmp_path / "corrections.csv").open("a", encoding="utf-8") as handle:
        handle.write("C11,1910.212(a)(3)(ii),,low,,a test correction,proposed\n")
    rows, _ = merge_labels(tmp_path)
    c11 = next(r for r in rows if r["case"] == "C11")
    assert (
        c11["primary_standard"] == "1910.212(a)(3)(ii)"
        and c11["status"] == "corrected, pending team confirmation"
    )
