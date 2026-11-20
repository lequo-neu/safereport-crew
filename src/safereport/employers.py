"""Find an employer's earlier reports when its name is spelled many ways.

The reports hold 70,593 employer strings; Walmart alone appears under 340 of them. Names are
normalized, then compared with rapidfuzz only within the same state. A match is "same" when
the normalized names are identical (or a person said so) and the site or the industry confirms
it; every fuzzy match is "possible". Near names are often rivals in the same trade ("Bass
Energy Services" and "Basic Energy Services" score 93), and a possible match never counts as a
repeat until a person confirms it, because a repeat can force an inspection under OSHA's
Category 1 rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
import re
import sqlite3
from typing import Literal

import pandas as pd
from rapidfuzz import fuzz, process


LEGAL_WORDS = {
    "inc",
    "incorporated",
    "llc",
    "l l c",
    "co",
    "corp",
    "corporation",
    "company",
    "ltd",
    "limited",
    "lp",
    "llp",
    "plc",
    "the",
    "dba",
}
SAME_NAME = 92  # token sort ratio of a near spelling ("Walmart Inc" and "Wal Mart Inc"); still only possible
POSSIBLE_NAME = 90  # token set ratio at or above which they may be the same employer
# A name that is one of these words alone says what a company does, not who it is: "Steel Co Inc"
# holds every word of "Steel Dynamics", so the token set score alone would call them a match.
GENERIC_NAMES = frozenset(
    [
        "steel",
        "metal",
        "metals",
        "plastics",
        "manufacturing",
        "construction",
        "services",
        "industries",
        "products",
        "foods",
        "supply",
        "logistics",
        "solutions",
        "systems",
        "builders",
        "contractors",
        "group",
        "enterprises",
        "company",
        "corporation",
        "holdings",
        "transport",
        "trucking",
        "farms",
        "roofing",
        "electric",
        "plumbing",
        "concrete",
        "lumber",
        "packaging",
        "fabrication",
        "machine",
        "tool",
        "american",
        "national",
        "united",
        "general",
        "southern",
        "northern",
        "western",
        "eastern",
    ]
)

Level = Literal["site", "company"]
Status = Literal["same", "possible"]


def normalize_name(name: str) -> str:
    """Lower case, no punctuation, no legal suffixes: "Tyson Foods, Inc." becomes "tyson foods"."""
    text = name.lower().replace("&", " and ")
    text = re.sub(r"\bu\.\s*s\.", "us", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    words = [w for w in text.split() if w not in LEGAL_WORDS]
    text = " ".join(words)
    return re.sub(r"\bunited states\b", "us", text)


def initials(name: str) -> str:
    """Initials of a normalized name; a two letter word such as "us" keeps both letters."""
    return "".join(w if len(w) == 2 and w.isalpha() else w[0] for w in name.split())


def _is_acronym_of(short: str, long: str) -> bool:
    return " " not in short and 2 <= len(short) <= 6 and len(long.split()) >= 2 and initials(long) == short


@dataclass
class EmployerMatch:
    report_id: str
    employer: str
    city: str
    event_date: date
    level: Level
    status: Status
    score: float
    # The OIICS 3 event code (OSHA's from 2024, estimated before), to tell a similar incident.
    event_code_v3: str = ""


class DecisionStore:
    """Confirmations and rejections of name pairs, kept in SQLite so they outlive a run.

    A decision is stored once per pair of normalized names, so it settles every report that
    carries either spelling, in every state.
    """

    def __init__(self, path: Path | str) -> None:
        self.con = sqlite3.connect(str(path), check_same_thread=False)
        self.con.execute(
            "CREATE TABLE IF NOT EXISTS name_pairs (name_a TEXT, name_b TEXT, same INTEGER, by TEXT, at TEXT, "
            "PRIMARY KEY (name_a, name_b))"
        )
        self.con.commit()

    def save(self, name_a: str, name_b: str, same: bool, by: str = "") -> None:
        a, b = sorted((normalize_name(name_a), normalize_name(name_b)))
        self.con.execute(
            "INSERT OR REPLACE INTO name_pairs VALUES (?, ?, ?, ?, ?)",
            (a, b, int(same), by, datetime.now(UTC).isoformat(timespec="seconds")),
        )
        self.con.commit()

    def load(self) -> dict[frozenset[str], bool]:
        rows = self.con.execute("SELECT name_a, name_b, same FROM name_pairs").fetchall()
        return {frozenset((a, b)): bool(same) for a, b, same in rows}


@dataclass
class EmployerIndex:
    """Employer names by state, built once from the reports."""

    frame: pd.DataFrame
    decisions: dict[frozenset[str], bool] = field(default_factory=dict)
    store: DecisionStore | None = None

    def __post_init__(self) -> None:
        columns = ["id", "employer", "city", "zip", "state", "naics", "event_date"]
        frame = self.frame[columns].copy()
        codes = self.frame.get("event_code_v3")
        frame["event_code_v3"] = codes.fillna("").astype(str) if codes is not None else ""
        frame["state"] = frame["state"].str.upper()
        frame["event_date"] = pd.to_datetime(frame["event_date"]).dt.date
        frame["norm"] = frame["employer"].map(normalize_name)
        self.frame = frame
        self._names = {state: sorted(group["norm"].unique()) for state, group in frame.groupby("state")}
        self._rows = {key: group for key, group in frame.groupby(["state", "norm"])}
        if self.store is not None:
            self.decisions = {**self.store.load(), **self.decisions}

    def decide(self, name_a: str, name_b: str, same: bool, by: str = "") -> None:
        """Record a person's confirmation (same employer) or rejection of a possible match.

        It applies to every report with either spelling, and is saved when the index has a store.
        """
        self.decisions[frozenset((normalize_name(name_a), normalize_name(name_b)))] = same
        if self.store is not None:
            self.store.save(name_a, name_b, same, by)

    def _name_status(self, query: str, candidate: str) -> tuple[Status | None, float]:
        decided = self.decisions.get(frozenset((query, candidate)))
        if decided is not None:
            return ("same" if decided else None), 100.0
        if query == candidate:
            return "same", 100.0
        sort_score = fuzz.token_sort_ratio(query, candidate)
        if sort_score >= SAME_NAME:
            return "possible", sort_score
        set_score = fuzz.token_set_ratio(query, candidate)
        shorter = min(query, candidate, key=len)
        if set_score >= POSSIBLE_NAME and len(shorter) >= 4 and shorter not in GENERIC_NAMES:
            return "possible", set_score
        if _is_acronym_of(query, candidate) or _is_acronym_of(candidate, query):
            return "possible", 90.0
        return None, 0.0

    def history(
        self,
        employer: str,
        state: str,
        city: str = "",
        zip_code: str = "",
        naics: str = "",
        exclude_id: str = "",
    ) -> list[EmployerMatch]:
        """Earlier reports by the same employer in the same state, newest first."""
        state = state.upper()
        query = normalize_name(employer)
        names = self._names.get(state, [])
        if not query or not names:
            return []
        candidates = {
            c
            for c, _, _ in process.extract(
                query, names, scorer=fuzz.token_set_ratio, score_cutoff=80, limit=None
            )
        }
        candidates |= {c for c in names if _is_acronym_of(query, c) or _is_acronym_of(c, query)}
        matches = []
        for candidate in candidates:
            status, score = self._name_status(query, candidate)
            if status is None:
                continue
            for row in self._rows[(state, candidate)].itertuples():
                if row.id == exclude_id:
                    continue
                same_site = bool(zip_code and row.zip == zip_code) or bool(
                    city and row.city.upper() == city.upper()
                )
                level: Level = "site" if same_site else "company"
                row_status = status
                # Away from the site, the same name needs the same industry to count; without an
                # industry to compare there is nothing to confirm it.
                if level == "company" and status == "same" and (not naics or row.naics[:3] != naics[:3]):
                    row_status = "possible"
                matches.append(
                    EmployerMatch(
                        row.id,
                        row.employer,
                        row.city,
                        row.event_date,
                        level,
                        row_status,
                        score,
                        row.event_code_v3,
                    )
                )
        return sorted(matches, key=lambda m: (m.event_date, m.report_id), reverse=True)

    def repeats_within(
        self, employer: str, state: str, on: date, days: int = 365, division: str = "", **site: str
    ) -> list[EmployerMatch]:
        """Confirmed earlier reports within `days` before `on`, the Category 1 history test.

        OSHA's criterion is a history of "the same or similar hazards or incidents", so with a
        `division` (the first digit of the OIICS 3 event code: 4 falls, 6 contact with objects
        and equipment, and so on) only earlier incidents of the same division count.
        """
        start = on - timedelta(days=days)
        return [
            m
            for m in self.history(employer, state, **site)
            if m.status == "same"
            and start <= m.event_date < on
            and (not division or not m.event_code_v3 or m.event_code_v3.startswith(division))
        ]


def repeat_summary(frame: pd.DataFrame) -> tuple[int, int, list[tuple[str, str]]]:
    """Employers with more than one report in `frame`, and near name pairs a person must confirm.

    Returns the number of employers whose normalized name appears more than once, the number of
    possible pairs, and up to 20 of those pairs for the matches panel.
    """
    names = frame["employer"].map(normalize_name)
    counts = names.value_counts()
    repeated = int((counts > 1).sum())
    unique = sorted(n for n in counts.index if n)
    pairs: list[tuple[str, str]] = []
    for position, name in enumerate(unique):
        rest = unique[position + 1 :]
        for other, score, _ in process.extract(
            name, rest, scorer=fuzz.token_set_ratio, score_cutoff=POSSIBLE_NAME, limit=None
        ):
            shorter = min(name, other, key=len)
            if len(shorter) >= 4 and score >= POSSIBLE_NAME:
                pairs.append((name, other))
    return repeated, len(pairs), pairs[:20]
