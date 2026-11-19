"""The app on the small file: every page's handlers, each role's view, approval and exports."""

from __future__ import annotations

from pathlib import Path

import gradio as gr
from langgraph.checkpoint.memory import InMemorySaver
import pytest

from safereport import views
from safereport.app import build_app, role_view
from safereport.employers import DecisionStore
from safereport.views import Crew, Session


JAM = "An employee's hand was pulled into the rollers of a laminator machine while clearing a jam, amputating a fingertip."


@pytest.fixture
def crew(small_services, tmp_path: Path) -> Crew:
    small_services.router.sleep = lambda _: None
    return Crew.start(small_services, InMemorySaver(), folder=tmp_path)


def test_the_app_builds_and_each_role_opens_on_its_page(crew):
    assert isinstance(build_app(crew), gr.Blocks)
    for role, home in views.HOME.items():
        tabs, week_tab, approve, controls, save_matches = role_view(role)
        assert tabs.selected == home
        assert week_tab.visible == (role != "Plant safety manager")
        assert approve.visible == (role == "Area Director")
        assert controls.visible == (role == "Admin")
        assert save_matches.visible == (role in ("Triage officer", "Area Director"))


def test_a_pasted_narrative_answers_with_a_trace_evidence_and_a_brief(crew):
    session = Session()
    history, box, trace, _, brief, session = views.ask(crew, JAM, [], session)
    assert box == "" and "1910.147" in history[-1]["content"] and brief.endswith("inspection_brief.docx")
    assert "Planner" in trace and "Decision critic" in trace and "sr-step" in trace
    assert any(path.endswith("inspection_brief.docx") for path in views.files(crew, session))

    assert views.evidence_choices(crew, session)[0] == "Pasted narrative"
    pieces, rule, checks, questions, _ = views.evidence(crew, session, "Pasted narrative")
    assert "".join(text for text, _ in pieces) == JAM, "the highlights cover the narrative exactly"
    assert any(label for _, label in pieces)
    assert rule.startswith("### 1910.147") and "in eCFR" in checks and "domain checks pass" in checks
    assert "locked out" in questions


def test_a_missing_state_is_asked_for_and_the_week_opens_for_approval(crew):
    session = Session()
    request = "Check which employers reported more than once, then plan this week's inspections."
    history, *_ = views.ask(crew, request, [], session)
    assert "Which state" in history[-1]["content"] and session.question
    history, *_ = views.ask(crew, "somewhere warm", history, session)
    assert history[-1]["content"].startswith("I still need this"), "an answer without a state is asked again"
    history, *_ = views.ask(crew, "Texas, please", history, session)
    assert "week's list is ready" in history[-1]["content"] and session.week_state == "TEXAS"
    tiles, table, *_ = views.week_view(crew, session)
    assert "sr-tile" in tiles and set(table["Report"]) == {"1", "2", "3", "4", "5"}


def test_the_director_edits_rows_resumes_and_approves(crew):
    session = Session()
    _, table, _, _, chart, status = views.load_week(crew, session, "Texas", 5)
    assert chart is not None and "Waiting for the Area Director" in status

    bad = table.copy()
    bad.loc[0, "Decision"] = "maybe"
    assert (
        "write Inspection or RRI letter"
        in views.ask_for_changes(crew, session, bad, 5, "", "Area Director")[5]
    )

    letter = table.index[
        (table["Decision"] == "RRI letter") & (table["Establishment Name"] != "Walmart, Inc.")
    ][0]
    report = table.loc[letter, "Report"]
    edited = table.copy()
    edited.loc[letter, ["Decision", "Note"]] = ["Inspection", "prior complaint on file"]
    _, after, *_, status = views.ask_for_changes(crew, session, edited, 6, "WALMART INC", "Area Director")
    row = after[after["Report"] == report].iloc[0]
    assert row["Decision"] == "Inspection" and "prior complaint on file" in row["Reason"]
    assert "Plan updated with 1 changed rows and a rule for WALMART INC" in status
    walmart = after[after["Establishment Name"] == "Walmart, Inc."].iloc[0]
    assert walmart["Decision"] == "Inspection" and "rule" in walmart["Reason"], (
        "case, commas and Inc are ignored"
    )

    refused = views.approve(crew, session, "Triage officer")
    assert "Only the Area Director approves" in refused[5]
    *_, status, answer = views.approve(crew, session, "Area Director")
    assert "Approved" in status and "asked for changes" in status and answer
    names = {Path(p).name for p in views.files(crew, session)}
    assert {"inspection_list.csv", "week_summary.docx"} <= names
    assert "no list waiting" in views.approve(crew, session, "Area Director")[5]


