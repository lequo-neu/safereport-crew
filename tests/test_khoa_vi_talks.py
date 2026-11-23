"""B5: Vietnamese safety talks keep the essential instructions and data placeholders."""

from safereport.talk_languages import LEADS, TRANSLATIONS


def test_vi_talks_preserve_required_topics_and_safety_messages():
    assert set(TRANSLATIONS) >= {"lockout", "machine guarding", "fall", "forklift"}
    vi = {topic: TRANSLATIONS[topic]["vi"] for topic in ("lockout", "machine guarding", "fall", "forklift")}
    assert "năng lượng tích trữ" in " ".join(vi["lockout"]["points"])
    assert "thẻ cảnh báo" in " ".join(vi["lockout"]["points"])
    assert "bộ phận che chắn" in vi["machine guarding"]["title"]
    assert "Phòng ngã" in vi["fall"]["title"]
    assert "xác nhận nhường đường" in " ".join(vi["forklift"]["points"])
    assert "dưới tải đang nâng" in " ".join(vi["forklift"]["points"])


def test_vi_lead_keeps_counts_as_runtime_placeholders():
    assert LEADS["vi"].count("{{topic_reports}}") == 1
    assert LEADS["vi"].count("{{since}}") == 1
