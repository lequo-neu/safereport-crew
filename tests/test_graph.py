"""The crew end to end on the offline backend: each demo scenario of the proposal."""

from __future__ import annotations

from collections import Counter

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
import pytest

from safereport.backends import OfflineBackend
from safereport.data import CODES_V3_PARQUET, REPORTS_PARQUET
from safereport.ecfr import ECFR_DIR
from safereport.graph import build_graph, load_services, run_config, sqlite_checkpointer
from safereport.retrieval import INDEX_DIR


JAM = "An employee's hand was pulled into the rollers of a laminator machine while clearing a jam, amputating a fingertip."
THREE_TASKS = ("Find caught in machinery injuries in Texas since 2022, check which employers reported more than once, "
               "then plan this week's inspections with {days} inspector days.")  # fmt: skip


def agents(state) -> list[str]:
    return [t["agent"] for t in state["trace"]]


# ---- On the small file: these run in CI with no data download ----


def test_a_pasted_narrative_becomes_a_brief(small_services):
    graph = build_graph(small_services, InMemorySaver())
    out = graph.invoke({"request": JAM}, run_config())
    assert "1910.147" in out["answer"] and "Was the machine shut down and locked out" in out["answer"]
    assert {"Planner", "Intake", "Standards", "Analyst", "Writer", "Decision critic"} <= set(agents(out))


def test_missing_state_interrupts_and_the_answer_resumes(small_services):
    graph = build_graph(small_services, InMemorySaver())
    config = run_config()
    out = graph.invoke(
        {"request": "Check which employers reported more than once, then plan this week's inspections."},
        config,
    )
    assert out["__interrupt__"][0].value["missing"] == ["state"]
    out = graph.invoke(Command(resume={"state": "texas"}), config)
    rows = out["__interrupt__"][0].value["rows"]
    assert {r["report_id"] for r in rows} == {"1", "2", "3", "4", "5"}
    assert (
        Counter(a for a in agents(graph.get_state(config).values))["Planner"] == 2
    )  # planned once, then the answer


def test_approval_with_changes_resumes_at_the_optimizer_and_is_logged(small_services, tmp_path):
    graph = build_graph(small_services, sqlite_checkpointer(str(tmp_path / "runs.sqlite")))
    config = run_config()
    out = graph.invoke({"request": "Plan this week's inspections in Texas."}, config)
    rows = out["__interrupt__"][0].value["rows"]
    letter = next(r["report_id"] for r in rows if r["decision"] == "rri_letter")
    intakes_before = agents(graph.get_state(config).values).count("Intake")
    out = graph.invoke(
        Command(resume={"action": "changes", "force_inspection": [letter], "by": "A. Director"}), config
    )
    changed = {r["report_id"]: r for r in out["__interrupt__"][0].value["rows"]}
    assert changed[letter]["decision"] == "inspection" and "Area Director" in changed[letter]["reason"]
    assert (
        agents(graph.get_state(config).values).count("Intake") == intakes_before
    )  # nothing before the Optimizer reran
    out = graph.invoke(Command(resume={"action": "approve", "by": "A. Director"}), config)
    assert [e["action"] for e in out["decision_log"]] == ["asked for changes", "approved"]
    assert out["decision_log"][1]["by"] == "A. Director" and letter in out["decision_log"][1]["decisions"]


def test_too_few_days_says_how_many_more_are_needed(small_services):
    small_services.capacity = 0.5
    graph = build_graph(small_services, InMemorySaver())
    config = run_config()
    graph.invoke({"request": "Plan this week's inspections in Ohio."}, config)
    out = graph.invoke(Command(resume={"action": "approve"}), config)
    assert "Not enough inspector days" in out["answer"] and "more days" in out["answer"]


def test_seeded_wrong_and_invented_citations_are_caught_and_fixed(small_services):
    graph = build_graph(small_services, InMemorySaver())
    small_services.seeded_pick = {"primary": "1910.212(a)(1)"}
    out = graph.invoke({"request": JAM}, run_config())
    assert "Standard:** 1910.147, secondary 1910.212(a)(1)" in out["answer"]
    assert any("energy" in t["summary"] or "issues back" in t["summary"] for t in out["trace"])
    small_services.seeded_pick = {"primary": "1910.999(z)"}
    out = graph.invoke({"request": JAM}, run_config())
    assert "1910.999" not in out["answer"]


def test_a_hand_written_number_is_retried_then_left_out(small_services):
    handlers = dict(small_services.router.backends["gpt_nano"].handlers)
    write = handlers["writer"]

    def careless(prompt):
        reply = write(prompt)
        return {**reply, "template": reply["template"] + "\n\nAbout 37 similar cases were never reported."}

    for backend in small_services.router.backends.values():
        backend.handlers["writer"] = careless
    graph = build_graph(small_services, InMemorySaver())
    out = graph.invoke({"request": JAM}, run_config())
    assert "37" not in out["answer"] and "could not be traced" in out["answer"]
    writers = [t["model"] for t in out["trace"] if t["agent"] == "Writer"]
    assert writers[0] == "gpt_nano" and writers[-1] == "claude"  # the retry moved up a model


