"""What each page of the app shows.

The layout in `app.py` only wires these functions to Gradio components. Every handler takes the
`Crew` (built once per server) and a `Session` (one per browser tab) and returns plain values:
chat messages, HTML, DataFrames, images and file paths. The tests call them directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import html
import io
import json
import math
from pathlib import Path
import re
import textwrap
import time
from typing import Any
import uuid

from langgraph.types import Command
import numpy as np
import pandas as pd
from PIL import Image

from safereport import offline
from safereport.backends import ModelError
from safereport.config import PROJECT_ROOT
from safereport.data import Filters
from safereport.domain import check_citation
from safereport.employers import DecisionStore, normalize_name
from safereport.evaluation import RESULTS_DIR
from safereport.graph import (
    TALK_MIN_REPORTS,
    Services,
    build_graph,
    load_services,
    run_config,
    sqlite_checkpointer,
)
from safereport.icons import svg
from safereport.ledger import FactLedger
from safereport.outputs import pareto_chart, sensitivity_chart, word_document
from safereport.schemas import CITATION, DIRECTIVE, GENERAL_DUTY, IntakeResult, clip
from safereport.talk_languages import LANGUAGES, extra_language
from safereport.triage import MAX_DAYS


OUTPUTS = PROJECT_ROOT / "outputs"
ROLES = ("Triage officer", "Area Director", "Plant safety manager", "Admin")
APPROVER = "Area Director"
# The page each role opens on (see the Interface section of docs/PROPOSAL.md).
HOME = {
    "Triage officer": "week",
    "Area Director": "week",
    "Plant safety manager": "trends",
    "Admin": "controls",
}
DECISION_LABELS = {"inspection": "Inspection", "rri_letter": "RRI letter"}
WEEK_COLUMNS = ["Report", "Establishment Name", "Decision", "Category 1", "Standard", "Days", "Reply due", "Note",
                "Priority", "Review tier", "Reason"]  # fmt: skip
EDITABLE = ("Note",)
MATCH_COLUMNS = ["This week", "City", "Earlier spelling", "Earlier city", "Last earlier report",
                 "Same industry", "Earlier reports", "Similarity", "Same employer?"]  # fmt: skip
# The order a triage officer works the week in: the musts, the model reviewed, the unclear codes.
FILTERS = ("All", "Category 1", "Needs review", "Inspection", "RRI letter")
TRIGGER_COLUMNS = ["Report", "Establishment Name", "Criterion", "Evidence"]
RRI_REPLY_DAYS = 5  # working days the employer has to answer the letter
INDUSTRY_CHOICES = {"All industries": "", "Manufacturing": "3", "Food manufacturing": "311",
                    "Plastics": "326", "Primary metal": "331", "Fabricated metal": "332",
                    "Warehousing": "493", "Construction": "23"}  # fmt: skip
HAZARD_CHOICES = {"All events": "", "Caught in machinery": "653", "Struck by an object": "64",
                  "Falls to a lower level": "41", "Slips and trips": "43"}  # fmt: skip
TALK_TOPICS = ("lockout", "machine guarding", "fall", "forklift")
TALK_LANGUAGE_CHOICES = ["None (English only)", *(f"{name} ({code})" for code, name in LANGUAGES.items())]
MODES = {
    "Lowest cost": "lowest_cost",
    "Best quality": "best_quality",
    "Private (local model only)": "private",
}


@dataclass
class Crew:
    """The services and the compiled graph, shared by every browser tab."""

    services: Services
    graph: Any
    # Every backend the router started with, so a simulated outage can be lifted.
    backends: dict[str, Any]
    folder: Path

    @classmethod
    def start(cls, services: Services | None = None, checkpointer=None, folder: Path = OUTPUTS) -> Crew:
        services = services or load_services()
        folder.mkdir(parents=True, exist_ok=True)
        if services.decisions is None:
            services.decisions = DecisionStore(folder / "employer_decisions.sqlite")
        graph = build_graph(services, checkpointer or sqlite_checkpointer(str(folder / "runs.sqlite")))
        return cls(services, graph, dict(services.router.backends), folder)

    def run(self, thread: str, payload: Any) -> dict[str, Any]:
        return self.graph.invoke(payload, run_config(thread))

    def values(self, thread: str) -> dict[str, Any]:
        return self.graph.get_state(run_config(thread)).values if thread else {}

    def waiting_for(self, thread: str) -> tuple[str, ...]:
        return tuple(self.graph.get_state(run_config(thread)).next) if thread else ()


@dataclass
class Session:
    """One browser tab: its conversation, its week and its files."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    ask_thread: str = ""
    question: dict[str, Any] | None = None  # a question the Planner is waiting on
    week_thread: str = ""
    week_state: str = ""
    week_seconds: float = 0.0
    # The week list whose Approve was pressed once with employer matches open; a second press on
    # that same list approves anyway. A new list, from Load week or from Ask, is warned again.
    approve_warned: str = ""


# ---- Small helpers ----


def picture(png: bytes | None) -> Image.Image | None:
    return Image.open(io.BytesIO(png)) if png else None


def rendered(draft: dict[str, Any]) -> str:
    """A Writer draft with its facts filled in."""
    ledger = FactLedger()
    for key, (value, source, same_months) in draft["facts"].items():
        ledger.add(key, value, source, same_months=same_months)
    return ledger.render(draft["template"])


def save(crew: Crew, session: Session, name: str, content: bytes | str) -> str:
    folder = crew.folder / "downloads" / session.id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_bytes(content)
    return str(path)


def files(crew: Crew, session: Session) -> list[str]:
    folder = crew.folder / "downloads" / session.id
    return sorted(str(p) for p in folder.iterdir()) if folder.exists() else []


def badge(text: str, kind: str = "info") -> str:
    return f'<span class="sr-badge sr-{kind}">{html.escape(text)}</span>'


def citation_known(crew: Crew, citation: str) -> bool:
    return (
        citation == GENERAL_DUTY
        or bool(DIRECTIVE.match(citation))
        or (bool(CITATION.match(citation)) and crew.services.citations.exists(citation))
    )


# ---- Ask ----


def trace_html(trace: list[dict[str, Any]], offline_rules: bool = False) -> str:
    """The run as a routing slip: one line per agent step, with the model and why it was chosen.

    With the offline rules answering, costs are what the chosen model would have charged.
    """
    if not trace:
        return '<div class="sr-empty">Each step of the crew appears here as it runs.</div>'
    items = []
    for step in trace:
        agent = step["agent"]
        meta = []
        if step.get("model"):
            meta.append(badge(step["model"], "model"))
        if step.get("fallback"):
            meta.append(badge(f"fell back from {step['fallback']}", "warn"))
        if step.get("tool"):
            meta.append(badge(step["tool"], "tool"))
        if step.get("cost"):
            meta.append(f'<span class="sr-num">{"est. " if offline_rules else ""}${step["cost"]:.4f}</span>')
        if (step.get("seconds") or 0) >= 0.01:
            meta.append(f'<span class="sr-num">{step["seconds"]:.2f} s</span>')
        reason = f'<div class="sr-reason">{html.escape(step["reason"])}</div>' if step.get("reason") else ""
        slug = re.sub(r"[^a-z]+", "-", agent.lower()).strip("-")
        items.append(
            f'<li class="sr-step sr-agent-{slug}"><div class="sr-step-head"><strong>{html.escape(agent)}</strong>'
            f' {html.escape(step["summary"])}</div><div class="sr-meta">{"".join(meta)}</div>{reason}</li>'
        )
    note = (
        '<div class="sr-offline-note">Offline rules answered every step, so nothing was paid. Each step names '
        "the model the router would call, and est. is what that call would cost.</div>"
        if offline_rules
        else ""
    )
    return f'{note}<ol class="sr-trace">{"".join(items)}</ol>'


def offline_rules(crew: Crew) -> bool:
    """True when no model answers for real (the offline rules, or every live model in an outage)."""
    return all(
        type(b).__name__ in ("OfflineBackend", "Outage") for b in crew.services.router.backends.values()
    )


def answers_for(question: dict[str, Any], text: str) -> dict[str, str] | None:
    """Read the user's reply to the Planner's question; None when it does not answer it."""
    found = {}
    for name in question["missing"]:
        if name == "state":
            state = next((s for s in offline.STATES if re.search(rf"\b{s}\b", text, re.IGNORECASE)), "")
            if state:
                found[name] = state
        elif name == "start":
            year = re.search(r"\b(20\d{2})\b", text)
            if year:
                found[name] = f"{year.group(1)}-01-01"
        elif text.strip():
            found[name] = text.strip()
    return found if len(found) == len(question["missing"]) else None


