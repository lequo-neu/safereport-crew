from __future__ import annotations

from pathlib import Path

import pytest

from safereport.ecfr import ECFR_DIR, CitationIndex, parse_part
from safereport.labels import load_answer_key


PART_1910 = ECFR_DIR / "title-29-part-1910.xml"

SAMPLE = """<?xml version="1.0"?>
<DIV5 N="1910" TYPE="PART">
<DIV8 N="1910.99" TYPE="SECTION">
<HEAD>&#xA7; 1910.99 Sample machines.</HEAD>
<P>(a) <I>Scope</I>&#x2014;(1) <I>Coverage.</I> (i) This section covers sample machines.</P>
<P>(ii) It also covers their guards.</P>
<P>(h) Eighth item.</P>
<P>(i) Ninth item, a letter and not a roman numeral.</P>
<P>(b) <I>Devices.</I> (1) Devices shall meet the following requirements:</P>
<P>(A) <I>Durable.</I> (<I>1</I>) Devices shall withstand the environment.</P>
<P>(<I>2</I>) Tags shall stay legible.</P>
</DIV8>
<DIV9 N="Appendix A" TYPE="APPENDIX"><P>(a) Appendix text is left out.</P></DIV9>
</DIV5>
"""


def test_markers_nest_and_italics_are_their_own_level(tmp_path: Path):
    xml = tmp_path / "part.xml"
    xml.write_text(SAMPLE, encoding="utf-8")
    paragraphs = parse_part(xml)
    assert [p.citation for p in paragraphs] == [
        "1910.99(a)(1)(i)",
        "1910.99(a)(1)(ii)",
        "1910.99(h)",
        "1910.99(i)",
        "1910.99(b)(1)",
        "1910.99(b)(1)(A)(1)",
        "1910.99(b)(1)(A)(2)",
    ]
    assert paragraphs[0].section_title == "Sample machines."
    assert paragraphs[6].text == "(2) Tags shall stay legible."
    assert paragraphs[1].parent_text.startswith("(a) Scope")
    assert all(p.exact for p in paragraphs)


def test_a_roman_numeral_at_the_top_level_is_marked_doubtful(tmp_path: Path):
    xml = tmp_path / "part.xml"
    xml.write_text(
        '<DIV5><DIV8 N="1910.98" TYPE="SECTION"><HEAD>§ 1910.98 Old style.</HEAD>'
        "<P>(ii) A numeral with no parent.</P><P>(a) A letter.</P></DIV8></DIV5>",
        encoding="utf-8",
    )
    paragraphs = parse_part(xml)
    assert [(p.citation, p.exact) for p in paragraphs] == [("1910.98(ii)", False), ("1910.98(a)", True)]


def test_ambiguous_letters_follow_the_next_marker(tmp_path: Path):
    xml = tmp_path / "part.xml"
    xml.write_text(
        '<DIV5><DIV8 N="1910.97" TYPE="SECTION"><HEAD>§ 1910.97 Mixed.</HEAD>'
        "<P>(h) <I>Eighth</I>—(1) <I>One.</I> (i) A numeral, since (ii) follows.</P>"
        "<P>(ii) Second numeral.</P>"
        "<P>(i) <I>Ninth letter</I>—(1) A letter, since (1) follows.</P>"
        "<P>(b) <I>Overflow.</I> When must I pipe it? (1) After a question mark.</P>"
        "<P>(c) <I>Presence sensing (PSDI)</I>—(1) After a parenthesis.</P></DIV8></DIV5>",
        encoding="utf-8",
    )
    assert [p.citation for p in parse_part(xml)] == [
        "1910.97(h)(1)(i)",
        "1910.97(h)(1)(ii)",
        "1910.97(i)(1)",
        "1910.97(b)(1)",
        "1910.97(c)(1)",
    ]


def test_parents_and_sections_are_citations_too(tmp_path: Path):
    xml = tmp_path / "part.xml"
    xml.write_text(SAMPLE, encoding="utf-8")
    index = CitationIndex(parse_part(xml))
    for citation in ("1910.99", "1910.99(a)", "1910.99(a)(1)", "1910.99(a)(1)(ii)", "1910.99(b)(1)(A)"):
        assert index.exists(citation), citation
    assert not index.exists("1910.99(z)") and not index.exists("1910.98")
    assert index.text("1910.99(a)(1)").startswith("(a) Scope")
    assert index.exact("1910.99(a)")


needs_part = pytest.mark.skipif(not PART_1910.exists(), reason="download eCFR Part 1910 first (see README)")


@needs_part
def test_every_citation_in_the_answer_key_exists_in_part_1910():
    index = CitationIndex(parse_part(PART_1910))
    for case in load_answer_key():
        if case.has_standard:
            assert index.exists(case.primary_standard), f"{case.case}: {case.primary_standard}"
            assert index.exact(case.primary_standard), f"{case.case}: doubtful path"
        for section in case.accepted_sections:
            assert index.exists(section), f"{case.case}: {section}"


@needs_part
def test_a_parent_citation_reads_its_children():
    index = CitationIndex(parse_part(PART_1910))
    assert index.exists("1910.28(b)(1)") and index.exists("1910.179(n)")
    assert "unprotected side or edge" in index.text("1910.28(b)(1)")
    assert not index.exists("1910.28(b)(99)")