def test_a_talk_in_english_and_vietnamese(small_services):
    out = build_graph(small_services, InMemorySaver()).invoke(
        {"request": "Write a forklift safety talk for the next shift in English and Vietnamese."},
        run_config(),
    )
    assert "Forklifts and people" in out["answer"] and "Xe nâng và con người" in out["answer"]
    assert "Montacargas" not in out["answer"], "one extra language, not two"


def test_spanish_safety_talk(small_services):
    out = build_graph(small_services, InMemorySaver()).invoke(
        {"request": "Write a ten minute safety talk on lockout for my night shift, in English and Spanish."},
        run_config(),
    )
    assert (
        "Lockout before you reach in" in out["answer"] and "Bloquee antes de meter las manos" in out["answer"]
    )


def test_private_mode_and_provider_fallback(small_services):
    small_services.mode = "private"
    out = build_graph(small_services, InMemorySaver()).invoke({"request": JAM}, run_config())
    assert {t["model"] for t in out["trace"] if t["model"]} == {"gemma_local"}

    small_services.mode = "lowest_cost"
    small_services.router.backends["claude"] = OfflineBackend(
        name="claude",
        handlers=small_services.router.backends["gpt_nano"].handlers,
        failures={"planner": ["timeout", "timeout"]},
    )
    out = build_graph(small_services, InMemorySaver()).invoke({"request": JAM}, run_config())
    planner = next(t for t in out["trace"] if t["agent"] == "Planner")
    assert planner["model"] == "gemini_flash" and planner["fallback"] == "claude"


def test_names_are_redacted_before_a_cloud_model_sees_them(small_services):
    seen = []
    intake = small_services.router.backends["gpt_nano"].handlers["intake"]

    def spy(prompt):
        seen.append(prompt)
        return intake(prompt)

    small_services.router.backends["gpt_nano"].handlers["intake"] = spy
    graph = build_graph(small_services, InMemorySaver())
    config = run_config()
    graph.invoke({"request": "Plan this week's inspections in Ohio."}, config)
    assert seen and all("Acme Laminates" not in prompt for prompt in seen)


def test_an_invented_standard_in_the_weekly_list_is_corrected_without_a_crash(small_services, monkeypatch):
    """The critic checks every report of the week, and revise corrects it through the Optimizer."""
    graph = build_graph(small_services, InMemorySaver())
    rows = graph.invoke({"request": "Plan this week's inspections in Texas."}, run_config())["__interrupt__"][
        0
    ].value["rows"]
    cited = next(
        r["standard"] for r in rows if r["decision"] == "rri_letter" and r["standard"].startswith("1910")
    )
    real_exists = small_services.citations.exists
    monkeypatch.setattr(small_services.citations, "exists", lambda c: c.strip() != cited and real_exists(c))

    config = run_config()
    out = graph.invoke({"request": "Plan this week's inspections in Texas."}, config)
    rows = out["__interrupt__"][0].value["rows"]
    assert cited not in {r["standard"] for r in rows}
    state = graph.get_state(config).values
    assert state["pick_overrides"] and cited not in {d["citation"] for d in state["drafts"].values()}
    assert any("issues back" in t["summary"] for t in state["trace"])


def test_a_pasted_name_and_phone_never_reach_the_planner(small_services):
    seen = []
    for backend in small_services.router.backends.values():
        plan = backend.handlers["planner"]
        backend.handlers["planner"] = lambda prompt, plan=plan: seen.append(prompt) or plan(prompt)
    request = f"{JAM} Call Mr. John Smith at 555-201-3344 in Texas."
    out = build_graph(small_services, InMemorySaver()).invoke({"request": request}, run_config())
    assert seen and all("John Smith" not in p and "555-201-3344" not in p for p in seen)
    assert "Texas" in seen[0] and "1910.147" in out["answer"]


def test_the_planner_asks_only_for_what_the_code_can_use(small_services):
    # Gemma 4 E4B in private mode asked for "Date of occurrence" on a pasted narrative.
    def chatty(prompt):
        return {"tasks": [{"id": "report", "kind": "single_report", "needs": ["Date of occurrence"],
                           "depends_on": []}], "params": {}, "missing": ["Date of occurrence"]}  # fmt: skip

    for backend in small_services.router.backends.values():
        backend.handlers["planner"] = chatty
    out = build_graph(small_services, InMemorySaver()).invoke({"request": JAM}, run_config())
    assert "__interrupt__" not in out and "1910.147" in out["answer"]


def test_a_pasted_report_is_dated_to_the_replayed_week(small_services):
    out = build_graph(small_services, InMemorySaver()).invoke({"request": JAM}, run_config())
    finding = next(f for f in out["findings"].values() if f["kind"] == "single_report")
    assert finding["report"]["event_date"] == str(small_services.week[1])