def test_a_category_one_row_cannot_be_sent_a_letter(crew):
    session = Session()
    crew.services.capacity = 50
    _, table, *_ = views.load_week(crew, session, "Ohio", 50)
    finding = views._triage(crew, session)
    must = [r["report_id"] for r in finding["rows"] if r["category_one"]]
    assert must, "the amputation report in Ohio meets Category 1"
    edited = table.copy()
    edited.loc[edited["Report"] == must[0], "Decision"] = "RRI letter"
    assert "must be inspected" in views.ask_for_changes(crew, session, edited, 50, "", "Area Director")[5]


def test_a_match_decision_is_saved_once_for_the_pair(crew, tmp_path):
    session = Session()
    *_, matches, _, _ = views.load_week(crew, session, "Texas", 5)
    assert len(matches), "Walmart and the Postal Service spellings are possible matches"
    first = matches.iloc[0]
    answered = matches.copy()
    answered.loc[answered.index[0], "Same employer?"] = "yes"
    after, note = views.save_matches(crew, session, answered, "Triage officer")
    assert note.startswith("Saved 1 decisions")
    assert not (
        (after["This week"] == first["This week"]) & (after["Earlier spelling"] == first["Earlier spelling"])
    ).any()
    stored = DecisionStore(tmp_path / "employer_decisions.sqlite").load()
    assert len(stored) == 1 and all(stored.values())


def test_trends_mark_the_partial_year_and_talks_export_to_word(crew):
    image, table, note = views.trend_view(crew, "Texas", "All industries", "All events", 2024)
    assert image is not None and table["Year"].iloc[-1] == "2025 (Jan to Jun)" and "January to June" in note
    _, _, empty = views.trend_view(crew, "Alaska", "All industries", "All events", 2024)
    assert "No report matches" in empty

    session = Session()
    talk, names = views.safety_talk(crew, session, "lockout", True)
    assert talk and sorted(Path(n).name for n in names) == [
        "safety_talk_lockout_en.docx",
        "safety_talk_lockout_es.docx",
    ]


def test_an_outage_falls_back_and_private_mode_stays_local(crew):
    labels = [s.label for s in crew.services.settings.models]
    message, models = views.apply_controls(crew, "Lowest cost", True, labels)
    assert message == "At least one model must stay up."
    cloud = [s.label for s in crew.services.settings.models if not s.is_local]
    message, models = views.apply_controls(crew, "Lowest cost", True, cloud)
    assert "fall back" in message and (models["Status"] == "outage (simulated)").sum() == len(cloud)
    session = Session()
    history, _, trace, *_ = views.ask(crew, JAM, [], session)
    assert "1910.147" in history[-1]["content"] and "fell back from" in trace
    usage = views.usage_table(crew)
    assert {"Why this model", "Fell back from", "Error"} <= set(usage.columns) and (
        usage["Error"] == "server_error"
    ).any()

    views.apply_controls(crew, "Private (local model only)", True, [])
    before = len(crew.services.router.log.rows())
    views.ask(crew, JAM, [], Session())
    assert {r["model"] for r in crew.services.router.log.rows()[before:]} == {"gemma_local"}
    assert "Private mode needs the local model" in views.apply_controls(crew, "Private (local model only)", True,
                                                                        ["Gemma 4 E4B (local)"])[0]  # fmt: skip


