"""The draw for the hand check of the Category 1 rules (B3): reproducible, holdout only, blank labels."""

from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

import pytest

from safereport.config import PROJECT_ROOT
from tests.conftest import write_sir_csv


SCRIPT = PROJECT_ROOT / "scripts" / "make_category1_sample.py"
spec = importlib.util.spec_from_file_location("make_category1_sample", SCRIPT)
sample = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sample)

HOLDOUT = ["4", "5", "6", "7", "8", "9"]  # the 2025 reports of the small file


@pytest.fixture
def files(tmp_path: Path) -> dict[str, Path]:
    sir = write_sir_csv(tmp_path / "sir.csv")
    holdout = tmp_path / "holdout.csv"
    holdout.write_text("id\n" + "\n".join(HOLDOUT) + "\n", encoding="utf-8")
    return {"sir": sir, "holdout": holdout, "out": tmp_path / "check.csv", "khoa": tmp_path / "khoa.csv"}


def read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def run(files: dict[str, Path], *extra: str) -> int:
    return sample.main(
        [str(files["sir"]), "--holdout", str(files["holdout"]), "--out", str(files["out"]),
         "--check-out", str(files["khoa"]), "--cases", "4", "--shared", "2", *extra]
    )  # fmt: skip


def test_the_same_seed_draws_the_same_reports_in_the_same_order(files):
    reports, holdout = sample.read_reports(files["sir"]), sample.read_holdout(files["holdout"])
    first, _ = sample.draw(reports, holdout, cases=4, shared=2, seed=42)
    again, _ = sample.draw(reports, list(reversed(holdout)), cases=4, shared=2, seed=42)
    other, _ = sample.draw(reports, holdout, cases=4, shared=2, seed=7)
    ids = [r["sir_id"] for r in first]
    assert ids == [r["sir_id"] for r in again], "the order of the holdout file must not change the draw"
    assert ids != [r["sir_id"] for r in other]


def test_only_holdout_reports_are_drawn_with_every_label_blank(files):
    assert run(files) == 0
    rows = read(files["out"])
    assert len(rows) == 4 and len({r["sir_id"] for r in rows}) == 4
    assert {r["sir_id"] for r in rows} <= set(HOLDOUT)
    assert [r["case"] for r in rows] == ["K001", "K002", "K003", "K004"]
    assert all(r["hospitalized"].isdigit() and r["amputation"].isdigit() for r in rows)
    assert sample.count("2.00") == "2" and sample.count(" ") == "0"
    assert all(r[name] == "" for r in rows for name in sample.FILL_IN), "labels are a person's job"
    # Nothing that could sway the labeler: no rule output, no OSHA inspection decision.
    assert not {"inspection", "inspected", "category_one_rules", "priority"} & set(rows[0])


def test_the_checkers_file_holds_the_shared_cases_and_no_labels(files):
    assert run(files) == 0
    rows, khoa = read(files["out"]), read(files["khoa"])
    shared = [r for r in rows if r["checked_by"] == "Khoa"]
    assert len(khoa) == 2 and [r["sir_id"] for r in shared] == [r["sir_id"] for r in khoa]
    assert "checked_by" not in khoa[0]
    assert all(r[name] == "" for r in khoa for name in sample.FILL_IN)


def test_a_second_run_never_overwrites_labels(files):
    assert run(files) == 0
    files["out"].write_text(
        files["out"].read_text(encoding="utf-8") + "labels,in,progress\n", encoding="utf-8"
    )
    before = files["out"].read_text(encoding="utf-8")
    assert run(files) == 1
    assert files["out"].read_text(encoding="utf-8") == before
    files["out"].unlink()
    assert run(files) == 1, "the checker's file still exists, so nothing is written"
    assert not files["out"].exists()


def test_impossible_requests_are_refused(files):
    reports, holdout = sample.read_reports(files["sir"]), sample.read_holdout(files["holdout"])
    with pytest.raises(ValueError, match="fewer than"):
        sample.draw(reports, holdout, cases=7, shared=2)
    with pytest.raises(ValueError, match="shared"):
        sample.draw(reports, holdout, cases=4, shared=5)
    with pytest.raises(ValueError, match="not in the OSHA file"):
        sample.draw(reports, [*holdout, "2099"], cases=4, shared=2)


def test_the_file_reads_back_with_one_row_per_line_on_every_platform(files):
    assert run(files) == 0
    assert b"\r\r\n" not in files["out"].read_bytes()