def ask(crew: Crew, message: str, history: list | None, session: Session):
    """One chat turn: the chat, the cleared box, the trace, a chart, the brief file and the session."""
    history = list(history or [])
    message = (message or "").strip()
    if not message:
        return (
            history,
            "",
            trace_html(crew.values(session.ask_thread).get("trace", []), offline_rules(crew)),
            None,
            None,
            session,
        )
    history.append({"role": "user", "content": message})
    answers = answers_for(session.question, message) if session.question else None
    if session.question and answers is None and len(message.split()) > 6:
        # A full sentence that does not answer the open question is a new request: drop the question
        # instead of asking it again forever.
        session.question = None
    if session.question:
        if answers is None:
            history.append(
                {
                    "role": "assistant",
                    "content": "I still need this: " + " ".join(session.question["questions"]),
                }
            )
            return (
                history,
                "",
                trace_html(crew.values(session.ask_thread).get("trace", []), offline_rules(crew)),
                None,
                None,
                session,
            )
        out = crew.run(session.ask_thread, Command(resume=answers))
    else:
        session.ask_thread = uuid.uuid4().hex
        out = crew.run(session.ask_thread, {"request": message})
    session.question = None
    brief_file = None
    values = crew.values(session.ask_thread)
    if "__interrupt__" in out:
        waiting = out["__interrupt__"][0].value
        if "missing" in waiting:
            session.question = waiting
            reply = " ".join(waiting["questions"])
        else:
            session.week_thread, session.week_state = session.ask_thread, values["params"].get("state", "")
            rows = waiting["rows"]
            inspections = sum(r["decision"] == "inspection" for r in rows)
            note = next(
                (f.get("capacity_note") for f in values["findings"].values() if f["kind"] == "triage"), ""
            )
            reply = (f"The week's list is ready: {len(rows)} reports, {inspections} proposed for inspection. "
                     "Open **This week's reports** to change rows and approve it."
                     + (f" Inspector days: {note}" if note else ""))  # fmt: skip
    else:
        reply = out["answer"]
        brief = next((d for k, d in values.get("drafts", {}).items() if k.endswith(":brief")), None)
        if brief:
            brief_file = save(crew, session, "inspection_brief.docx", word_document(rendered(brief)))
    history.append({"role": "assistant", "content": reply})
    trace = trace_html(values.get("trace", []), offline_rules(crew))
    return history, "", trace, picture(chart_of(values)), brief_file, session


def chart_of(values: dict[str, Any]) -> bytes | None:
    for finding in values.get("findings", {}).values():
        if finding.get("chart"):
            return finding["chart"]
    return None


# ---- Evidence view ----


def evidence_choices(crew: Crew, session: Session) -> list[str]:
    choices = []
    if _pasted(crew, session):
        choices.append("Pasted narrative")
    week = _triage(crew, session)
    if week:
        choices += [f"{r['report_id']}  {r['employer']}" for r in week["rows"]]
    return choices


def evidence(crew: Crew, session: Session, choice: str | None):
    """Highlighted narrative, the rule and its check badges, open questions, and the employer context."""
    item = _pasted(crew, session) if choice == "Pasted narrative" else None
    if choice and item is None:
        week = _triage(crew, session)
        item = week["stage1"].get(choice.split()[0]) if week else None
    if item is None:
        return [], "Paste a narrative in **Ask** or load a week to see its evidence.", "", "", ""
    return (*report_parts(crew, item), context(crew, item))


def quick_view(crew: Crew, session: Session, report_id: str):
    """One row of the week, read before signing: the evidence, the context and its letter."""
    week = _triage(crew, session)
    item = week["stage1"].get(str(report_id)) if week else None
    if item is None:
        return [], "", "", "", "Pick a row in the list to read it here."
    pieces, rule, checks, questions = report_parts(crew, item)
    decision = week["plan"]["decisions"].get(item["report"]["id"])
    drafts = crew.values(session.week_thread).get("drafts", {})
    draft = next((d for k, d in drafts.items() if k.endswith(f":letter_{item['report']['id']}")), None)
    if decision == "rri_letter" and draft:
        letter = "**The RRI letter as it will be sent**\n\n" + rendered(draft)
    elif decision == "rri_letter":
        letter = "The letter is drafted when the list is planned again."
    else:
        letter = ("**Goes to an inspection.** No letter; the inspector takes the open questions to the site."
                  + (f"\n\n{questions}" if questions else ""))  # fmt: skip
    # The open questions are in the letter, or in the note for the inspector.
    return pieces, rule, checks, context(crew, item), letter


def report_parts(crew: Crew, item: dict[str, Any]):
    narrative, intake, pick = item["report"]["narrative"], item["intake"], item["pick"]
    pieces, cursor = [], 0
    for span in sorted(intake.get("spans", []), key=lambda s: s["start"]):
        if span["start"] < cursor:
            continue
        # A match can stop inside a word ("roller" in "rollers"); the highlight runs to its end.
        end = span["end"] + len(re.match(r"\w*", narrative[span["end"] :]).group(0))
        pieces += [(narrative[cursor : span["start"]], None), (narrative[span["start"] : end], span["label"])]
        cursor = end
    pieces.append((narrative[cursor:], None))

    primary, secondary = pick["primary"], pick.get("secondary", "")
    quote = pick.get("quote") or (crew.services.citations.text(primary) if primary != GENERAL_DUTY else "")
    rule = f"### {primary}" + (f"\n\nSecondary: **{secondary}**" if secondary else "")
    rule += "\n\n" + _quoted(quote)
    if pick.get("paragraph"):
        rule += (f"\n\nClosest paragraph the search found: **{pick['paragraph']}**. Check that it applies "
                 f"before citing it.\n\n{_quoted(pick.get('paragraph_text', ''))}")  # fmt: skip
    others = [c for c in item.get("candidates", []) if c not in (primary, secondary)][:3]
    if others:
        rule += f"\n\nOther sections the search found: {', '.join(others)}"

    badges = []
    threshold = crew.services.settings.router.min_confidence
    code = f"OIICS {intake['event_code'] or 'not coded'}, confidence {intake['confidence']:.2f}"
    badges.append(badge(code, "ok" if intake["confidence"] >= threshold else "warn"))
    if intake["confidence"] < threshold:
        badges.append(badge(f"below {threshold:.2f}: a person checks the code", "warn"))
    if intake.get("fatality_potential"):
        badges.append(badge("serious injury or fatality potential", "bad"))
    known = citation_known(crew, primary)
    badges.append(badge("in eCFR" if known else f"{primary} is not in eCFR", "ok" if known else "bad"))
    problems = check_citation(IntakeResult.model_validate(intake), primary, secondary, item["report"]["naics"],
                              "1926" in crew.services.registry.retrievers)  # fmt: skip
    badges += [
        badge(p.message if p.fix else f"check: {p.message}", "bad" if p.fix else "warn") for p in problems
    ] or [badge("OSHA domain checks pass", "ok")]
    badges += [badge(f"Category 1: {t['criterion']}", "bad") for t in item.get("category_one", [])]
    questions = intake.get("missing_facts", [])
    asks = (
        ("**Questions the narrative leaves open**\n\n" + "\n".join(f"* {q}" for q in questions))
        if questions
        else ""
    )
    return pieces, rule, f'<div class="sr-badges">{"".join(badges)}</div>', asks


def _history_line(match, report: dict[str, Any], item: dict[str, Any]) -> str:
    """One earlier report, with what decides whether it counts as a Category 1 repeat."""
    months = (date.fromisoformat(str(report["event_date"])[:10]) - match.event_date).days / 30.4
    division = (item["intake"].get("event_code") or "")[:1]
    # The same test as the Analyst's: an earlier report without a code is not ruled out.
    same_kind = not division or not match.event_code_v3 or str(match.event_code_v3).startswith(division)
    repeat = (
        match.status == "same"
        and (date.fromisoformat(str(report["event_date"])[:10]) - match.event_date).days <= 365
        and same_kind
    )
    facts = [
        match.status,
        match.level,
        f"event {match.event_code_v3 or 'not coded'}",
        f"{months:.0f} months before",
    ]
    flag = " **counts as a repeat**" if repeat else ""
    return f"* {match.event_date}, {match.city.title()}: {match.employer} ({', '.join(facts)}){flag}"