def test_the_evaluation_page_reads_the_results(crew):
    image, coding, retrieval, note = views.evaluation(crew)
    if (views.RESULTS_DIR / "phase1_baselines.json").exists():
        assert image is not None and len(coding) == 3 and retrieval.iloc[0, 0].startswith("No model")
        assert "final test set" in note
    else:
        assert image is None and "eval-baselines" in note


def test_rows_move_by_picking_them_from_a_list(crew):
    session = Session()
    _, table, *_ = views.load_week(crew, session, "Texas", 5)
    letters, inspections = views.move_choices(crew, session)
    assert letters and inspections and all(label.split()[0] in set(table["Report"]) for label in letters)
    _, after, *_, status = views.ask_for_changes(crew, session, table, 5, "", "Area Director",
                                                 to_inspect=[letters[0]], to_letter=[inspections[0]])  # fmt: skip
    decisions = dict(zip(after["Report"], after["Decision"], strict=True))
    assert (
        decisions[letters[0].split()[0]] == "Inspection"
        and decisions[inspections[0].split()[0]] == "RRI letter"
    )
    assert "with 2 changed rows" in status


def test_the_week_filters_to_one_part_of_the_work(crew):
    session = Session()
    _, table, *_ = views.load_week(crew, session, "Ohio", 50)
    for show in views.FILTERS:
        part = views.week_rows(crew, session, show)
        assert set(part["Report"]) <= set(table["Report"])
    assert (views.week_rows(crew, session, "Category 1")["Category 1"] != "").all()
    letters = views.week_rows(crew, session, "RRI letter")
    assert (letters["Decision"] == "RRI letter").all() and (letters["Reply due"] != "").all()
    assert len(views.week_rows(crew, session, "Inspection")) + len(letters) == len(table)


def test_a_reply_is_due_five_working_days_later_without_holidays():
    from datetime import date

    assert views.reply_due(date(2025, 11, 23)) == date(2025, 12, 1)  # Sunday; Thanksgiving falls on the 27th
    assert views.reply_due(date(2025, 11, 17)) == date(2025, 11, 24)


def test_a_picked_row_shows_its_evidence_context_and_letter(crew):
    session = Session()
    _, table, *_ = views.load_week(crew, session, "Texas", 5)
    letter_row = table[table["Decision"] == "RRI letter"].iloc[0]
    pieces, rule, checks, context, letter = views.quick_view(crew, session, letter_row["Report"])
    assert pieces and rule.startswith("### ") and "sr-badge" in checks
    assert (
        letter.startswith("**The RRI letter as it will be sent**")
        and letter_row["Establishment Name"] in letter
    )
    assert "earlier reports under the same name" in context
    inspected = table[table["Decision"] == "Inspection"].iloc[0]
    assert views.quick_view(crew, session, inspected["Report"])[4].startswith("**Goes to an inspection.**")
    assert views.quick_view(crew, session, "nope")[4] == "Pick a row in the list to read it here."


def test_asking_for_changes_lists_what_moved(crew):
    session = Session()
    views.load_week(crew, session, "Texas", 5)
    letters, _ = views.move_choices(crew, session)
    table = views.week_rows(crew, session)
    *_, status = views.ask_for_changes(crew, session, table, 5, "", "Area Director", to_inspect=[letters[0]])
    assert "**What changed**" in status and letters[0].split()[0] in status and "now inspection" in status


def test_matches_carry_what_tells_two_spellings_apart(crew):
    session = Session()
    *_, matches, _, _ = views.load_week(crew, session, "Texas", 5)
    assert list(matches.columns) == views.MATCH_COLUMNS
    row = matches.iloc[0]
    assert row["City"] and row["Earlier city"] and row["Last earlier report"] and row["Same industry"]


