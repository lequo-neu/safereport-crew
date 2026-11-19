"""The severe injury reports as Parquet, queried with DuckDB.

The CSV is read once and written as Parquet with clean column names; every question after
that is a DuckDB query on disk, so nothing loads the whole file into memory per question.
The 2025 holdout ids are kept in data/splits so every run and every teammate uses the same
1,000 reports for evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from safereport.config import PROJECT_ROOT
from safereport.schemas import Report


RAW_CSV = PROJECT_ROOT / "data" / "raw" / "January2015toNovember2025.csv"
REPORTS_PARQUET = PROJECT_ROOT / "data" / "processed" / "reports.parquet"
# Words the narratives use in lower case at least three times; redaction treats a pair of
# capitalized words that are not in it as a name (see redaction.py).
COMMON_WORDS = PROJECT_ROOT / "data" / "processed" / "common_words.txt"
# Written by `safereport train-baseline`: an OIICS 3 code for every report (see baseline.py).
CODES_V3_PARQUET = PROJECT_ROOT / "data" / "processed" / "event_codes_v3.parquet"
HOLDOUT_IDS = PROJECT_ROOT / "data" / "splits" / "holdout_2025.csv"
HOLDOUT_SIZE = 1000
HOLDOUT_SEED = 42
# OSHA codes events with OIICS 3 from January 2024: about 65% of the 2024 codes never appear
# in 2015 to 2023, so a coder is trained and scored on reports of the same OIICS version.
OIICS_3_FROM_YEAR = 2024

COLUMNS = {
    "ID": "id",
    "EventDate": "event_date",
    "Employer": "employer",
    "City": "city",
    "State": "state",
    "Zip": "zip",
    "Latitude": "latitude",
    "Longitude": "longitude",
    "Primary NAICS": "naics",
    "Hospitalized": "hospitalized",
    "Amputation": "amputation",
    "Loss of Eye": "loss_of_eye",
    "Inspection": "inspection",
    "Final Narrative": "narrative",
    "Event": "event_code",
    "EventTitle": "event_title",
    "Source": "source_code",
    "SourceTitle": "source_title",
    "NatureTitle": "nature_title",
    "Part of Body Title": "body_part_title",
}


def read_osha_csv(path: Path = RAW_CSV) -> pd.DataFrame:
    """OSHA's CSV with clean names and types; every cell is read as text first, then converted."""
    raw = pd.read_csv(path, dtype=str, keep_default_na=False, encoding_errors="replace")
    frame = raw.rename(columns=COLUMNS)
    frame["address1"] = raw["Address1"].str.strip()
    frame["address2"] = raw["Address2"].str.strip()
    frame["address"] = (frame["address1"] + " " + frame["address2"]).str.strip()
    frame = frame[[*COLUMNS.values(), "address", "address1", "address2"]].copy()
    for column in (
        "id",
        "employer",
        "city",
        "state",
        "zip",
        "naics",
        "inspection",
        "event_code",
        "source_code",
    ):
        frame[column] = frame[column].str.strip()
    frame["event_date"] = pd.to_datetime(frame["event_date"].str.split().str[0], format="%m/%d/%Y").dt.date
    for column in ("hospitalized", "amputation", "loss_of_eye"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0).astype(int)
    for column in ("latitude", "longitude"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["narrative"] = frame["narrative"].str.split().str.join(" ")
    # OSHA reuses a few IDs for different reports (five pairs in January 2015), so `id` gets a
    # suffix on the second report and `osha_id` keeps OSHA's own number.
    frame["osha_id"] = frame["id"]
    repeat = frame.groupby("id").cumcount()
    frame.loc[repeat > 0, "id"] = frame["id"] + "-" + (repeat + 1).astype(str)
    frame["year"] = pd.to_datetime(frame["event_date"]).dt.year
    frame["month"] = pd.to_datetime(frame["event_date"]).dt.month
    frame["naics2"] = frame["naics"].str[:2]
    frame["naics3"] = frame["naics"].str[:3]
    frame["event_group"] = frame["event_code"].str[:2]
    frame["inspected"] = frame["inspection"] != ""
    frame["oiics_version"] = np.where(frame["year"] >= OIICS_3_FROM_YEAR, 3, 2)
    return frame


def holdout_ids(frame: pd.DataFrame, path: Path = HOLDOUT_IDS, size: int = HOLDOUT_SIZE) -> list[str]:
    """The 1,000 held out 2025 reports: read from data/splits, or drawn once and written there."""
    if path.exists():
        return pd.read_csv(path, dtype=str)["id"].tolist()
    pool = sorted(frame.loc[frame["year"] == 2025, "id"])
    rng = np.random.default_rng(HOLDOUT_SEED)
    ids = sorted(rng.choice(pool, size=size, replace=False).tolist())
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"id": ids}).to_csv(path, index=False)
    return ids