def context(crew: Crew, item: dict[str, Any]) -> str:
    """The employer's earlier reports across spellings, and similar injuries in the industry.

    This is what decides whether a borderline report goes up to an inspection: a confirmed repeat
    within a year is a Category 1 criterion, and similar past injuries show a pattern.
    """
    report = item["report"]
    lines = []
    if report["id"] != "new" and report.get("state"):
        history = crew.services.employers(report["state"]).history(
            report["employer"], report["state"], city=report.get("city", ""), zip_code=report.get("zip", ""),
            naics=report["naics"], exclude_id=report["id"])  # fmt: skip
        earlier = [m for m in history if str(m.event_date) < str(report["event_date"])]
        same = [m for m in earlier if m.status == "same"]
        possible = [m for m in earlier if m.status == "possible"]
        lines.append(f"**{report['employer']}**: {len(same)} earlier reports under the same name, "
                     f"{len(possible)} under a spelling a person should confirm.")  # fmt: skip
        lines += [_history_line(m, report, item) for m in earlier[:4]]
    similar = item.get("similar")
    if similar is None and crew.services.similar is not None:
        group = (item["intake"].get("event_code") or report.get("event_code", ""))[:2]
        try:
            similar = [s.__dict__ for s in crew.services.similar.find(report["narrative"], report["naics"], group,
                                                                       exclude=report["id"])]  # fmt: skip
        except Exception:  # an index problem must not hide the rest of the page
            similar = []
    if similar:
        lines.append("\n**Similar injuries in the industry**")
        lines += [
            f"* {s['event_date']}, {s['state'].title()}: {clip(s['narrative'], 220)}" for s in similar[:3]
        ]
    return "\n".join(lines)


def _quoted(text: str) -> str:
    return "\n".join(f"> {line}" for line in clip(text, 900).splitlines() if line.strip()) or "> (no text)"


def _pasted(crew: Crew, session: Session) -> dict[str, Any] | None:
    findings = crew.values(session.ask_thread).get("findings", {})
    return next((f for f in findings.values() if f["kind"] == "single_report"), None)


def _triage(crew: Crew, session: Session) -> dict[str, Any] | None:
    findings = crew.values(session.week_thread).get("findings", {})
    return next((f for f in findings.values() if f["kind"] == "triage"), None)


# ---- This week's reports ----


def inspector_days(value: Any) -> tuple[float | None, str]:
    """Inspector days a person typed: a number from 0 up. Zero is a real week (a holiday week, or an
    office short of staff): the plan then says how many days the Category 1 reports need."""
    if value is None or str(value).strip() == "":
        return None, "Enter the inspector days for the week, 0 or more."
    try:
        days = float(value)
    except (TypeError, ValueError):
        return None, "Inspector days must be a number."
    if not math.isfinite(days) or days < 0:
        return None, "Inspector days cannot be negative."
    if days > MAX_DAYS:
        return None, f"{days:g} inspector days is more than an area office has in a week; check the number."
    return days, ""


def load_week(crew: Crew, session: Session, state: str, days: Any):
    capacity, problem = inspector_days(days)
    if problem or state not in offline.STATES:
        return week_view(crew, session, problem or "Choose a state from the list.")
    session.week_thread, session.week_state = uuid.uuid4().hex, state.upper()
    started = time.perf_counter()
    crew.run(
        session.week_thread,
        {"request": f"Plan this week's inspections in {state} with {capacity:g} inspector days."},
    )
    session.week_seconds = time.perf_counter() - started
    return week_view(crew, session)


def reply_due(sent: date, days: int = RRI_REPLY_DAYS) -> date:
    """The day an RRI reply is due: working days after the letter, federal holidays skipped."""
    from pandas.tseries.holiday import USFederalHolidayCalendar
    from pandas.tseries.offsets import CustomBusinessDay

    return (pd.Timestamp(sent) + CustomBusinessDay(days, calendar=USFederalHolidayCalendar())).date()


def week_rows(crew: Crew, session: Session, show: str = "All") -> pd.DataFrame:
    """The list as a table, narrowed to one part of the work when `show` names it.

    A report needs review when its code is unclear or a model read it again because it was
    severe, unclear or borderline; the others were coded by the rules alone.
    """
    finding = _triage(crew, session)
    if finding is None:
        return pd.DataFrame(columns=WEEK_COLUMNS)
    notes = crew.values(session.week_thread).get("rules", {}).get("notes", {})
    due = reply_due(crew.services.week[1])
    keep = {
        "All": lambda r: True,
        "Category 1": lambda r: bool(r["category_one"]),
        "Needs review": lambda r: _needs_review(crew, finding, r),
        "Inspection": lambda r: r["decision"] == "inspection",
        "RRI letter": lambda r: r["decision"] == "rri_letter",
    }[show if show in FILTERS else "All"]
    rows = [r for r in finding["rows"] if keep(r)]
    return pd.DataFrame(
        [[r["report_id"], r["employer"], DECISION_LABELS[r["decision"]], r["category_one"] or "", r["standard"],
          r["days"], f"{due:%a %d %b}" if r["decision"] == "rri_letter" else "", notes.get(r["report_id"], ""),
          round(r["priority"], 2), "Human check" if _needs_review(crew, finding, r) else "Auto-coded", r["reason"]]
         for r in rows], columns=WEEK_COLUMNS,
    )  # fmt: skip


def _needs_review(crew: Crew, finding: dict[str, Any], row: dict[str, Any]) -> bool:
    item = finding["stage1"][row["report_id"]]
    return row["stage"] == 2 or item["intake"]["confidence"] < crew.services.settings.router.min_confidence


def filters_line(crew: Crew, session: Session, show: str = "All") -> str:
    """What the list is showing, in words, as OSHA's dashboard states its active filters."""
    finding = _triage(crew, session)
    if finding is None:
        return '<div class="sr-filters">No week loaded yet.</div>'
    start, end = crew.services.week
    shown = len(week_rows(crew, session, show))
    parts = [
        session.week_state.title(),
        f"{start:%d %b} to {end:%d %b %Y}",
        f"{finding['capacity']:g} inspector days",
    ]
    if show != "All":
        parts.append(show)
    return (f'<div class="sr-filters"><b>Active filters:</b> {html.escape(", ".join(parts))}. '
            f"Showing {shown} of {len(finding['rows'])} reports.</div>")  # fmt: skip


def download_week(crew: Crew, session: Session, show: str = "All") -> str | None:
    """The rows on screen as CSV, like the dashboard's "Download Selected Data"."""
    table = week_rows(crew, session, show)
    if table.empty:
        return None
    label = show.lower().replace(" ", "_")
    return save(crew, session, f"week_{session.week_state.lower()}_{label}.csv", table.to_csv(index=False))