def test_the_week_map_and_the_marked_chart(crew, monkeypatch):
    session = Session()
    views.load_week(crew, session, "Texas", 5)
    assert views.week_map(crew, session) is None, "the small file has no coordinates"
    places = crew.services.store.frame("SELECT id FROM reports WHERE state = 'TEXAS'")
    import pandas as pd

    fake = pd.DataFrame({"id": places["id"], "latitude": 30.0 + places.index * 0.1,
                         "longitude": -97.0 - places.index * 0.1, "city": "Austin"})  # fmt: skip
    real_frame = crew.services.store.frame
    monkeypatch.setattr(crew.services.store, "frame",
                        lambda sql, params=None: fake if "latitude" in sql else real_frame(sql, params))  # fmt: skip
    figure = views.week_map(crew, session)
    names = {trace.name for trace in figure.data}
    assert names <= {"Category 1", "Inspection", "RRI letter"} and sum(
        len(t.lat) for t in figure.data
    ) == len(fake)
    chart = views.week_view(crew, session)[4]
    assert chart is not None


@pytest.mark.parametrize(("days", "message"), [(-5, "cannot be negative"), ("", "Enter the inspector days"),
                                               ("many", "must be a number"), (9999, "check the number")])  # fmt: skip
def test_bad_inspector_days_are_refused_before_any_planning(crew, days, message):
    session = Session()
    *_, status = views.load_week(crew, session, "Texas", days)
    assert message in status and not session.week_thread, "nothing was planned"


def test_zero_inspector_days_is_a_real_week(crew):
    session = Session()
    *_, status = views.load_week(crew, session, "Ohio", 0)
    assert "Waiting for the Area Director" in status and session.week_thread


def test_an_empty_week_cannot_be_approved(crew):
    session = Session()
    _, table, *_, status = views.load_week(crew, session, "Wyoming", 7)
    assert table.empty and "No severe injury reports came from Wyoming" in status
    assert "nothing to approve" in views.approve(crew, session, "Area Director")[5]
    assert views.files(crew, session) == [], "no empty files were written"


def test_a_talk_needs_a_topic(crew):
    session = Session()
    for topic in (" ", "", None, "cooking"):
        talk, names = views.safety_talk(crew, session, topic, True)
        assert talk.startswith("Choose a topic") and names == []
    assert views.files(crew, session) == []


def test_the_list_draws_decisions_as_labels_and_reads_them_back(crew):
    from safereport.app import chips

    session = Session()
    _, table, *_ = views.load_week(crew, session, "Texas", 5)
    drawn = chips(table)
    assert drawn["Decision"].str.startswith('<span class="sr-chip').all()
    assert {views._decision(label) for label in drawn["Decision"]} <= {"inspection", "rri_letter"}
    *_, status = views.ask_for_changes(crew, session, drawn, 5, "", "Area Director")
    assert "Plan updated with 0 changed rows" in status, "labels read back as the same decisions"


def test_the_admin_sees_the_data_behind_the_crew(crew):
    data = views.data_table(crew)
    assert data.iloc[0]["What"] == "Severe injury reports" and data.iloc[0]["Size"] == "9"
    assert any(data["What"].str.startswith("Index: 1910"))


def test_trends_answer_how_people_get_hurt_in_an_industry(crew):
    figure, numbers, _ = views.trend_view(crew, "Texas", "All industries", "All events", 2024)
    assert len(figure.data[0].x) == len(numbers)
    events, caption = views.top_events(crew, "Texas", "All industries")
    assert events is not None and "since OSHA moved to OIICS 3" in caption
    assert views.top_events(crew, "Alaska", "Plastics")[0] is None


@pytest.mark.parametrize(
    "choice", ["Spanish (es)", "Chinese (zh)", "Tagalog (tl)", "Vietnamese (vi)", "Arabic (ar)"]
)
def test_a_talk_comes_in_english_and_one_more_language(crew, choice):
    code = choice[-3:-1]
    talk, names = views.safety_talk(crew, Session(), "forklift", choice)
    assert sorted(Path(n).name for n in names) == sorted(
        ["safety_talk_forklift_en.docx", f"safety_talk_forklift_{code}.docx"]
    )
    assert "Forklifts and people" in talk and "could not be traced" not in talk


