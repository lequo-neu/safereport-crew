"""Split an eCFR part into citable paragraphs.

The eCFR XML gives each section as a DIV8 and each paragraph as a P whose text starts with its
marker, for example "(a) Machine guarding—(1) Types of guarding. ...". CFR paragraphs nest in
a fixed order of marker styles: (a), (1), (i), (A), then italic (1) and italic (i). A stack of
the styles seen so far gives every paragraph its full citation, such as 1910.212(a)(3)(ii).
"""

from __future__ import annotations

from dataclasses import dataclass
import gzip
from pathlib import Path
import re
import urllib.request

from defusedxml import ElementTree

from safereport.config import PROJECT_ROOT


ECFR_DIR = PROJECT_ROOT / "data" / "raw" / "ecfr"
ECFR_DATE = "2026-11-10"
ECFR_URL = "https://www.ecfr.gov/api/versioner/v1/full/{date}/title-29.xml?part={part}"
SECTION_URL = "https://www.ecfr.gov/current/title-29/section-{section}"

ROMAN = re.compile(r"^(?=[ivxl]+$)l?x{0,3}(ix|iv|v?i{0,3})$")
# Markers are written "(a)"; an italic marker is flagged as "(*1)" by `_marked_text`.
MARKER = re.compile(r"^\s*\((\*?[A-Za-z0-9]{1,6})\)\s*")
# A heading ending in a dash or a period, then the marker of a child paragraph.
# Also "(b) When must I provide overflow piping? (1) ...", "(a)(1) Certain ...", and headings
# with a parenthesis that is not a marker, such as "(h) Presence sensing device initiation (PSDI)—(1)".
HEADING = r"(?:[^()]|\((?![ivxl]+\))[^()]{3,40}\))"
CHILD_MARKER = re.compile(rf"^(?:{HEADING}{{0,160}}?(?:—|\.|\?)\s*|\s*)\((\*?[A-Za-z0-9]{{1,6}})\)\s+")


@dataclass
class Paragraph:
    section: str
    section_title: str
    citation: str
    text: str
    parent_text: str
    # False when the paragraph path is doubtful: a roman numeral at the top level or a citation
    # used twice in the section. It happens in a few old style sections (1910.106, .110, .269,
    # .109, .6, .180, .399); such a paragraph is cited by its section only.
    exact: bool = True

    @property
    def url(self) -> str:
        return SECTION_URL.format(section=self.section)


def _roman_value(marker: str) -> int:
    values = {"i": 1, "v": 5, "x": 10, "l": 50}
    total = 0
    for current, following in zip(marker, [*marker[1:], ""], strict=True):
        value = values[current]
        total += -value if following and values[following] > value else value
    return total


def _style(marker: str, italic: bool, stack: list[tuple[str, str]], following: str = "") -> str:
    """The marker style, settling whether a letter such as (i) or (v) is a letter or a roman numeral.

    The marker that comes next decides most cases: (i) followed by (ii) or by (A) is a numeral,
    (i) followed by (j) or by (1) is a letter. Without that, the markers already open decide.
    """
    if marker.isdigit():
        return "italic_digit" if italic else "digit"
    if marker.isupper():
        return "upper"
    if italic:
        return (
            "italic_roman"
            if ROMAN.match(marker) and any(s == "italic_digit" for s, _ in stack)
            else "italic_lower"
        )
    if not ROMAN.match(marker):
        return "lower"
    following = following.lstrip("*")
    if following:
        if len(marker) == len(following) == 1 and ord(following) == ord(marker) + 1:
            return "lower"
        if ROMAN.match(following) and _roman_value(following) == _roman_value(marker) + 1:
            return "roman"
        if following.isupper():
            return "roman"
        if following == "1":
            return "lower"
    styles = dict(stack)
    if "roman" in styles and _roman_value(marker) == _roman_value(styles["roman"]) + 1:
        return "roman"
    if (
        "lower" in styles
        and len(marker) == len(styles["lower"]) == 1
        and ord(marker) == ord(styles["lower"]) + 1
    ):
        return "lower"
    if marker == "i" and stack and stack[-1][0] in ("digit", "roman", "upper", "italic_digit"):
        return "roman"
    if "roman" in styles or (stack and stack[-1][0] == "digit"):
        return "roman"
    return "lower"


# CFR paragraphs always nest in this order, so a marker closes every open level at or below its own.
LEVELS = {
    "lower": 0,
    "digit": 1,
    "roman": 2,
    "upper": 3,
    "italic_digit": 4,
    "italic_lower": 5,
    "italic_roman": 5,
}


def _push(stack: list[tuple[str, str]], style: str, marker: str) -> None:
    level = LEVELS[style]
    while stack and LEVELS[stack[-1][0]] >= level:
        stack.pop()
    stack.append((style, marker))


def _text(element) -> str:
    return " ".join("".join(element.itertext()).split())


def _marked_text(element) -> str:
    """The paragraph text, with italic markers such as (<I>1</I>) written as (*1)."""
    pieces = [element.text or ""]
    for child in element:
        inner = "".join(child.itertext())
        italic_marker = (
            child.tag == "I"
            and re.fullmatch(r"[A-Za-z0-9]{1,6}", inner or "")
            and pieces[-1].endswith("(")
            and (child.tail or "").startswith(")")
        )
        pieces += [("*" + inner) if italic_marker else inner, child.tail or ""]
    return " ".join("".join(pieces).split())