def week_view(crew: Crew, session: Session, note: str = "", show: str = "All"):
    """Summary cards, the editable list, Category 1 triggers, matches, the chart and the status."""
    finding = _triage(crew, session)
    empty = pd.DataFrame(columns=WEEK_COLUMNS)
    if finding is None:
        message = note or "Choose a state and load the replayed week."
        return (
            "",
            empty,
            _placeholder(TRIGGER_COLUMNS, "Load a week to see its Category 1 reports."),
            _match_frame([]),
            None,
            message,
        )
    plan, rows, values = finding["plan"], finding["rows"], crew.values(session.week_thread)
    table = week_rows(crew, session, show)
    triggers = pd.DataFrame(
        [[rid, item["report"]["employer"], t["criterion"], t["evidence"]]
         for rid, item in finding["stage1"].items() for t in item["category_one"]],
        columns=TRIGGER_COLUMNS,
    )  # fmt: skip
    if triggers.empty:
        triggers = _placeholder(TRIGGER_COLUMNS, "No report meets a Category 1 criterion this week.")
    start, end = crew.services.week
    letters = sum(d == "rri_letter" for d in plan["decisions"].values())
    due = reply_due(end)
    reports = [item["report"] for item in finding["stage1"].values()]
    harm = (sum(int(r["hospitalized"] > 0) for r in reports), sum(int(r["amputation"] > 0) for r in reports),
            sum(int(r["loss_of_eye"] > 0) for r in reports))  # fmt: skip
    left = max(0.0, finding["capacity"] - plan["days_used"])
    tiles = [
        ("alert", "Category 1 (mandatory inspection)", sum(bool(r["category_one"]) for r in rows),
         "criteria of OSHA's 2016 memo"),
        ("inspection", "Proposed inspections", len(rows) - letters,
         f"{plan['days_used']:g} inspector days used, {left:g} left"),
        ("letter", "RRI letters", letters, f"replies due {due:%a %d %b}" if letters else "none this week"),
    ]  # fmt: skip
    if plan["shortfall"]:
        tiles.append(
            (
                "clock",
                "Inspector days short",
                f"{plan['shortfall']:g}",
                "to inspect every report that must be inspected",
            )
        )
    cards = (
        outcome_strip(len(rows), *harm)
        + '<div class="sr-tiles">'
        + "".join(
            f'<div class="sr-tile sr-tile-{icon}"><div class="sr-tile-head">{svg(icon, 15)}<span>{label}</span></div>'
            f'<div class="sr-tile-value">{value}</div><div class="sr-tile-note">{html.escape(sub)}</div></div>'
            for icon, label, value, sub in tiles
        )
        + "</div>"
    )
    approval = values.get("approval")
    if not rows:
        start, end = crew.services.week
        status = (f"**No severe injury reports came from {session.week_state.title()} between {start:%d %B} and "
                  f"{end:%d %B %Y}.** There is nothing to plan or approve.")  # fmt: skip
    elif approval:
        status = f"**Approved** by {approval['by']}. Letters and the list are in Downloads."
    elif "approval" in crew.waiting_for(session.week_thread):
        status = "**Waiting for the Area Director.** Move rows or add a rule, then approve the list."
        if finding.get("capacity_note"):
            status = f"**Inspector days:** {finding['capacity_note']}\n\n" + status
    else:
        status = ""
    log = values.get("decision_log", [])
    if log:
        status += "\n\n" + "\n".join(f"* {e['at']}: {e['by']} {e['action']}" for e in log)
    if note:
        status = f"{note}\n\n{status}"
    matches = week_matches(crew, session)
    return (
        cards,
        table,
        triggers,
        matches,
        picture(sensitivity_chart(finding["sensitivity"], finding["capacity"], _category_one_days(finding))),
        status,
    )


def _category_one_days(finding: dict[str, Any]) -> float:
    return sum(finding["stage1"][r["report_id"]]["days"] for r in finding["rows"] if r["category_one"])


def week_trace(crew: Crew, session: Session) -> str:
    """The routing and audit log of the week: what was checked again, what was corrected, every step."""
    finding = _triage(crew, session)
    values = crew.values(session.week_thread)
    if finding is None:
        return '<div class="sr-empty">Load a week to see how its list was made.</div>'
    review = sum(_needs_review(crew, finding, r) for r in finding["rows"])
    corrected = len(values.get("pick_overrides", {}))
    timing = f" The list took {session.week_seconds:.1f} s." if session.week_seconds else ""
    summary = (f'<p class="sr-audit">{review} reports needed code review; {corrected} auto-verified citations were '
               f"corrected before the list was shown.{timing}</p>")  # fmt: skip
    return summary + trace_html(values.get("trace", []), offline_rules(crew))


def _placeholder(columns: list[str], message: str) -> pd.DataFrame:
    """A one line table that says why it is empty, so a blank box never stands for "nothing"."""
    return pd.DataFrame([[message, *([""] * (len(columns) - 1))]], columns=columns)


def placeholder_figure(message: str):
    """An empty chart that says what would fill it."""
    import plotly.graph_objects as go

    figure = go.Figure()
    figure.add_annotation(text=html.escape(message), showarrow=False, x=0.5, y=0.5, xref="paper", yref="paper",
                          font={"size": 14, "color": MUTED})  # fmt: skip
    figure.update_xaxes(visible=False)
    figure.update_yaxes(visible=False)
    figure.update_layout(height=220, margin={"l": 10, "r": 10, "t": 10, "b": 10}, plot_bgcolor="white",
                         paper_bgcolor="white")  # fmt: skip
    return figure


def week_events(crew: Crew, session: Session):
    """Top five events and exposures in the week, by OSHA's OIICS titles."""
    finding = _triage(crew, session)
    titles = [
        " ".join(str(item["report"].get("event_title", "")).split())
        for item in (finding or {}).get("stage1", {}).values()
    ]
    counts = pd.Series([t for t in titles if t]).value_counts().head(5)
    if counts.empty:
        return None
    return _events_bar(counts.index.tolist(), counts.tolist(), "reports this week")


def move_choices(crew: Crew, session: Session) -> tuple[list[str], list[str]]:
    """Rows that can move: letters to inspection, and inspections (not Category 1) to letters."""
    finding = _triage(crew, session)
    if finding is None:
        return [], []
    letters = [f"{r['report_id']}  {r['employer']}" for r in finding["rows"] if r["decision"] == "rri_letter"]
    inspections = [f"{r['report_id']}  {r['employer']}" for r in finding["rows"]
                   if r["decision"] == "inspection" and not r["category_one"]]  # fmt: skip
    return letters, inspections


def imminent_choices(crew: Crew, session: Session) -> tuple[list[str], list[str]]:
    """Reports the Director may flag as an imminent danger, and the ones flagged now."""
    finding = _triage(crew, session)
    if finding is None:
        return [], []
    flagged = set(crew.values(session.week_thread).get("rules", {}).get("imminent_danger", []))
    labels = {r["report_id"]: f"{r['report_id']}  {r['employer']}" for r in finding["rows"]}
    choices = [labels[r["report_id"]] for r in finding["rows"]
               if r["report_id"] in flagged or not r["category_one"]]  # fmt: skip
    return choices, [labels[i] for i in sorted(flagged) if i in labels]


def _decision(label: Any) -> str | None:
    text = re.sub(r"<[^>]+>", "", str(label)).strip().lower()
    if text in ("inspection", "inspect"):
        return "inspection"
    if text in ("rri letter", "rri_letter", "letter", "rri"):
        return "rri_letter"
    return None


def ask_for_changes(crew: Crew, session: Session, table: pd.DataFrame, capacity: float, rule: str, role: str,
                    to_inspect: list[str] | None = None, to_letter: list[str] | None = None,
                    imminent: list[str] | None = None):  # fmt: skip
    """Send the changed rows, notes and rules back; the run resumes at the Optimizer.

    Rows move with `to_inspect` and `to_letter` (report labels picked from a list, so nothing is
    typed by hand); a Decision edited in the table is read too.
    """
    finding = _triage(crew, session)
    if finding is None or "approval" not in crew.waiting_for(session.week_thread):
        return week_view(crew, session, "Load a week first; an approved list cannot be changed.")
    if not finding["rows"]:
        return week_view(crew, session, "An empty week has nothing to change.")
    planned = finding["plan"]["decisions"]
    must = {r["report_id"] for r in finding["rows"] if r["category_one"]}
    force_inspection, force_letter, notes = [], [], {}
    for row in table.to_dict("records"):
        report_id, wanted = str(row["Report"]), _decision(row["Decision"])
        if wanted is None:
            return week_view(crew, session, f"Row {report_id}: write Inspection or RRI letter.")
        if wanted == "rri_letter" and report_id in must:
            return week_view(crew, session, f"Row {report_id} meets Category 1, so it must be inspected.")
        if wanted != planned.get(report_id):
            (force_inspection if wanted == "inspection" else force_letter).append(report_id)
        notes[report_id] = str(row.get("Note") or "").strip()
    for label in to_inspect or []:
        report_id = label.split()[0]
        if report_id not in force_inspection and planned.get(report_id) != "inspection":
            force_inspection.append(report_id)
    for label in to_letter or []:
        report_id = label.split()[0]
        if report_id in must:
            return week_view(crew, session, f"Row {report_id} meets Category 1, so it must be inspected.")
        if report_id not in force_letter and planned.get(report_id) != "rri_letter":
            force_letter.append(report_id)
    employers = [name.strip() for name in (rule or "").split(",") if name.strip()]
    days, problem = inspector_days(capacity)
    if problem:
        return week_view(crew, session, problem)
    resume = {"action": "changes", "by": role, "force_inspection": force_inspection, "force_letter": force_letter,
              "inspect_employers": employers, "notes": notes, "capacity": days}  # fmt: skip
    flagged_before = set(crew.values(session.week_thread).get("rules", {}).get("imminent_danger", []))
    if imminent is not None:
        resume["imminent_danger"] = [label.split()[0] for label in imminent]
    crew.run(session.week_thread, Command(resume=resume))
    changed = len(force_inspection) + len(force_letter)
    flagged = set(resume.get("imminent_danger", flagged_before))
    note = (f"Plan updated with {changed} changed rows"
            + (f" and a rule for {', '.join(employers)}" if employers else "") + "."
            + (f" Now Category 1 as an imminent danger: {', '.join(sorted(flagged - flagged_before))}."
               if flagged - flagged_before else "")
            + (f" No longer flagged as an imminent danger: {', '.join(sorted(flagged_before - flagged))}."
               if flagged_before - flagged else ""))  # fmt: skip
    return week_view(crew, session, note + _moves(planned, _triage(crew, session)))