def test_english_only_and_bad_language_choices(crew):
    talk, names = views.safety_talk(crew, Session(), "lockout", "None (English only)")
    assert [Path(n).name for n in names] == ["safety_talk_lockout_en.docx"]
    for bad, message in [
        ("Klingon (tlh)", "is not offered"),
        (["es", "vi"], "at most one language"),
        ("fr", "is not offered"),
    ]:
        talk, names = views.safety_talk(crew, Session(), "lockout", bad)
        assert message in talk and names == []


def test_the_week_states_its_active_filters_and_downloads_what_it_shows(crew):
    session = Session()
    assert "No week loaded" in views.filters_line(crew, session)
    tiles, *_ = views.load_week(crew, session, "Texas", 5)
    assert "Total Severe Injury Reports" in tiles and "Category 1 (mandatory inspection)" in tiles
    assert "model branches" not in tiles and "Decision critic" not in tiles, (
        "no agent words on the front line"
    )
    line = views.filters_line(crew, session, "RRI letter")
    letters = views.week_rows(crew, session, "RRI letter")
    assert "Active filters:" in line and "Texas" in line and f"Showing {len(letters)} of 5 reports" in line
    path = views.download_week(crew, session, "RRI letter")
    assert Path(path).read_text().count("\n") == len(letters) + 1, "a header and one line per shown row"
    assert set(views.week_rows(crew, session)["Review tier"]) <= {"Auto-coded", "Human check"}


def test_unresolved_matches_are_counted_and_recalled_at_approval(crew):
    session = Session()
    views.load_week(crew, session, "Texas", 5)
    open_matches = views.unresolved_matches(crew, session)
    assert open_matches > 0
    *_, status, _ = views.approve(crew, session, "Area Director")
    assert f"{open_matches} possible employer matches are still unresolved" in status and "Approved" in status


def test_empty_tables_say_why_they_are_empty(crew):
    session = Session()
    _, _, triggers, matches, _, _ = views.week_view(crew, session)
    assert triggers.iloc[0, 0].startswith("Load a week")
    views.load_week(crew, session, "Wyoming", 5)
    _, _, triggers, matches, _, _ = views.week_view(crew, session)
    assert triggers.iloc[0, 0].startswith("No report meets") and matches.iloc[0, 0].startswith("No possible")
    assert views.unresolved_matches(crew, session) == 0
    assert views.placeholder_figure("nothing here").layout.annotations[0].text == "nothing here"


def test_trends_show_the_dashboard_figures_and_export_the_selection(crew):
    tiles = views.trend_tiles(crew, "Texas", "All industries", "All events", 2024)
    assert "Total Severe Injury Reports" in tiles and "Total Workers with Amputations" in tiles
    assert "Total Workers with Loss of an Eye" in tiles and "Total Workers Hospitalized" in tiles
    assert "Active filters:" in views.trend_filters_line(crew, "Texas", "All industries", "All events", 2024)
    path = views.download_trend(crew, Session(), "Texas", "All industries", "All events", 2024)
    lines = Path(path).read_text().splitlines()
    assert lines[0].startswith("id,event_date,establishment_name") and len(lines) == 1 + 5


def test_trends_draw_four_outcomes_and_mark_state_plan_states(crew):
    figure, *_ = views.trend_view(crew, "Texas", "All industries", "All events", 2024)
    assert [t.name for t in figure.data] == ["Total reports", "Total hospitalized", "Total amputations",
                                             "Total loss of eye(s)"]  # fmt: skip
    assert list(figure.data[0].x)[-1] == "2025*", "the partial year is starred, as on the dashboard"
    geo = views.state_map(crew, "All industries", "All events", 2024, "Texas")
    federal, plan, outlined = geo.data
    assert "CA" in plan.locations and "CA" not in federal.locations and "TX" in federal.locations
    assert dict(zip(federal.locations, federal.z, strict=True))["TX"] == 5 and list(outlined.locations) == [
        "TX"
    ]


def test_the_routing_page_opens_on_the_starting_mode():
    assert {views.mode_label(mode) for mode in views.MODES.values()} == set(views.MODES)
    assert views.mode_label("private") == "Private (local model only)"
