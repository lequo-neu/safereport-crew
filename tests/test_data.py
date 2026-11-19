from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from safereport.data import (
    CODES_V3_PARQUET,
    REPORTS_PARQUET,
    Filters,
    MixedCodingError,
    ReportStore,
    build_parquet,
    holdout_ids,
)
from safereport.evaluation import recode_check
from tests.conftest import ROWS, write_sir_csv


needs_parquet = pytest.mark.skipif(not REPORTS_PARQUET.exists(), reason="run `safereport build-data` first")


def test_splits_follow_the_year_and_the_holdout(small_store: ReportStore):
    splits = small_store.frame("SELECT split, count(*) AS n FROM reports GROUP BY split ORDER BY split")
    assert dict(zip(splits["split"], splits["n"], strict=True)) == {"holdout": 2, "recent": 4, "train": 3}


def test_filters_are_case_insensitive_and_combine(small_store: ReportStore):
    assert small_store.count(Filters(state="texas")) == 5
    assert small_store.count(Filters(state="Ohio", naics_prefix="23")) == 1
    assert small_store.count(Filters(start=date(2025, 1, 1), end=date(2025, 3, 31))) == 2


def test_event_filters_are_refused_across_the_oiics_change(tmp_path: Path):
    old = (
        "10",
        "5/5/2023",
        "Acme Laminates LLC",
        "DAYTON",
        "OHIO",
        "45402",
        "326130",
        "0",
        "1",
        "",
        "6411",
        "Caught in rollers.",
    )
    csv_path = write_sir_csv(tmp_path / "sir.csv", [*ROWS, old])
    build_parquet(csv_path, tmp_path / "r.parquet", tmp_path / "h.csv", holdout_size=1)
    store = ReportStore(tmp_path / "r.parquet", codes_v3=None)
    for filters in (Filters(event_group="64"), Filters(event_text="title")):
        with pytest.raises(MixedCodingError, match="January 2024"):
            store.count(filters)
        with pytest.raises(MixedCodingError):
            store.yearly_trend(filters)
    assert store.count(Filters(event_group="64", start=date(2024, 1, 1))) == 4
    assert store.count(Filters(event_group="64", end=date(2023, 12, 31))) == 1


def test_event_group_v3_needs_the_recoded_events(small_store: ReportStore):
    with pytest.raises(MixedCodingError, match="train-baseline"):
        small_store.count(Filters(event_group_v3="64"))


def test_queries_cannot_read_other_files(small_store: ReportStore):
    with pytest.raises(Exception, match="disabled"):
        small_store.frame("SELECT * FROM read_csv('/etc/hosts')")


def test_yearly_trend_compares_the_same_months(small_store: ReportStore):
    trend = small_store.yearly_trend().set_index("year")
    assert small_store.last_date() == date(2025, 6, 20)
    assert trend.loc[2025, "partial"] and not trend.loc[2024, "partial"]
    # 2024 has three reports, but only two fall in January to June, the months 2025 covers.
    assert trend.loc[2024, "reports"] == 3
    assert trend.loc[2024, "same_months"] == 2
    assert trend.loc[2025, "change"] == pytest.approx(6 / 2 - 1)


def test_only_single_select_queries_run(small_store: ReportStore):
    for bad in (
        "DROP TABLE reports",
        "SELECT 1; SELECT 2",
        "COPY reports TO 'x.csv'",
        "WITH x AS (SELECT 1) UPDATE reports SET split = 'train' WHERE split = 'holdout'",
        "WITH x AS (SELECT 1) DELETE FROM reports",
        "not sql at all",
    ):
        with pytest.raises(ValueError, match="single SELECT"):
            small_store.frame(bad)


def test_years_without_reports_count_as_zero(small_store: ReportStore):
    trend = small_store.yearly_trend(Filters(state="Ohio")).set_index("year")
    assert trend.loc[2024, "reports"] == 0
    assert trend.loc[2025, "reports"] == 4
    assert pd.isna(trend.loc[2025, "change"])  # no change can be measured from zero


def test_report_comes_back_as_a_validated_record(small_store: ReportStore):
    report = small_store.report("6")
    assert report.amputation == 1 and report.inspected and report.is_manufacturing
    with pytest.raises(KeyError):
        small_store.report("999")