def build_parquet(
    csv_path: Path = RAW_CSV,
    out: Path = REPORTS_PARQUET,
    splits: Path = HOLDOUT_IDS,
    holdout_size: int = HOLDOUT_SIZE,
) -> int:
    """Write reports.parquet with a split column: train (2015 to 2024), holdout, or recent (other 2025)."""
    frame = read_osha_csv(csv_path)
    held = set(holdout_ids(frame, splits, holdout_size))
    frame["split"] = np.where(
        frame["year"] <= 2024, "train", np.where(frame["id"].isin(held), "holdout", "recent")
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(out, index=False)
    write_common_words(frame["narrative"], out.parent / COMMON_WORDS.name)
    return len(frame)


def write_common_words(narratives: pd.Series, path: Path = COMMON_WORDS, minimum: int = 3) -> int:
    counts = narratives.str.findall(r"\b[a-z][a-z'-]+\b").explode().value_counts()
    words = sorted(counts[counts >= minimum].index)
    path.write_text("\n".join(words) + "\n")
    return len(words)


class MixedCodingError(ValueError):
    """An event code filter covers reports coded with two OIICS versions."""


@dataclass
class Filters:
    """The filters every Analyst question can use. Empty fields do not filter.

    OSHA moved from OIICS 2 to OIICS 3 in January 2024, and both the codes and the titles
    changed meaning: group 64 is "caught in machinery" in OIICS 2 and "struck by a falling
    object" in OIICS 3, and reports with "caught" in the title fall 42% from 2023 to 2024 only
    because OIICS 3 sorts them differently. So `event_group` and `event_text` are refused over a
    period that spans both versions. `event_group_v3` works across all years: it uses OSHA's
    code from 2024 on and the code the OIICS 3 baseline estimates for older reports.
    """

    state: str = ""
    naics_prefix: str = ""
    event_group: str = ""
    event_text: str = ""
    event_group_v3: str = ""
    start: date | None = None
    end: date | None = None

    def where(self) -> tuple[str, list[object]]:
        parts, params = ["TRUE"], []
        if self.state:
            parts.append("upper(state) = upper(?)")
            params.append(self.state)
        if self.naics_prefix:
            parts.append("starts_with(naics, ?)")
            params.append(self.naics_prefix)
        if self.event_group:
            parts.append("starts_with(event_code, ?)")
            params.append(self.event_group)
        if self.event_text:
            parts.append("contains(lower(event_title), lower(?))")
            params.append(self.event_text)
        if self.event_group_v3:
            parts.append("starts_with(event_code_v3, ?)")
            params.append(self.event_group_v3)
        if self.start:
            parts.append("event_date >= ?")
            params.append(self.start)
        if self.end:
            parts.append("event_date <= ?")
            params.append(self.end)
        return " AND ".join(parts), params


class ReportStore:
    """Read only access to the reports through DuckDB.

    The reports are copied into an in memory table, and then DuckDB's access to files and the
    network is switched off and locked, so a query (one day written by a model) cannot read
    anything else on the machine, such as `read_csv('/etc/passwd')`. Every query runs on its own
    cursor, because parallel report branches query from several threads at once.
    """

    def __init__(self, parquet: Path = REPORTS_PARQUET, codes_v3: Path | None = CODES_V3_PARQUET) -> None:
        if not Path(parquet).exists():
            raise FileNotFoundError(f"{parquet} is missing; run `safereport build-data` first")
        self.con = duckdb.connect()
        self.con.read_parquet(str(parquet)).create("raw_reports")
        if codes_v3 is not None and Path(codes_v3).exists():
            self.con.read_parquet(str(codes_v3)).create("codes_v3")
            self.con.execute(
                "CREATE TABLE reports AS SELECT * FROM raw_reports LEFT JOIN codes_v3 USING (id)"
            )
            self.con.execute("DROP TABLE codes_v3")
        else:
            self.con.execute(
                "CREATE TABLE reports AS SELECT *, CAST(NULL AS VARCHAR) AS event_code_v3, "
                "CAST(NULL AS DOUBLE) AS event_v3_confidence, CAST(NULL AS BOOLEAN) AS event_v3_estimated "
                "FROM raw_reports"
            )
        self.con.execute("DROP TABLE raw_reports")
        self.con.execute("SET enable_external_access = false")
        self.con.execute("SET lock_configuration = true")

    def frame(self, sql: str, params: list[object] | None = None) -> pd.DataFrame:
        """Run a SELECT and return a DataFrame. Anything other than one read query is refused."""
        # DuckDB's own parser decides what the statement is: "WITH x AS (...) DELETE ..." starts
        # like a query but is a DELETE, so a prefix check is not enough.
        try:
            statements = self.con.cursor().extract_statements(sql)
        except duckdb.Error as error:
            raise ValueError(f"only a single SELECT query is allowed: {error}") from error
        if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
            raise ValueError("only a single SELECT query is allowed")
        return self.con.cursor().execute(sql, params or []).df()

    def check_coding(self, filters: Filters) -> None:
        """Refuse an event filter tied to one OIICS version over reports coded with both."""
        if (
            filters.event_group_v3
            and not self.con.cursor()
            .execute("SELECT count(*) FROM reports WHERE event_code_v3 IS NOT NULL")
            .fetchone()[0]
        ):
            raise MixedCodingError("event_group_v3 needs the recoded events; run `safereport train-baseline`")
        if not (filters.event_group or filters.event_text):
            return
        period = Filters(
            state=filters.state, naics_prefix=filters.naics_prefix, start=filters.start, end=filters.end
        )
        where, params = period.where()
        versions = (
            self.con.cursor()
            .execute(
                f"SELECT DISTINCT oiics_version FROM reports WHERE {where}",  # noqa: S608 (fixed fragments, parameter values)
                params,
            )
            .fetchall()
        )
        if len(versions) > 1:
            raise MixedCodingError(
                "event codes and titles mean different things before and after January 2024 (OIICS 2 and 3); "
                "limit the period to one side of 2024, or use event_group_v3, which is estimated before 2024"
            )

    def count(self, filters: Filters | None = None) -> int:
        filters = filters or Filters()
        self.check_coding(filters)
        where, params = filters.where()
        query = f"SELECT count(*) FROM reports WHERE {where}"  # noqa: S608 (fixed fragments, parameter values)
        return int(self.con.cursor().execute(query, params).fetchone()[0])

    def last_date(self) -> date:
        return self.con.cursor().execute("SELECT max(event_date) FROM reports").fetchone()[0]

    def report(self, report_id: str) -> Report:
        rows = self.frame("SELECT * FROM reports WHERE id = ?", [report_id])
        if rows.empty:
            raise KeyError(f"no report with id {report_id}")
        row = rows.iloc[0]
        return Report(**{name: row[name] for name in Report.model_fields if name in row.index})

    def yearly_trend(self, filters: Filters | None = None) -> pd.DataFrame:
        """Reports per year, with a like for like column for partial years.

        The data ends before the year does (30 November 2025), so a plain yearly count makes the
        last year look smaller than it is. `same_months` counts every year over the months the
        last year covers, and `change` compares each year with the one before on that basis.
        """
        filters = filters or Filters()
        self.check_coding(filters)
        where, params = filters.where()
        last = self.last_date()
        trend = self.frame(
            f"SELECT year, count(*) AS reports, count(*) FILTER (WHERE month <= ?) AS same_months, "  # noqa: S608 (fixed fragments, parameter values)
            f"count(DISTINCT month) AS months, any_value(oiics_version) AS oiics_version, "
            f"avg(CASE WHEN event_v3_estimated THEN 1.0 ELSE 0.0 END) AS estimated_share "
            f"FROM reports WHERE {where} GROUP BY year ORDER BY year",
            [last.month, *params],
        )
        # A year without reports is a zero, not a gap: otherwise the change after it is measured
        # against an older year and the empty year disappears.
        first = int(self.con.cursor().execute("SELECT min(year) FROM reports").fetchone()[0])
        trend = trend.set_index("year").reindex(range(first, last.year + 1)).rename_axis("year").reset_index()
        for column in ("reports", "same_months", "months"):
            trend[column] = trend[column].fillna(0).astype(int)
        trend["oiics_version"] = np.where(trend["year"] >= OIICS_3_FROM_YEAR, 3, 2)
        trend["estimated_share"] = trend["estimated_share"].fillna(0.0)
        trend["partial"] = trend["year"].eq(last.year) & (last.month < 12)
        previous = trend["same_months"].shift()
        trend["change"] = (trend["same_months"] - previous) / previous.where(previous > 0)
        return trend

    def reports_between(self, start: date, end: date, state: str = "") -> pd.DataFrame:
        """A replayed week (or any period) of reports, for batch triage."""
        where, params = Filters(state=state, start=start, end=end).where()
        return self.frame(f"SELECT * FROM reports WHERE {where} ORDER BY event_date, id", params)  # noqa: S608 (fixed fragments, parameter values)