def test_a_one_year_trend_and_an_empty_range_answer_without_a_crash(small_services):
    graph = build_graph(small_services, InMemorySaver())
    out = graph.invoke({"request": "Show the injury trend in Texas since 2025."}, run_config())
    assert "no earlier year to compare" in out["answer"] and "could not be traced" not in out["answer"]
    out = graph.invoke({"request": "Show the injury trend in Texas since 2030."}, run_config())
    assert "no report matches this range" in out["answer"]


def test_finalize_leaves_out_a_line_that_compares_unequal_periods(small_services, monkeypatch):
    from safereport.ledger import FactLedger

    # No fact of the offline crew compares a partial year with a full one, so the ledger is told
    # that this line does; the critic retries twice and the final answer must drop the line.
    monkeypatch.setattr(FactLedger, "unequal_periods",
                        lambda self, text: ["history_same"] if "against last year" in text else [])  # fmt: skip
    write = small_services.router.backends["gpt_nano"].handlers["writer"]

    def unequal(prompt):
        reply = write(prompt)
        return {**reply, "template": reply["template"] + "\n\nThat is {{history_same}} against last year."}

    for backend in small_services.router.backends.values():
        backend.handlers["writer"] = unequal
    out = build_graph(small_services, InMemorySaver()).invoke({"request": JAM}, run_config())
    assert "against last year" not in out["answer"] and "could not be traced" in out["answer"]
    assert "1910.147" in out["answer"], "the rest of the brief is kept"


# ---- On the real data: the demo scenarios as they will be shown ----

needs_data = pytest.mark.skipif(
    not (REPORTS_PARQUET.exists() and CODES_V3_PARQUET.exists() and (INDEX_DIR / "manifest.json").exists()
         and (ECFR_DIR / "title-29-part-1910.xml").exists()),
    reason="build the data, indexes and baseline first (see README)",
)  # fmt: skip


@pytest.fixture(scope="module")
def real():
    return load_services(dense=False)


@needs_data
def test_demo_three_tasks_on_a_real_texas_week(real):
    graph = build_graph(real, InMemorySaver())
    config = run_config()
    out = graph.invoke({"request": THREE_TASKS.format(days=40)}, config)
    rows = out["__interrupt__"][0].value["rows"]
    state = graph.get_state(config).values
    assert len(rows) == 31
    stage2 = sum(r["stage"] == 2 for r in rows)
    assert 0 < stage2 < len(rows), "only the unclear, severe or borderline reports get model branches"
    assert all(r["decision"] == "inspection" for r in rows if r["category_one"])
    critic = [t["summary"] for t in state["trace"] if t["agent"] == "Decision critic"]
    assert critic[-1].startswith("every citation, number and rule checks out"), critic
    # A fall standard for an injury that was not a fall is left for a person, and the list keeps it.
    checks = [i for i in state["issues"] if i["rule"] == "fall_only"]
    assert checks and all(i["route"] == "person" for i in checks)
    scale = next(r for r in rows if r["report_id"] == "20251111443")  # metal scale fell off a crane load
    assert scale["standard"] == "1910.28"
    valet = next(r for r in rows if r["report_id"] == "20251111613")  # a road vehicle: no Part 1910 standard
    assert valet["standard"] == "OSH Act 5(a)(1)"
    assert state["findings"]["triage"]["sensitivity"] and state["findings"]["triage"]["csv"].startswith(
        "report_id"
    )
    letters = [k for k in state["drafts"] if ":letter_" in k]
    assert len(letters) == sum(r["decision"] == "rri_letter" for r in rows)
    out = graph.invoke(Command(resume={"action": "approve"}), config)
    assert "January to November only" in out["answer"] and "estimated" in out["answer"]
    assert "could not be traced" not in out["answer"]


@needs_data
def test_demo_too_few_days_on_the_real_week(real):
    graph = build_graph(real, InMemorySaver())
    config = run_config()
    graph.invoke({"request": "Plan this week's inspections in Texas with 10 inspector days."}, config)
    out = graph.invoke(Command(resume={"action": "approve"}), config)
    assert "Not enough inspector days" in out["answer"]


@needs_data
def test_demo_pasted_narrative_on_real_indexes(real):
    out = build_graph(real, InMemorySaver()).invoke({"request": JAM}, run_config())
    assert "Standard:** 1910.147" in out["answer"]
    finding = next(f for f in out["findings"].values() if f["kind"] == "single_report")
    assert finding["industry_share"] > 0, "the share uses the code the Intake agent read"


@pytest.mark.parametrize(
    ("typed", "why"), [("-5", "cannot be planned"), ("1,200", "more than an office has")]
)
def test_typed_inspector_days_a_person_could_not_mean_are_refused(small_services, typed, why):
    graph = build_graph(small_services, InMemorySaver())
    config = run_config()
    graph.invoke({"request": f"Plan this week's inspections in Texas with {typed} inspector days."}, config)
    out = graph.invoke(Command(resume={"action": "approve"}), config)
    assert why in out["answer"] and f"{small_services.capacity:g}" in out["answer"]
