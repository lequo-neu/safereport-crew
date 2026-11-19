from __future__ import annotations

import pytest

from safereport.data import REPORTS_PARQUET, ReportStore
from safereport.signals import TEMPORARY_WORKER, mentions_temporary_worker


@pytest.mark.parametrize(
    ("narrative", "expected"),
    [
        ("A temporary employee caught a finger in the press.", True),
        ("A temp worker from a staffing agency fell.", True),
        ("Workers made temporary repairs to the platform.", False),
        ("An employee stood on a temporary platform.", False),
    ],
)
def test_temporary_worker_rule(narrative: str, expected: bool):
    assert mentions_temporary_worker(narrative) is expected


@pytest.mark.skipif(not REPORTS_PARQUET.exists(), reason="run `safereport build-data` first")
def test_the_proposal_figure_comes_from_this_rule():
    rows = ReportStore().frame("SELECT narrative, inspected FROM reports")
    temporary = rows[rows["narrative"].str.contains(TEMPORARY_WORKER)]
    # 1,058 reports on the cleaned narratives (one more than on the raw CSV, where a line break
    # split "temporary" from "employee"); 49.7% of them were inspected, as the proposal says.
    assert len(temporary) == 1058
    assert round(temporary["inspected"].mean() * 100, 1) == 49.7