def _leading_markers(text: str) -> list[str]:
    """The markers a paragraph opens with: "(a) Scope—(1) Scope. (i) ..." gives a, 1, i."""
    match = MARKER.match(text)
    if not match:
        return []
    markers, rest = [match.group(1)], text[match.end() :]
    while child := CHILD_MARKER.match(rest):
        markers.append(child.group(1))
        rest = rest[child.end() :]
    return markers


def parse_part(xml_path: Path) -> list[Paragraph]:
    """Every paragraph of every section in the part, appendices left out."""
    root = ElementTree.parse(xml_path).getroot()
    paragraphs: list[Paragraph] = []
    for div in root.iter("DIV8"):
        if div.get("TYPE") != "SECTION":
            continue
        section = div.get("N", "")
        head = div.find("HEAD")
        title = re.sub(r"^§+\s*[\d.]+\s*", "", _text(head)) if head is not None else section
        stack: list[tuple[str, str]] = []
        texts: dict[tuple[str, ...], str] = {}
        items = [(marked, _leading_markers(marked)) for p in div.findall("P") if (marked := _marked_text(p))]
        sequence = [marker for _, markers in items for marker in markers]
        position = 0
        for marked, markers in items:
            for marker in markers:
                position += 1
                following = sequence[position] if position < len(sequence) else ""
                italic = marker.startswith("*")
                plain = marker.lstrip("*")
                _push(stack, _style(plain, italic, stack, following), plain)
            text = marked.replace("(*", "(")
            path = tuple(m for _, m in stack)
            citation = section + "".join(f"({m})" for m in path)
            # A paragraph that opens several levels at once is the text of each of them.
            for depth in range(len(path) - len(markers) + 1, len(path) + 1):
                texts[path[:depth]] = text
            parent = texts.get(path[:-1], "") if len(path) > 1 else ""
            if paragraphs and paragraphs[-1].citation == citation:
                paragraphs[-1].text += " " + text
                continue
            paragraphs.append(Paragraph(section, title, citation, text, parent))
    _mark_doubtful(paragraphs)
    return paragraphs


def _mark_doubtful(paragraphs: list[Paragraph]) -> None:
    counts: dict[str, int] = {}
    for paragraph in paragraphs:
        counts[paragraph.citation] = counts.get(paragraph.citation, 0) + 1
    top_roman = re.compile(r"^\d{4}\.\d+\((?:ii|iii|iv|v|vi|vii|viii|ix|x)\)")
    for paragraph in paragraphs:
        if counts[paragraph.citation] > 1 or top_roman.match(paragraph.citation):
            paragraph.exact = False


def _prefixes(citation: str) -> list[str]:
    """1910.28(b)(1)(i) gives 1910.28, 1910.28(b), 1910.28(b)(1) and 1910.28(b)(1)(i)."""
    section = citation.split("(", 1)[0]
    markers = re.findall(r"\([^()]+\)", citation[len(section) :])
    return [section + "".join(markers[:depth]) for depth in range(len(markers) + 1)]


class CitationIndex:
    """Every way a rule can be cited: a section, a paragraph, or a paragraph's parent.

    A parent such as 1910.28(b)(1) has no paragraph of its own in the XML (its heading opens
    the first child, 1910.28(b)(1)(i)), yet it is a correct citation, and seven cases of the
    answer key use one. The citation check of the critic asks this index, not the paragraph list.
    """

    def __init__(self, paragraphs: list[Paragraph]) -> None:
        self.under: dict[str, list[Paragraph]] = {}
        for paragraph in paragraphs:
            for prefix in _prefixes(paragraph.citation):
                self.under.setdefault(prefix, []).append(paragraph)

    def exists(self, citation: str) -> bool:
        return citation.strip() in self.under

    def exact(self, citation: str) -> bool:
        """False when any paragraph under the citation has a doubtful path.

        A section alone is always exact: its number does not depend on how paragraphs nest.
        """
        citation = citation.strip()
        if not self.exists(citation):
            return False
        return "(" not in citation or all(p.exact for p in self.under[citation])

    def text(self, citation: str, limit: int = 4000) -> str:
        """The official words of a citation: its paragraph, or the paragraphs under a parent."""
        paragraphs = self.under.get(citation.strip(), [])
        return " ".join(p.text for p in paragraphs)[:limit]


def download_part(part: str = "1910", date: str = ECFR_DATE, folder: Path = ECFR_DIR) -> Path:
    """Fetch one part of Title 29 from the public eCFR API (no key needed) as of `date`.

    The API only answers compressed requests, so the request asks for gzip and unpacks it.
    """
    folder.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(  # noqa: S310 (a fixed https URL on ecfr.gov)
        ECFR_URL.format(date=date, part=part),
        headers={"Accept-Encoding": "gzip", "User-Agent": "safereport-course-project/0.1"},
    )
    with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310
        body = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
    if not body.lstrip().startswith(b"<?xml") or b"<error>" in body[:200]:
        raise RuntimeError(f"eCFR did not return Part {part}: {body[:200]!r}")
    path = folder / f"title-29-part-{part}.xml"
    path.write_bytes(body)
    return path