def _moves(before: dict[str, str], finding: dict[str, Any]) -> str:
    """Every row whose decision changed, the ones the person asked for and the ones that followed."""
    rows = {r["report_id"]: r for r in finding["rows"]}
    moved = [
        rows[rid] for rid, decision in finding["plan"]["decisions"].items() if before.get(rid) != decision
    ]
    if not moved:
        return " No row changed."
    lines = [f"* {r['report_id']} {r['employer']}: now {DECISION_LABELS[r['decision']].lower()} ({r['reason']})"
             for r in moved]  # fmt: skip
    return "\n\n**What changed**\n\n" + "\n".join(lines)


def approve(crew: Crew, session: Session, role: str):
    """The Area Director approves; the letters and the list are written for download."""
    if role != APPROVER:
        return (*week_view(crew, session, "Only the Area Director approves the list."), "")
    week = _triage(crew, session)
    if week is not None and not week["rows"]:
        return (*week_view(crew, session, "An empty week has nothing to approve."), "")
    if "approval" not in crew.waiting_for(session.week_thread):
        return (*week_view(crew, session, "There is no list waiting for approval."), "")
    open_matches = unresolved_matches(crew, session)
    if open_matches and session.approve_warned != session.week_thread:
        # A confirmed match can make a report Category 1, so the Director sees this before approving.
        session.approve_warned = session.week_thread
        warning = (f"{open_matches} possible employer matches are not answered yet; a confirmed match can make a "
                   "report Category 1. Answer them in the matches panel, or press Approve again to approve as is.")  # fmt: skip
        return (*week_view(crew, session, warning), "")
    out = crew.run(session.week_thread, Command(resume={"action": "approve", "by": role}))
    values = crew.values(session.week_thread)
    finding = _triage(crew, session)
    save(crew, session, "inspection_list.csv", finding["csv"])
    letters = [rendered(d) for k, d in sorted(values.get("drafts", {}).items()) if ":letter_" in k]
    if letters:
        save(crew, session, "rri_letters.docx", word_document("\n\n".join(letters)))
    save(crew, session, "week_summary.docx", word_document(out.get("answer", "")))
    reminder = (f"Approved with {open_matches} employer matches unanswered; answering them can add repeats "
                "and Category 1 reports next week." if open_matches else "")  # fmt: skip
    return (*week_view(crew, session, reminder), out.get("answer", ""))


def week_matches(crew: Crew, session: Session) -> pd.DataFrame:
    """Possible employer matches in the week, one row per pair of spellings, with what tells them apart."""
    finding = _triage(crew, session)
    if finding is None:
        return _match_frame([])
    index = crew.services.employers(session.week_state)
    earlier = index.frame.set_index("id")
    answered = index.decisions  # every yes or no saved so far, in this state and others
    pairs: dict[frozenset[str], list] = {}
    for item in finding["stage1"].values():
        report = item["report"]
        for match in index.history(report["employer"], report["state"], city=report.get("city", ""),
                                   zip_code=report.get("zip", ""), naics=report["naics"], exclude_id=report["id"]):  # fmt: skip
            key = frozenset((normalize_name(report["employer"]), normalize_name(match.employer)))
            # The same name in another industry is a question of site, not of spelling.
            if match.status != "possible" or len(key) == 1:
                continue
            naics = str(earlier.loc[match.report_id, "naics"]) if match.report_id in earlier.index else ""
            row = pairs.setdefault(key, [report["employer"], report.get("city", "").title(), match.employer,
                                         match.city.title(), str(match.event_date),
                                         "yes" if naics[:3] == report["naics"][:3] else f"no ({naics[:3]})", 0,
                                         round(match.score), _answer(answered.get(key))])  # fmt: skip
            row[4] = max(row[4], str(match.event_date))
            row[6] += 1
    rows = sorted(pairs.values(), key=lambda r: -r[7])
    return (
        _match_frame(rows)
        if rows
        else _placeholder(MATCH_COLUMNS, "No possible employer matches to resolve.")
    )


def _answer(decided: bool | None) -> str:
    return "" if decided is None else ("yes" if decided else "no")


def unresolved_matches(crew: Crew, session: Session) -> int:
    """Possible matches nobody has answered yet; the placeholder line is not one."""
    table = week_matches(crew, session)
    if table.empty or str(table.iloc[0]["This week"]).startswith("No possible"):
        return 0
    return int((table["Same employer?"].astype(str).str.strip() == "").sum())


def _match_frame(rows: list) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=MATCH_COLUMNS)


def save_matches(crew: Crew, session: Session, table: pd.DataFrame, role: str):
    """Store each yes or no; one decision settles every report with that pair of spellings."""
    if not session.week_state:
        return week_matches(crew, session), "Load a week first."
    index = crew.services.employers(session.week_state)
    saved = 0
    for row in table.to_dict("records"):
        answer = str(row.get("Same employer?") or "").strip().lower()
        if answer in ("yes", "no"):
            index.decide(row["This week"], row["Earlier spelling"], answer == "yes", by=role)
            saved += 1
    if not saved:
        return week_matches(crew, session), "Write yes or no in the last column, then save."
    return week_matches(crew, session), (f"Saved {saved} decisions. They apply to every report with those spellings. "
                                         "Repeats and Category 1 are recounted when the week is loaded again, which "
                                         "starts a new list without the moves made so far.")  # fmt: skip


def week_map(crew: Crew, session: Session):
    """The week's reports where they happened: colour by decision, size by priority."""
    import plotly.graph_objects as go

    finding = _triage(crew, session)
    if finding is None:
        return None
    ids = [r["report_id"] for r in finding["rows"]]
    places = crew.services.store.frame(
        "SELECT id, latitude, longitude, city FROM reports WHERE list_contains(?, id)", [ids]
    ).set_index("id")
    groups = {"Category 1": "#b3261e", "Inspection": "#1d4e89", "RRI letter": "#c58a00"}
    figure = go.Figure()
    for label, colour in groups.items():
        rows = [r for r in finding["rows"] if (label == "Category 1") == bool(r["category_one"])
                and (label == "Category 1" or DECISION_LABELS[r["decision"]] == label)]  # fmt: skip
        rows = [
            r
            for r in rows
            if r["report_id"] in places.index and pd.notna(places.loc[r["report_id"], "latitude"])
        ]
        if not rows:
            continue
        figure.add_trace(go.Scattermap(
            lat=[places.loc[r["report_id"], "latitude"] for r in rows],
            lon=[places.loc[r["report_id"], "longitude"] for r in rows],
            mode="markers", name=label,
            marker={"size": [9 + 2.2 * r["priority"] for r in rows], "color": colour, "opacity": 0.8},
            text=[f"<b>{html.escape(r['employer'])}</b><br>{html.escape(str(places.loc[r['report_id'], 'city']).title())}"
                  f"<br>{r['report_id']}, {r['standard']}<br>{html.escape(r['reason'])}" for r in rows],
            hovertemplate="%{text}<extra></extra>",
        ))  # fmt: skip
    if not figure.data:
        return None
    lats = places["latitude"].dropna()
    lons = places["longitude"].dropna()
    span = max(lats.max() - lats.min(), lons.max() - lons.min(), 0.5)
    figure.update_layout(
        map={"style": "carto-positron", "center": {"lat": float(lats.mean()), "lon": float(lons.mean())},
             "zoom": float(np.clip(np.log2(360 / span) - 0.9, 2.5, 11))},
        margin={"l": 0, "r": 0, "t": 0, "b": 0}, height=420,
        legend={"orientation": "h", "x": 0.01, "y": 0.01, "xanchor": "left", "yanchor": "bottom",
                "bgcolor": "rgba(255,255,255,0.88)", "font": {"size": 12}},
    )  # fmt: skip
    return figure