def test_holdout_is_drawn_once_and_then_reused(tmp_path: Path):
    frame = pd.DataFrame({"id": [str(i) for i in range(20)], "year": [2025] * 20})
    first = holdout_ids(frame, tmp_path / "ids.csv", size=5)
    frame["id"] = frame["id"].iloc[::-1].to_numpy()
    assert holdout_ids(frame, tmp_path / "ids.csv", size=5) == first


def test_missing_parquet_says_how_to_build_it(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="build-data"):
        ReportStore(tmp_path / "none.parquet")


def test_build_returns_the_row_count(tmp_path: Path):
    csv_path = write_sir_csv(tmp_path / "sir.csv")
    assert build_parquet(csv_path, tmp_path / "r.parquet", tmp_path / "h.csv", holdout_size=1) == 9


@needs_parquet
def test_real_data_matches_the_numbers_in_the_proposal():
    store = ReportStore()
    assert store.count() == 105_996
    assert store.last_date() == date(2025, 11, 30)
    trend = store.yearly_trend().set_index("year")
    assert trend.loc[2024, "reports"] == 9034
    assert trend.loc[2024, "same_months"] == 8340
    assert trend.loc[2025, "same_months"] == 8712
    assert round(trend.loc[2025, "change"] * 100, 1) == 4.5
    assert store.count(Filters(state="texas", start=date(2024, 1, 1), end=date(2024, 12, 31))) == 1485


@needs_parquet
def test_real_report_keys_are_unique_and_keep_osha_ids():
    counts = ReportStore().frame(
        "SELECT count(*) AS n, count(DISTINCT id) AS ids, count(DISTINCT osha_id) AS osha FROM reports"
    )
    assert counts.to_dict("records") == [{"n": 105_996, "ids": 105_996, "osha": 105_991}]


@needs_parquet
def test_real_holdout_is_1000_reports_from_2025():
    store = ReportStore()
    holdout = store.frame("SELECT year, count(*) AS n FROM reports WHERE split = 'holdout' GROUP BY year")
    assert holdout.to_dict("records") == [{"year": 2025, "n": 1000}]


@needs_parquet
def test_real_codes_switch_to_oiics_3_in_2024():
    store = ReportStore()
    shares = store.frame(
        "WITH old AS (SELECT DISTINCT event_code FROM reports WHERE year <= 2022) "
        "SELECT year, avg(CASE WHEN event_code IN (SELECT event_code FROM old) THEN 0 ELSE 1 END) AS new "
        "FROM reports WHERE year IN (2023, 2024) GROUP BY year ORDER BY year"
    )["new"].tolist()
    assert shares[0] < 0.01 and shares[1] > 0.5
    versions = store.frame(
        "SELECT DISTINCT year, oiics_version FROM reports WHERE year IN (2023, 2024) ORDER BY year"
    )
    assert versions["oiics_version"].tolist() == [2, 3]


@needs_parquet
def test_real_event_codes_are_refused_across_2024_but_allowed_on_one_side():
    store = ReportStore()
    with pytest.raises(MixedCodingError):
        store.yearly_trend(Filters(event_group="64"))
    with pytest.raises(MixedCodingError):
        store.count(Filters(event_text="caught", start=date(2023, 1, 1)))
    assert store.count(Filters(event_group="64", start=date(2024, 1, 1))) > 0
    assert store.count(Filters(event_group="64", end=date(2023, 12, 31))) > 0


@needs_parquet
@pytest.mark.skipif(not CODES_V3_PARQUET.exists(), reason="run `safereport train-baseline` first")
def test_recoded_groups_are_close_to_the_real_oiics_3_groups():
    store = ReportStore()
    check = recode_check(store)
    # Measured on 19 November 2026: 0.064, against 0.047 between the real 2024 and 2025.
    assert check["recoded_2023_vs_real_2024"] < 0.10
    trend = store.yearly_trend(Filters(event_group_v3="64")).set_index("year")
    assert trend.loc[2023, "estimated_share"] == 1.0 and trend.loc[2024, "estimated_share"] == 0.0
