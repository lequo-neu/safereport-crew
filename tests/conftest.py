"""Shared fixtures: a small OSHA file in the real format, so data tests run without the download."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from safereport.data import ReportStore, build_parquet


HEADERS = [
    "ID", "UPA", "EventDate", "Employer", "Address1", "Address2", "City", "State", "Zip", "Latitude",
    "Longitude", "Primary NAICS", "Hospitalized", "Amputation", "Loss of Eye", "Inspection",
    "Final Narrative", "Nature", "NatureTitle", "Part of Body", "Part of Body Title", "Event",
    "EventTitle", "Source", "SourceTitle", "Secondary Source", "Secondary Source Title", "FederalState",
]  # fmt: skip

# id, date, employer, city, state, zip, naics, hospitalized, amputation, inspection, event, narrative
ROWS = [
    ("1", "1/10/2024", "Walmart, Inc.", "AUSTIN", "TEXAS", "78701", "452311", "1", "0", "", "4220", "An employee slipped on a wet floor and broke a hip."),
    ("2", "6/15/2024", "Walmart Supercenter", "AUSTIN", "TEXAS", "78701", "452311", "1", "0", "1234567", "4220", "An employee slipped near the freezer aisle."),
    ("3", "12/1/2024", "U.S. Postal Service", "DALLAS", "TEXAS", "75201", "491110", "1", "0", "", "6411", "A carrier's hand was caught in a conveyor."),
    ("4", "2/2/2025", "United States Postal Service", "HOUSTON", "TEXAS", "77001", "491110", "1", "0", "", "6411", "A clerk's finger was caught in a sorting machine."),
    ("5", "3/3/2025", "USPS", "DALLAS", "TEXAS", "75201", "491110", "1", "0", "", "6411", "A worker's arm was pulled into a belt."),
    ("6", "4/4/2025", "Acme Laminates LLC", "DAYTON", "OHIO", "45402", "326130", "0", "1", "7654321", "6411", "An employee of Acme Laminates had a fingertip amputated by the rollers while cleaning."),
    ("7", "5/5/2025", "Smith Construction", "DAYTON", "OHIO", "45402", "236220", "1", "0", "", "4330", "A worker fell 12 feet from a ladder."),
    ("8", "6/6/2025", "Smith", "DAYTON", "OHIO", "45402", "332710", "1", "0", "", "4330", "A worker fell from a platform."),
    ("9", "6/20/2025", "Walmart", "TOLEDO", "OHIO", "43604", "452311", "1", "0", "", "4220", "An employee tripped over a pallet."),
]  # fmt: skip


def write_sir_csv(path: Path, rows=ROWS) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        for rid, day, employer, city, state, zip_code, naics, hosp, amp, insp, event, narrative in rows:
            writer.writerow(
                {
                    **dict.fromkeys(HEADERS, ""),
                    "ID": rid,
                    "EventDate": f"{day} 0:00",
                    "Employer": employer,
                    "Address1": "1 Main Street",
                    "City": city,
                    "State": state,
                    "Zip": zip_code,
                    "Primary NAICS": naics,
                    "Hospitalized": hosp,
                    "Amputation": amp,
                    "Loss of Eye": "0",
                    "Inspection": insp,
                    "Final Narrative": narrative,
                    "Event": event,
                    "EventTitle": "Event title",
                    "Source": "3500",
                    "SourceTitle": "Source title",
                }
            )
    return path


@pytest.fixture
def small_store(tmp_path: Path) -> ReportStore:
    csv_path = write_sir_csv(tmp_path / "sir.csv")
    build_parquet(csv_path, tmp_path / "reports.parquet", tmp_path / "holdout.csv", holdout_size=2)
    return ReportStore(tmp_path / "reports.parquet", codes_v3=None)


@pytest.fixture
def small_services(small_store: ReportStore):
    """The crew's services on the small file, tiny indexes and a tiny baseline: no download needed."""
    from datetime import date

    from safereport import offline
    from safereport.baseline import EventBaseline
    from safereport.config import load_model_settings
    from safereport.ecfr import CitationIndex, Paragraph
    from safereport.graph import Services
    from safereport.retrieval import Document, IndexRegistry, Retriever
    from safereport.router import offline_router

    rules = [
        ("1910.147", "The control of hazardous energy (lockout/tagout).", "1910.147(c)(4)(i)",
         "(4) Energy control procedure. (i) Procedures shall be developed for the control of hazardous energy during servicing and maintenance of machines."),
        ("1910.212", "General requirements for all machines.", "1910.212(a)(1)",
         "(a) Machine guarding—(1) Types of guarding. Guarding shall protect the operator from in-running nip points, rotating parts and the point of operation."),
        ("1910.23", "Ladders.", "1910.23(b)(1)", "(b) Ladder rungs, steps and cleats are parallel, level and uniformly spaced."),
        ("1910.178", "Powered industrial trucks.", "1910.178(l)(1)(i)", "(l) Operator training. (1) Safe operation. (i) Forklift operators shall be trained."),
        ("1910.22", "General requirements.", "1910.22(a)(1)", "(a) Surface conditions. (1) Walking-working surfaces are kept free of hazards such as slippery floors and trip hazards."),
    ]  # fmt: skip
    paragraphs = [Paragraph(section, title, citation, text, "") for section, title, citation, text in rules]
    part = [
        Document(f"d{n}", "1910", p.citation, p.section, p.section_title, p.text)
        for n, p in enumerate(paragraphs)
    ]
    nep = [Document("n1", "emphasis_program", "CPL 03-00-027", "CPL 03-00-027", "Amputations", "amputation",
                    industries=["31", "32", "33"], triggers=["amputat"])]  # fmt: skip
    gdc = [
        Document(
            "g",
            "general_duty",
            "OSH Act 5(a)(1)",
            "OSH Act 5(a)(1)",
            "General Duty Clause",
            "recognized hazards",
        )
    ]
    registry = IndexRegistry(
        {"1910": Retriever(part), "emphasis_program": Retriever(nep), "general_duty": Retriever(gdc)}
    )
    texts = [
        "hand caught in rollers while cleaning",
        "fell from a ladder",
        "slipped on a wet floor",
        "arm pulled into a belt",
    ]
    baseline = EventBaseline(max_features=200, alpha=1e-4).fit(
        texts * 3, ["6411", "4330", "4220", "6411"] * 3
    )
    settings = load_model_settings()
    return Services(
        store=small_store, registry=registry, citations=CitationIndex(paragraphs), baseline=baseline,
        router=offline_router(settings, offline.handlers()), settings=settings,
        week=(date(2024, 1, 1), date(2025, 12, 31)), capacity=5.0,
    )  # fmt: skip
