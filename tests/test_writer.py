from __future__ import annotations

import io
import re
import zipfile

import pandas as pd
import pytest

from safereport.ledger import FactLedger
from safereport.offline import plan_request
from safereport.outputs import sensitivity_chart, trend_chart, triage_csv, word_document
from safereport.writer import TALKS, draft


PAYLOADS = [
    {"kind": "inspection_brief", "hazard": "machine", "activity": "cleaning", "citation": "1910.147", "questions": ["Was it locked out?"]},
    {"kind": "rri_letter", "citation": "1910.212(a)(1)", "questions": ["Was a guard in place?"]},
    {"kind": "trend_answer", "subject": "Reports in Texas", "estimated": True},
    {"kind": "repeat_answer"},
    {"kind": "triage_summary", "infeasible": True},
    {"kind": "plant_memo", "citation": "1910.147"},
    *({"kind": "safety_talk", "topic": topic, "language": language}
      for topic in TALKS for language in ("en", "es", "zh", "tl", "vi", "ar")),
]  # fmt: skip


@pytest.mark.parametrize(
    "payload", PAYLOADS, ids=lambda p: f"{p['kind']}-{p.get('topic', '')}-{p.get('language', '')}"
)
def test_no_template_writes_a_number_by_hand(payload: dict):
    assert FactLedger().untraced(draft(payload)["template"]) == []


def test_rri_letter_asks_the_missing_facts_and_lists_what_is_owed():
    text = draft(
        {"kind": "rri_letter", "citation": "1910.147", "questions": ["Was the machine locked out?"]}
    )["template"]
    assert (
        "Was the machine locked out?" in text
        and "five working days" in text
        and "abatement verification" in text
    )


def test_spanish_talk_is_spanish():
    english = draft({"kind": "safety_talk", "topic": "lockout", "language": "en"})["template"]
    spanish = draft({"kind": "safety_talk", "topic": "lockout", "language": "es"})["template"]
    assert "Bloquee" in spanish and "candado" in spanish and spanish != english


def test_word_and_csv_exports():
    data = word_document("# Title\n\n**Bold** line\n* a bullet\n> a quote")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        body = archive.read("word/document.xml").decode()
    assert "Title" in body and "a bullet" in body and "**" not in body
    assert triage_csv([{"report_id": "1", "decision": "inspection"}]).splitlines() == [
        "report_id,decision",
        "1,inspection",
    ]


def test_charts_are_png():
    trend = pd.DataFrame({"year": [2023, 2024, 2025], "same_months": [5, 7, 6], "estimated_share": [1.0, 0, 0],
                          "partial": [False, False, True]})  # fmt: skip
    assert trend_chart(trend, "t").startswith(b"\x89PNG")
    assert sensitivity_chart(
        [{"capacity": 1, "priority_covered": 2}, {"capacity": 2, "priority_covered": 3}]
    ).startswith(b"\x89PNG")


def test_planner_splits_a_three_task_request_with_dependencies():
    plan = plan_request("Find caught in machinery injuries in Texas since 2022, check which employers reported "
                        "more than once, then plan this week's inspections with 40 inspector days.")  # fmt: skip
    kinds = [t["kind"] for t in plan["tasks"]]
    assert kinds == ["trend", "repeat_employers", "triage"]
    assert plan["tasks"][1]["depends_on"] == ["trend"] and plan["tasks"][2]["depends_on"] == ["repeats"]
    assert plan["params"] == {"state": "TEXAS", "start": "2022-01-01", "hazard_label": "caught in machinery",
                              "event_group_v3": "653", "capacity": 40.0}  # fmt: skip
    assert plan["missing"] == []


def test_planner_lists_missing_parameters():
    assert plan_request("Check which employers reported more than once, then plan this week's inspections.")[
        "missing"
    ] == ["state"]
    assert plan_request("How many injuries in Ohio?")["missing"] == ["start"]
    assert plan_request("hello")["missing"] == ["request"]


def test_a_pasted_narrative_is_one_report():
    plan = plan_request("An employee's hand was pulled into the rollers while clearing a jam.")
    assert [t["kind"] for t in plan["tasks"]] == ["single_report"]


@pytest.mark.parametrize("language", ["es", "zh", "tl", "vi", "ar"])
def test_every_topic_has_its_talk_in_each_language(language):
    from safereport.ledger import FactLedger

    for topic in ("lockout", "machine guarding", "fall", "forklift"):
        english = draft({"kind": "safety_talk", "topic": topic, "language": "en"})["template"]
        text = draft({"kind": "safety_talk", "topic": topic, "language": language})["template"]
        assert text != english and "{{topic_reports}}" in text and "{{since}}" in text
        ledger = FactLedger()
        ledger.add("topic_reports", 2183, "ReportStore")
        ledger.add("since", "2015", "data")
        assert ledger.untraced(text) == [] and ledger.unknown(text) == [], (topic, language)
        assert "2,183" in ledger.render(text)


def test_word_exports_set_the_script_of_each_language():
    import io
    import zipfile

    from safereport.outputs import word_document

    def body(language, text):
        with zipfile.ZipFile(io.BytesIO(word_document(text, language))) as archive:
            return archive.read("word/document.xml").decode("utf-8")

    assert "Khóa nguồn trước khi đưa tay vào" in body("vi", "# Khóa nguồn trước khi đưa tay vào")
    chinese = body("zh", "# 伸手之前先上锁")
    assert "伸手之前先上锁" in chinese and 'w:eastAsia="Microsoft YaHei"' in chinese
    arabic = body("ar", "# اقفل الطاقة قبل أن تمد يدك\n\n* أوقف الآلة")
    assert "<w:bidi/>" in arabic and "<w:rtl/>" in arabic
    # #23: w:bidi alone starts a paragraph at the right margin; w:jc="right" would push it left.
    assert arabic.count("<w:bidi/>") == 2 and "<w:jc " not in arabic
    for paragraph in re.findall(r"<w:pPr>.*?</w:pPr>", arabic):
        assert "<w:bidi/>" in paragraph, "every Arabic paragraph is right to left"
        assert not re.search(r"<w:(spacing|ind|jc|rPr)\b.*<w:bidi/>", paragraph), "w:bidi in schema order"
    assert "<w:bidi/>" not in body("en", "# Lockout")
