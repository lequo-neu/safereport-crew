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


def sensitivity_chart(rows: list[dict], current: float | None = None, floor: float | None = None) -> bytes:
    """What each added inspector day buys, with this week's days and the Category 1 minimum marked."""
    figure = Figure(figsize=(6, 3), dpi=120)
    axes = figure.subplots()
    axes.plot([r["capacity"] for r in rows], [r["priority_covered"] for r in rows], color=INK, marker="o")
    if floor:
        axes.axvline(floor, color=ACCENT, linestyle=":", linewidth=1.2)
        axes.annotate(f"Category 1 needs {floor:g}", (floor, 0.04), xycoords=("data", "axes fraction"),
                      xytext=(4, 0), textcoords="offset points", color=ACCENT, fontsize=8)  # fmt: skip
    if current is not None:
        axes.axvline(current, color=MUTED, linewidth=1.2)
        axes.annotate(f"this week {current:g}", (current, 0.92), xycoords=("data", "axes fraction"),
                      xytext=(4, 0), textcoords="offset points", color=MUTED, fontsize=8)  # fmt: skip
    axes.set_xlabel("inspector days")
    axes.set_ylabel("priority covered")
    axes.spines[["top", "right"]].set_visible(False)
    return _png(figure)


def pareto_front(points: list[dict]) -> list[dict]:
    """The points no other point beats on both cost and accuracy, cheapest first."""
    front, best = [], -1.0
    for point in sorted(points, key=lambda p: (p["cost"], -p["accuracy"])):
        if point["accuracy"] > best:
            front.append(point)
            best = point["accuracy"]
    return front


def pareto_chart(points: list[dict], measure: str = "standards found in the top 3") -> bytes:
    """Cost of one run over the answer key against accuracy, with the frontier drawn through it."""
    figure = Figure(figsize=(8, 3.6), dpi=120)
    axes = figure.subplots()
    front = pareto_front(points)
    axes.plot(
        [p["cost"] for p in front], [p["accuracy"] for p in front], color=MUTED, linestyle="--", linewidth=1
    )
    for point in points:
        on_front = point in front
        axes.scatter([point["cost"]], [point["accuracy"]], s=60, zorder=3,
                     color=INK if on_front else "white", edgecolors=INK)  # fmt: skip
        low, high = point.get("ci95", (point["accuracy"], point["accuracy"]))
        axes.vlines(point["cost"], low, high, color=MUTED, linewidth=1, zorder=2)
        axes.annotate(point["label"], (point["cost"], point["accuracy"]), textcoords="offset points",
                      xytext=(8, -3), fontsize=8, color=INK)  # fmt: skip
    axes.set_xlabel("dollars per run over the key")
    # Room on the right for the label of the dearest point.
    axes.set_xlim(-0.05 * max(p["cost"] for p in points) - 1e-4, 1.35 * max(p["cost"] for p in points) + 1e-4)
    axes.set_ylabel(measure)
    axes.set_ylim(0, 1)
    axes.yaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
    axes.spines[["top", "right"]].set_visible(False)
    return _png(figure)