# ---- Trends and safety talks ----


def trend_view(crew: Crew, state: str, industry: str, hazard: str, start_year: float):
    """Reports per year on a like for like basis, for the plant safety manager."""
    start = int(start_year)
    filters = Filters(state="" if state == "All states" else state.upper(), naics_prefix=INDUSTRY_CHOICES[industry],
                      event_group_v3=HAZARD_CHOICES[hazard], start=date(start, 1, 1))  # fmt: skip
    frame = crew.services.store.yearly_trend(filters)
    frame = frame[frame["year"] >= start]
    place = "all states" if state == "All states" else state.title()
    subject = f"{hazard if hazard != 'All events' else 'Severe injury reports'}, {industry.lower()}, {place}"
    if frame.empty or not frame["reports"].any():
        return None, pd.DataFrame(), f"No report matches {subject.lower()}."
    last = crew.services.store.last_date()
    table = pd.DataFrame({
        "Year": [f"{y} (Jan to {last:%b})" if partial else str(y) for y, partial in zip(frame["year"], frame["partial"], strict=True)],
        "Reports": frame["reports"],
        "Same months": frame["same_months"],
        "Change": [f"{c:+.0%}" if pd.notna(c) else "" for c in frame["change"]],
        "Codes estimated": [f"{e:.0%}" for e in frame["estimated_share"]],
    })  # fmt: skip
    note = (f"{last.year} runs from January to {last:%B}, so every year is counted over the same months. "
            "Before 2024 the event codes are estimated from the narrative (OSHA moved to OIICS 3).")  # fmt: skip
    return outcome_figure(crew, filters, start, last), table, note


INK, MUTED, BLUE = "#1b1b1b", "#565c65", "#005ea2"
# The outcome colours of OSHA's Severe Injury Dashboard: reports, hospitalized, amputations, eye.
OUTCOME_COLOURS = {"reports": "#d83933", "hospitalized": "#2e8540", "amputation": "#2378c3", "eye": "#e5a000"}
EVENT_COLOURS = ["#3e6db5", "#f28e2b", "#3a9a46", "#a55aa0", "#b0a597"]
STATE_CODES = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR", "CALIFORNIA": "CA", "COLORADO": "CO",
    "CONNECTICUT": "CT", "DELAWARE": "DE", "DISTRICT OF COLUMBIA": "DC", "FLORIDA": "FL", "GEORGIA": "GA",
    "HAWAII": "HI", "IDAHO": "ID", "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS", "KENTUCKY": "KY",
    "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD", "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN",
    "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV", "NEW HAMPSHIRE": "NH",
    "NEW JERSEY": "NJ", "NEW MEXICO": "NM", "NEW YORK": "NY", "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND",
    "OHIO": "OH", "OKLAHOMA": "OK", "OREGON": "OR", "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI",
    "SOUTH CAROLINA": "SC", "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT", "VERMONT": "VT",
    "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV", "WISCONSIN": "WI", "WYOMING": "WY",
}  # fmt: skip
# States whose OSHA approved State Plan covers private employers: their reports go to the state, not to
# this federal file, so the map marks them instead of showing them as safe.
STATE_PLAN = {"AK", "AZ", "CA", "HI", "IN", "IA", "KY", "MD", "MI", "MN", "NV", "NM", "NC", "OR", "SC", "TN", "UT",
              "VT", "VA", "WA", "WY"}  # fmt: skip


def outcome_figure(crew: Crew, filters: Filters, start: int, last: date):
    """Reports and their outcomes per year, as OSHA's dashboard draws them, over the same months."""
    import plotly.graph_objects as go

    where, params = filters.where()
    frame = crew.services.store.frame(
        f"SELECT year, count(*) AS reports, count(*) FILTER (WHERE hospitalized > 0) AS hospitalized, "  # noqa: S608 (fixed fragments, parameter values)
        f"count(*) FILTER (WHERE amputation > 0) AS amputation, count(*) FILTER (WHERE loss_of_eye > 0) AS eye "
        f"FROM reports WHERE {where} AND month <= ? GROUP BY year ORDER BY year", [*params, last.month],
    )  # fmt: skip
    frame = frame[frame["year"] >= start]
    if frame.empty:
        return None
    labels = [f"{y}*" if y == last.year and last.month < 12 else str(y) for y in frame["year"]]
    figure = go.Figure()
    series = [("reports", "Total reports", "circle"), ("hospitalized", "Total hospitalized", "cross"),
              ("amputation", "Total amputations", "diamond"), ("eye", "Total loss of eye(s)", "square")]  # fmt: skip
    for column, name, symbol in series:
        figure.add_trace(go.Scatter(
            x=labels, y=frame[column], name=name, mode="lines+markers",
            line={"color": OUTCOME_COLOURS[column], "width": 2},
            marker={"symbol": symbol, "size": 9, "color": OUTCOME_COLOURS[column], "line": {"color": "#1b1b1b", "width": 1}},
            hovertemplate=f"%{{x}}<br>{name}: %{{y:,}}<extra></extra>",
        ))  # fmt: skip
    figure.update_yaxes(title_text="Number of reports")
    figure = _plain_layout(figure, height=340)
    figure.update_layout(showlegend=True, legend={"orientation": "h", "y": 1.12, "x": 0.5, "xanchor": "center"},
                         margin={"l": 60, "r": 20, "t": 40, "b": 40})  # fmt: skip
    return figure


def state_map(crew: Crew, industry: str, hazard: str, start_year: float, selected: str = "All states"):
    """Reports by state for the industry and event, with State Plan states marked, as OSHA maps them."""
    import plotly.graph_objects as go

    filters = Filters(naics_prefix=INDUSTRY_CHOICES[industry], event_group_v3=HAZARD_CHOICES[hazard],
                      start=date(int(start_year), 1, 1))  # fmt: skip
    where, params = filters.where()
    frame = crew.services.store.frame(
        f"SELECT upper(state) AS state, count(*) AS n FROM reports WHERE {where} GROUP BY 1",  # noqa: S608 (fixed fragments, parameter values)
        params,
    )
    counts = {
        STATE_CODES[s]: int(n) for s, n in zip(frame["state"], frame["n"], strict=True) if s in STATE_CODES
    }
    federal = [c for c in STATE_CODES.values() if c not in STATE_PLAN]
    figure = go.Figure()
    figure.add_trace(go.Choropleth(
        locations=federal, z=[counts.get(c, 0) for c in federal], locationmode="USA-states",
        colorscale=[[0, "#eef6ef"], [1, "#2e8540"]], marker_line_color="#ffffff", marker_line_width=0.8,
        colorbar={"title": {"text": "reports"}, "thickness": 12, "len": 0.7},
        hovertemplate="%{location}: %{z:,} reports<extra></extra>",
    ))  # fmt: skip
    plan = sorted(STATE_PLAN)
    figure.add_trace(go.Choropleth(
        locations=plan, z=[1] * len(plan), locationmode="USA-states", showscale=False,
        colorscale=[[0, "#d9d9d9"], [1, "#d9d9d9"]], marker_line_color="#ffffff", marker_line_width=0.8,
        hovertemplate="%{location}: State Plan state, reports go to the state<extra></extra>",
    ))  # fmt: skip
    code = STATE_CODES.get(selected.upper())
    if code:
        figure.add_trace(go.Choropleth(
            locations=[code], z=[0], locationmode="USA-states", showscale=False, hoverinfo="skip",
            colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]], marker_line_color="#1b1b1b", marker_line_width=2.5,
        ))  # fmt: skip
    figure.update_layout(geo={"scope": "usa", "showlakes": False, "bgcolor": "white"}, height=380,
                         margin={"l": 0, "r": 0, "t": 0, "b": 0}, paper_bgcolor="white")  # fmt: skip
    return figure


def _plain_layout(figure, height: int = 320):
    figure.update_layout(
        height=height, margin={"l": 50, "r": 20, "t": 10, "b": 40}, plot_bgcolor="white", paper_bgcolor="white",
        font={"family": "Public Sans, system-ui, sans-serif", "color": INK, "size": 12}, showlegend=False,
        hoverlabel={"bgcolor": "white", "font_size": 12},
    )  # fmt: skip
    figure.update_xaxes(showgrid=False, linecolor="#d6dde5")
    figure.update_yaxes(gridcolor="#eef1f4", zeroline=False, rangemode="tozero")
    return figure


