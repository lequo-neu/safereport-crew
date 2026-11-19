"""Charts for answers and files to download: CSV lists and Word documents.

Charts use matplotlib's object oriented API (no global pyplot state), so the app can draw
several at once; each returns PNG bytes.
"""

from __future__ import annotations

import csv
import io
import re

from docx import Document as WordDocument
from matplotlib.figure import Figure
import pandas as pd


INK, ACCENT, MUTED = "#1f2a36", "#c0392b", "#8a96a3"


def trend_chart(trend: pd.DataFrame, title: str) -> bytes:
    """Reports per year on a like for like basis; estimated and partial years are marked."""
    figure = Figure(figsize=(7, 3.2), dpi=120)
    axes = figure.subplots()
    years = trend["year"].tolist()
    counts = trend["same_months"].tolist()
    axes.plot(years, counts, color=INK, marker="o", linewidth=2)
    for year, count, estimated in zip(
        years, counts, trend.get("estimated_share", [0] * len(years)), strict=True
    ):
        if estimated and estimated > 0.5:
            axes.plot([year], [count], marker="o", color="white", markeredgecolor=INK, markersize=7)
    if "partial" in trend and trend["partial"].any():
        axes.annotate("same months only", (years[-1], counts[-1]), textcoords="offset points", xytext=(-10, 10),
                      ha="right", color=MUTED, fontsize=8)  # fmt: skip
    axes.set_title(title, loc="left", fontsize=10, color=INK)
    axes.set_ylabel("reports")
    axes.spines[["top", "right"]].set_visible(False)
    axes.set_ylim(bottom=0)
    return _png(figure)


def sensitivity_chart(rows: list[dict]) -> bytes:
    """What each added inspector day buys."""
    figure = Figure(figsize=(6, 3), dpi=120)
    axes = figure.subplots()
    axes.plot([r["capacity"] for r in rows], [r["priority_covered"] for r in rows], color=INK, marker="o")
    axes.set_xlabel("inspector days")
    axes.set_ylabel("priority covered")
    axes.spines[["top", "right"]].set_visible(False)
    return _png(figure)


def _png(figure: Figure) -> bytes:
    figure.tight_layout()
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png")
    return buffer.getvalue()


def triage_csv(rows: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]) if rows else ["report_id"])
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def word_document(markdown: str) -> bytes:
    """A Word file from the Writer's text: "#" lines become headings, "*" lines bullets."""
    document = WordDocument()
    for line in markdown.splitlines():
        if line.startswith("# "):
            document.add_heading(line[2:].strip(), level=1)
        elif line.startswith("* "):
            document.add_paragraph(_plain(line[2:]), style="List Bullet")
        elif line.startswith("> "):
            document.add_paragraph(_plain(line[2:]), style="Intense Quote")
        elif line.strip():
            document.add_paragraph(_plain(line))
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _plain(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text)