def router_pareto_chart(points: list[dict]) -> bytes:
    """B7/B8 cost and accuracy on the same 35 eligible reports.

    Identical cost and accuracy coordinates share one label and
    frontier position. A ring identifies the router replay.
    """
    figure = Figure(figsize=(9, 4.8), dpi=150)
    axes = figure.subplots()

    groups = {}

    for point in points:
        key = (point["cost"], point["accuracy"])
        groups.setdefault(key, []).append(point)

    unique = [group[0] for group in groups.values()]
    front = pareto_front(unique)

    frontier_coordinates = {(point["cost"], point["accuracy"]) for point in front}

    axes.plot(
        [point["cost"] for point in front],
        [point["accuracy"] for point in front],
        color=MUTED,
        linestyle="--",
        linewidth=1.2,
        label="Pareto frontier",
    )

    router_label_added = False

    for (cost, accuracy), group in groups.items():
        on_front = (cost, accuracy) in frontier_coordinates

        axes.scatter(
            [cost],
            [accuracy],
            s=55,
            color=INK if on_front else "white",
            edgecolors=INK,
            zorder=3,
        )

        low, high = group[0]["ci95"]

        axes.errorbar(
            cost,
            accuracy,
            yerr=[[accuracy - low], [high - accuracy]],
            fmt="none",
            ecolor=MUTED,
            elinewidth=1.2,
            capsize=4,
            zorder=2,
        )

        has_router = any(point["model"] == "router" for point in group)

        if has_router:
            axes.scatter(
                [cost],
                [accuracy],
                s=180,
                facecolors="none",
                edgecolors=ACCENT,
                linewidths=1.8,
                zorder=4,
                label=None if router_label_added else "Router replay",
            )
            router_label_added = True

        names = " + ".join(point["label"] for point in group)

        label = f"{names}\\n{accuracy:.1%} | {group[0]['hits']}/{group[0]['cases']} | ${cost:.4f}"

        right_side = cost >= max(point["cost"] for point in points) / 2

        axes.annotate(
            label,
            (cost, accuracy),
            textcoords="offset points",
            xytext=(-12, 22) if right_side else (12, -24),
            ha="right" if right_side else "left",
            va="bottom" if right_side else "top",
            fontsize=8,
            color=INK,
        )

    max_cost = max(point["cost"] for point in points)

    axes.set_xlim(
        -0.08 * max_cost - 1e-4,
        1.18 * max_cost + 1e-4,
    )

    axes.set_ylim(0, 1)

    axes.set_xlabel("Historical cost per 35-case evaluation (USD)")

    axes.set_ylabel("Strict standards retrieval Hit@3")

    axes.xaxis.set_major_formatter(lambda value, _: f"${value:.2f}")

    axes.yaxis.set_major_formatter(lambda value, _: f"{value:.0%}")

    axes.set_title(
        "B7/B8: retrieval cost and accuracy",
        loc="left",
        fontsize=12,
        color=INK,
        fontweight="bold",
        pad=14,
    )

    axes.grid(
        axis="y",
        color=MUTED,
        alpha=0.18,
        linewidth=0.7,
    )

    axes.spines[["top", "right"]].set_visible(False)

    axes.legend(
        loc="upper left",
        frameon=False,
        fontsize=8,
    )

    figure.text(
        0.02,
        0.015,
        "Wilson 95% intervals. Retrospective router replay; "
        "no new inference cost. Gemini and Gemma unmeasured.",
        fontsize=8,
        color=INK,
    )

    figure.tight_layout(rect=(0, 0.07, 1, 1))

    buffer = io.BytesIO()
    figure.savefig(buffer, format="png")
    return buffer.getvalue()


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


# Fonts Word has on Windows and macOS for each script; Latin text keeps the template's own.
EAST_ASIAN_FONT = "Microsoft YaHei"
COMPLEX_SCRIPT_FONT = "Arial"
WORD_LANGUAGE = {"en": "en-US", "es": "es-US", "zh": "zh-CN", "tl": "fil-PH", "vi": "vi-VN", "ar": "ar-SA"}
# The paragraph properties that come after w:bidi in the schema, so w:bidi goes in its place.
BIDI_SUCCESSORS = (
    "w:adjustRightInd", "w:snapToGrid", "w:spacing", "w:ind", "w:contextualSpacing", "w:mirrorIndents",
    "w:suppressOverlap", "w:jc", "w:textDirection", "w:textAlignment", "w:textboxTightWrap",
    "w:outlineLvl", "w:divId", "w:cnfStyle", "w:rPr", "w:sectPr", "w:pPrChange",
)  # fmt: skip


def word_document(markdown: str, language: str = "en") -> bytes:
    """A Word file from the Writer's text: "#" lines become headings, "*" lines bullets.

    `language` sets the proofing language and the script: Chinese gets an East Asian font, and
    Arabic paragraphs are right to left, so they start at the right margin as the talk should read.
    """
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
    for paragraph in document.paragraphs:
        _script(paragraph, language)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _script(paragraph, language: str) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    right_to_left = language == "ar"
    if right_to_left:
        # w:bidi alone starts the paragraph at the right margin. No w:jc: in a right to left
        # paragraph Word reads "right" as the end side, so it would push the lines left (#23).
        properties = paragraph._p.get_or_add_pPr()
        properties.insert_element_before(OxmlElement("w:bidi"), *BIDI_SUCCESSORS)
    for run in paragraph.runs:
        properties = run._r.get_or_add_rPr()
        fonts = properties.find(qn("w:rFonts"))
        if fonts is None:
            fonts = OxmlElement("w:rFonts")
            properties.insert(0, fonts)
        if language == "zh":
            fonts.set(qn("w:eastAsia"), EAST_ASIAN_FONT)
        if right_to_left:
            fonts.set(qn("w:cs"), COMPLEX_SCRIPT_FONT)
            properties.append(OxmlElement("w:rtl"))
        tag = OxmlElement("w:lang")
        tag.set(qn("w:bidi" if right_to_left else ("w:eastAsia" if language == "zh" else "w:val")),
                WORD_LANGUAGE.get(language, "en-US"))  # fmt: skip
        properties.append(tag)


def _plain(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text)