def trend_figure(frame: pd.DataFrame, last: date):
    """Reports per year over the same months; estimated years are hollow, the partial year is named."""
    import plotly.graph_objects as go

    estimated = frame["estimated_share"] > 0.5
    labels = [
        f"{y}, Jan to {last:%b}" if partial else str(y)
        for y, partial in zip(frame["year"], frame["partial"], strict=True)
    ]
    hover = [f"<b>{label}</b><br>{same:,} reports in the same months<br>{total:,} in the whole year"
             + (f"<br>{change:+.0%} on the year before" if pd.notna(change) else "")
             + ("<br>event codes estimated from the narrative" if est else "")
             for label, same, total, change, est in zip(labels, frame["same_months"], frame["reports"], frame["change"],
                                                        estimated, strict=True)]  # fmt: skip
    figure = go.Figure(go.Scatter(
        x=frame["year"], y=frame["same_months"], mode="lines+markers", line={"color": INK, "width": 2.5},
        marker={"size": 9, "color": ["white" if e else INK for e in estimated], "line": {"color": INK, "width": 2}},
        text=hover, hovertemplate="%{text}<extra></extra>",
    ))  # fmt: skip
    figure.update_xaxes(dtick=1)
    figure.update_yaxes(title_text="reports, same months")
    if estimated.any():
        figure.add_annotation(x=frame["year"][estimated].iloc[0], y=frame["same_months"][estimated].iloc[0],
                              text="hollow: codes estimated", showarrow=False, yshift=18, font={"color": MUTED, "size": 11})  # fmt: skip
    return _plain_layout(figure)


def top_events(crew: Crew, state: str, industry: str):
    """How people get hurt in this industry and state, by OSHA's own event titles since 2024.

    A plant's own history is too thin to rank hazards (most employers file one report in eleven
    years), so the industry's reports stand in. Only OIICS 3 titles are used, so nothing is estimated.
    """

    where = ["year >= 2024", "event_title <> ''"]
    params: list[Any] = []
    if state != "All states":
        where.append("upper(state) = ?")
        params.append(state.upper())
    if INDUSTRY_CHOICES[industry]:
        where.append("starts_with(naics, ?)")
        params.append(INDUSTRY_CHOICES[industry])
    frame = crew.services.store.frame(
        f"SELECT trim(regexp_replace(event_title, '\\s+', ' ', 'g')) AS event, count(*) AS n FROM reports "  # noqa: S608 (fixed fragments, parameter values)
        f"WHERE {' AND '.join(where)} GROUP BY 1 ORDER BY 2 DESC LIMIT 5", params,
    )  # fmt: skip
    if frame.empty:
        return None, "No report since January 2024 matches this industry and state."
    total = int(frame["n"].sum())
    place = "all states" if state == "All states" else state.title()
    figure = _events_bar(frame["event"].tolist(), frame["n"].tolist(), "reports since January 2024")
    return figure, (f"Top five events and exposures in {industry.lower()}, {place}, since OSHA moved to OIICS 3 "
                    f"({total:,} reports in these five).")  # fmt: skip


def _events_bar(events: list[str], counts: list[int], axis: str):
    import plotly.graph_objects as go

    events, counts = events[::-1], counts[::-1]
    figure = go.Figure(go.Bar(
        x=counts, y=["<br>".join(textwrap.wrap(e[0].upper() + e[1:], 32)) for e in events], orientation="h",
        marker_color=EVENT_COLOURS[: len(events)][::-1], text=counts, textposition="outside", cliponaxis=False,
        hovertemplate="%{y}<br>%{x} reports<extra></extra>",
    ))  # fmt: skip
    figure.update_xaxes(title_text=axis)
    figure = _plain_layout(figure, height=70 + 52 * len(events))
    figure.update_layout(margin={"l": 10, "r": 40, "t": 10, "b": 50})
    figure.update_yaxes(automargin=True)
    return figure


def trend_tiles(crew: Crew, state: str, industry: str, hazard: str, start_year: float) -> str:
    """The selection in OSHA's dashboard figures: reports, hospitalized, amputations, loss of an eye."""
    where, params = _trend_filters(state, industry, hazard, start_year).where()
    total, hospital, amputation, eye = crew.services.store.con.cursor().execute(
        f"SELECT count(*), count(*) FILTER (WHERE hospitalized > 0), count(*) FILTER (WHERE amputation > 0), "  # noqa: S608 (fixed fragments, parameter values)
        f"count(*) FILTER (WHERE loss_of_eye > 0) FROM reports WHERE {where}", params,
    ).fetchone()  # fmt: skip
    return outcome_strip(total, hospital, amputation, eye)


def outcome_strip(total: int, hospital: int, amputation: int, eye: int) -> str:
    figures = [("Total Severe Injury Reports", total, "reports"), ("Total Workers Hospitalized", hospital, "hospitalized"),
               ("Total Workers with Amputations", amputation, "amputation"), ("Total Workers with Loss of an Eye", eye, "eye")]  # fmt: skip
    return (
        '<div class="sr-outcomes">'
        + "".join(
            f'<div class="sr-outcome"><div class="sr-outcome-label">{label}</div>'
            f'<div class="sr-outcome-value" style="color:{OUTCOME_COLOURS[key]}">{value:,}</div></div>'
            for label, value, key in figures
        )
        + "</div>"
    )


def trend_filters_line(crew: Crew, state: str, industry: str, hazard: str, start_year: float) -> str:
    return (f'<div class="sr-filters"><b>Active filters:</b> {html.escape(state)}, {html.escape(industry)}, '
            f"{html.escape(hazard)}, from {int(start_year)} to {crew.services.store.last_date():%B %Y}.</div>")  # fmt: skip


def download_trend(
    crew: Crew, session: Session, state: str, industry: str, hazard: str, start_year: float
) -> str:
    """Every report in the selection as CSV, like the dashboard's "Download Selected Data"."""
    where, params = _trend_filters(state, industry, hazard, start_year).where()
    frame = crew.services.store.frame(
        f"SELECT id, event_date, employer AS establishment_name, city, state, naics, hospitalized, amputation, "  # noqa: S608 (fixed fragments, parameter values)
        f"loss_of_eye, event_title, source_title, narrative FROM reports WHERE {where} ORDER BY event_date", params,
    )  # fmt: skip
    name = f"reports_{state}_{industry}_{hazard}_{int(start_year)}".lower().replace(" ", "_")
    return save(crew, session, f"{name}.csv", frame.to_csv(index=False))


def _trend_filters(state: str, industry: str, hazard: str, start_year: float) -> Filters:
    return Filters(state="" if state == "All states" else state.upper(), naics_prefix=INDUSTRY_CHOICES[industry],
                   event_group_v3=HAZARD_CHOICES[hazard], start=date(int(start_year), 1, 1))  # fmt: skip


def safety_talk(
    crew: Crew, session: Session, topic: str, extra: Any = "es", state_name: str = "", industry_name: str = ""
):
    """A talk for the next shift in English, and in at most one more language for the floor crew.

    `extra` is a code or a label from TALK_LANGUAGE_CHOICES ("Vietnamese (vi)"); True and False are
    still read as Spanish or English only, as the first version of this control sent them.
    """
    topic = (topic or "").strip().lower()
    if topic not in TALK_TOPICS:
        return f"Choose a topic for the talk: {', '.join(TALK_TOPICS)}.", []
    code, problem = extra_language("es" if extra is True else ("" if extra is False else extra))
    if problem:
        return problem, []
    thread = uuid.uuid4().hex
    language = f" in English and {LANGUAGES[code]}" if code else ""
    # The talk counts injuries in the plants the page is filtered to, so it says "plants like yours".
    params = {"naics_prefix": INDUSTRY_CHOICES.get(industry_name, "3")}
    if state_name and state_name != "All states":
        params["state"] = state_name.upper()
    request = f"Write a {topic} safety talk for the next shift{language}."
    out = crew.run(thread, {"request": request, "params": params})
    names = []
    talk = next(
        (f for f in crew.values(thread).get("findings", {}).values() if f["kind"] == "safety_talk"), {}
    )
    widened = (
        f"\n\n_The count is for {talk['scope']}: the plants this page is filtered to report fewer than "
        f"{TALK_MIN_REPORTS} such injuries._"
        if talk.get("widened")
        else ""
    )
    for key, draft in sorted(crew.values(thread).get("drafts", {}).items()):
        if ":talk_" in key:
            language_code = key.rsplit("_", 1)[1]
            names.append(save(crew, session, f"safety_talk_{topic.replace(' ', '_')}_{language_code}.docx",
                              word_document(rendered(draft), language_code)))  # fmt: skip
    return out.get("answer", "") + widened, names


# ---- AI controls and evaluation ----


@dataclass
class Outage:
    """A provider made to fail with server errors, to show the fallback chain at work."""

    name: str

    def complete(self, step: str, prompt: str):
        raise ModelError("server_error", self.name)


def models_table(crew: Crew) -> pd.DataFrame:
    live = _live_scores()
    rows = []
    for spec in crew.services.settings.models:
        backend = crew.services.router.backends.get(spec.name)
        if backend is None:
            # Started with --live --mode private, cloud models are left out even when a key is set.
            status = "no key or server, or left out in private mode"
        elif isinstance(backend, Outage):
            status = "outage (simulated)"
        else:
            status = "offline rules" if type(backend).__name__ == "OfflineBackend" else "live"
        price = f"${spec.prices[0]:g} / ${spec.prices[1]:g}" if spec.prices else "not confirmed"
        measured = live.get(spec.name, {}).get("strict_at_3", {}).get("rate")
        rows.append([spec.label, spec.provider, spec.model_id, price, status, f"{spec.prior['retrieve']:.0%}" if "retrieve" in spec.prior else "",
                     f"{measured:.1%}" if measured is not None else ""])  # fmt: skip
    return pd.DataFrame(rows, columns=["Model", "Provider", "Model ID", "Price per M tokens (in / out)", "Status",
                                       "Routing prior, retrieval", "Measured on the key, top 3 (not used to route)"])  # fmt: skip


def mode_label(mode: str) -> str:
    """The routing page's label for a mode, so the page opens on the mode the app started with."""
    return next(label for label, value in MODES.items() if value == mode)


def apply_controls(crew: Crew, mode_label: str, redact: bool, outages: list[str]):
    """Routing mode, redaction and simulated outages. Returns a message and the model table."""
    names = {spec.label: spec.name for spec in crew.services.settings.models}
    down = {names[label] for label in outages or []}
    if not set(crew.backends) - down:
        return "At least one model must stay up.", models_table(crew)
    mode = MODES[mode_label]
    if mode == "private" and not any(
        crew.services.settings.model(n).is_local for n in set(crew.backends) - down
    ):
        return "Private mode needs the local model up.", models_table(crew)
    router = crew.services.router
    router.backends = {
        name: Outage(name) if name in down else backend for name, backend in crew.backends.items()
    }
    router.down.clear()  # a fresh start: every model is tried again under the new settings
    crew.services.mode = mode
    crew.services.redact_for_cloud = bool(redact)
    up = len(crew.backends) - len(down)
    message = (f"{mode_label}; redaction {'on' if redact else 'off'}; {up} of {len(crew.backends)} models up"
               + (f"; calls to {', '.join(sorted(outages))} fail and fall back." if down else "."))  # fmt: skip
    return message, models_table(crew)


def usage_table(crew: Crew) -> pd.DataFrame:
    rows = crew.services.router.log.rows()[-300:]
    frame = pd.DataFrame(rows, columns=["at", "run_id", "node", "step", "model", "reason", "fallback_from",
                                        "input_tokens", "output_tokens", "cost", "seconds", "error"])  # fmt: skip
    return frame.iloc[::-1].rename(columns={"at": "Time", "node": "Agent step", "step": "Step type", "model": "Model",
                                            "reason": "Why this model", "fallback_from": "Fell back from",
                                            "input_tokens": "Tokens in", "output_tokens": "Tokens out",
                                            "cost": "Cost ($)", "seconds": "Seconds", "error": "Error"}).drop(columns="run_id")  # fmt: skip


def data_table(crew: Crew) -> pd.DataFrame:
    """What the crew works on, and how big it is: the scale page for the admin."""
    services = crew.services
    store = services.store
    count, first, last = (
        store.con.cursor()
        .execute("SELECT count(*), min(event_date), max(event_date) FROM reports")
        .fetchone()
    )
    paragraphs = len({p.citation for group in services.citations.under.values() for p in group})
    rows = [["Severe injury reports", f"{count:,}", f"{first:%B %Y} to {last:%B %Y}, DuckDB over Parquet"],
            ["eCFR paragraphs", f"{paragraphs:,}", "Part 1910, every part on disk is read"]]  # fmt: skip
    for source, retriever in services.registry.retrievers.items():
        kind = "BM25 and embeddings" if retriever.faiss is not None else "BM25"
        rows.append([f"Index: {source.replace('_', ' ')}", f"{len(retriever.documents):,}", kind])
    if services.similar is not None:
        rows.append(["Similar injury search", f"{count:,}", services.similar.method])
    rows.append(["Event coder", "OIICS 3", "TF-IDF and SGD, trained outside the holdout"])
    from safereport.spend import CACHE_FILE, SpendLedger

    if CACHE_FILE.exists():
        rows.append(
            [
                "Paid model calls",
                f"${SpendLedger(CACHE_FILE).spent():.2f}",
                "of the team's $1.50 cap, every reply cached",
            ]
        )
    return pd.DataFrame(rows, columns=["What", "Size", "How"])


def _live_scores() -> dict[str, Any]:
    path = RESULTS_DIR / "live_terms_summary.json"
    return json.loads(path.read_text())["models"] if path.exists() else {}


def evaluation(crew: Crew):
    """The Pareto chart and the result tables, all read from eval/results."""
    phase1 = RESULTS_DIR / "phase1_baselines.json"
    if not phase1.exists():
        return None, pd.DataFrame(), pd.DataFrame(), "Run `safereport eval-baselines` to fill this page."
    results = json.loads(phase1.read_text())
    coding = results["event_baseline"]
    levels = {
        "full_code": "full code",
        "group_2_digit": "two digit group",
        "division_1_digit": "one digit division",
    }
    coding_table = pd.DataFrame(
        [[label, f"{coding['accuracy'][key]:.1%}", _interval(coding["accuracy_ci95"][key])] for key, label in levels.items()],
        columns=["Event coding, 1,000 report 2025 holdout", "Accuracy", "95% interval"],
    )  # fmt: skip
    base = results["retrieval"]["hybrid_narrative_and_codes"]
    points = [
        {"label": "no model", "cost": 0.0, "accuracy": base["strict_at_3"], "ci95": base["strict_at_3_ci95"]}
    ]
    rows = [
        [
            "No model (BM25 and embeddings)",
            f"{base['strict_at_3']:.1%}",
            _interval(base["strict_at_3_ci95"]),
            "",
            "",
            "$0",
        ]
    ]
    labels = {spec.name: spec.label for spec in crew.services.settings.models}
    for name, scores in _live_scores().items():
        run = json.loads((RESULTS_DIR / f"live_terms_{name}.json").read_text())
        spend = next((s for s in run["spend"] if s["model"] == name), None)
        per_run = spend["cost"] / spend["calls"] * scores["cases"] if spend and spend["calls"] else 0.0
        strict = scores["strict_at_3"]
        points.append(
            {
                "label": labels.get(name, name),
                "cost": per_run,
                "accuracy": strict["rate"],
                "ci95": strict["ci95"],
            }
        )
        rows.append([f"{labels.get(name, name)} terms", f"{strict['rate']:.1%}", _interval(strict["ci95"]),
                     f"{strict['gained']} / {strict['lost']}", f"{strict['mcnemar_p']:g}", f"${per_run:.3f}"])  # fmt: skip
    retrieval = pd.DataFrame(rows, columns=["Standards retrieval, 51 cases", "Top 3", "95% interval",
                                            "Gained / lost", "Paired p", "Cost per run"])  # fmt: skip
    note = ("Standards retrieval is measured on the answer key, the final test set: no prompt, weight or threshold "
            "was tuned on it, and the router does not use these numbers. Event coding is measured on the 2025 "
            "holdout, which the baseline never saw. The cost of a run is the average cost per call times 51.")  # fmt: skip
    return picture(pareto_chart(points)), coding_table, retrieval, note


def _interval(bounds: list[float]) -> str:
    return f"{bounds[0]:.1%} to {bounds[1]:.1%}"


__all__ = ["APPROVER", "HOME", "ROLES", "Crew", "Session"]
