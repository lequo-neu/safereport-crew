"""The Gradio app: one view per role over the same crew.

Sign in is off unless SAFEREPORT_PASSWORD is set; then the four demo accounts (triage,
director, manager, admin) share that password and each opens on its role's view. Without it,
the role is picked at the top of the page. Every handler lives in `views.py`.
"""

from __future__ import annotations

import hmac
import html
import os

import gradio as gr
import pandas as pd

from safereport import offline, views
from safereport.icons import svg, tab_script
from safereport.views import APPROVER, HOME, ROLES, Crew, Session


ACCOUNTS = {"triage": "Triage officer", "director": "Area Director", "manager": "Plant safety manager",
            "admin": "Admin"}  # fmt: skip
# One line per role: the job the page is for, in the order the person does it.
ROLE_HINTS = {
    "Triage officer": "Clear Category 1 first, then the reports that need review.",
    "Area Director": "Read the doubtful cases and their letters, then approve the list.",
    "Plant safety manager": "See how your industry gets hurt, then print the next shift's talk.",
    "Admin": "Set routing and privacy, and check model cost and accuracy.",
}
FEDERAL = gr.themes.Color(
    c50="#eef3f9", c100="#d8e3f1", c200="#b1c7e3", c300="#86a6d0", c400="#5882b8", c500="#2f629f",
    c600="#1d4e89", c700="#173f70", c800="#122f54", c900="#0c2039", c950="#081526", name="federal",
)  # fmt: skip

CSS = """
:root { --sr-ink: #1b1b1b; --sr-muted: #565c65; --sr-rule: #dfe1e2; --sr-paper: #ffffff; --sr-desk: #f0f0f0;
  --sr-navy: #1a4480; --sr-blue: #005ea2; --sr-link: #005ea2; --sr-red: #b3261e; --sr-red-bg: #fbe9e7;
  --sr-amber: #8a5a00; --sr-amber-bg: #fff1cc; --sr-green: #2e8540; --sr-green-bg: #e3f2e5; --sr-chip: #e7f2f8;
  --sr-hover: #f0f0f0; --sr-serif: "Merriweather", Georgia, "Times New Roman", serif; }
.dark { --sr-ink: #f0f0f0; --sr-muted: #a9aeb1; --sr-rule: #3d4551; --sr-paper: #1b1b1b; --sr-desk: #2d2e2f;
  --sr-navy: #162e51; --sr-blue: #73b3e7; --sr-link: #73b3e7; --sr-red: #f4b4ae; --sr-red-bg: #3d1713;
  --sr-amber: #f3cd7c; --sr-amber-bg: #33270b; --sr-green: #9fd8b0; --sr-green-bg: #12301d; --sr-chip: #22303d;
  --sr-hover: #2d2e2f; }
.gradio-container { font-size: 16px; }

/* Masthead: the site name on white, as an agency site sets it, with the role on the right. */
.sr-header { background: var(--sr-paper) !important; padding: 14px 4px 12px !important; align-items: center !important; }
.sr-header .block, .sr-header .form { background: transparent !important; border: none !important; box-shadow: none !important; }
.sr-brand { display: flex; gap: 12px; align-items: center; }
.sr-mark { flex: none; width: 38px; height: 38px; border-radius: 4px; background: var(--sr-blue); color: #ffffff;
  display: flex; align-items: center; justify-content: center; }
.sr-brand h1 { font-size: 1.25rem; margin: 0; color: var(--sr-ink); font-weight: 700; letter-spacing: 0; }
.sr-brand p { margin: 2px 0 0; color: var(--sr-muted); font-size: 0.85rem; }
.sr-hint { display: flex; gap: 8px; align-items: center; color: var(--sr-ink); font-size: 0.95rem; padding: 10px 2px 0; }
.sr-hint .sr-icon { flex: none; color: var(--sr-blue); }

/* The menu: a blue bar of white labels; the open page is marked by a white bar under its label. */
.tabs > .tab-wrapper { background: var(--sr-blue); padding: 0 8px !important; margin: 0 !important; border: none !important; }
.tabs .tab-container { gap: 0 !important; height: auto !important; }
.tabs button[role="tab"] { color: #ffffff !important; background: transparent !important; text-transform: uppercase;
  font-size: 0.82rem !important; font-weight: 700 !important; letter-spacing: 0.02em; padding: 14px 16px 12px !important;
  border: none !important; border-bottom: 4px solid transparent !important; border-radius: 0 !important; margin: 0 !important; }
.tabs button[role="tab"]:hover { background: var(--sr-navy) !important; }
.tabs button[role="tab"].selected { background: var(--sr-navy) !important; border-bottom-color: #ffffff !important; }
.tabs button[role="tab"].selected::after, .tabs button[role="tab"].selected::before { display: none !important; }
.tabs button[role="tab"]:focus-visible { outline: 3px solid #ffbe2e; outline-offset: -3px; }
.tabs button[role="tab"] .sr-icon { margin-right: 6px; vertical-align: -3px; color: #ffffff !important; }
.tabs > .tabitem { background: var(--sr-paper); border: none; padding: 18px 4px !important; }

/* Page title and introduction, set like a dashboard page. */
.sr-page .sr-crumbs { font-size: 0.9rem; color: var(--sr-muted); margin-bottom: 6px; }
.sr-page h2 { font-family: var(--sr-serif); font-size: 2rem; font-weight: 700; margin: 0 0 8px; color: var(--sr-ink); }
.sr-page p { font-size: 1rem; line-height: 1.6; color: var(--sr-ink); max-width: 80ch; margin: 0; }
.sr-page a, .sr-filters a { color: var(--sr-link); text-decoration: underline; padding: 0 !important; }

/* Headline figures: serif labels, coloured numbers, a heavy rule above as on the dashboard. */
.sr-outcomes { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 8px;
  border-top: 4px solid var(--sr-ink); padding-top: 12px; margin-top: 4px; }
.sr-outcome { text-align: center; padding: 4px 6px; }
.sr-outcome-label { font-family: var(--sr-serif); font-weight: 700; font-size: 1.15rem; line-height: 1.3; color: var(--sr-ink); }
.sr-outcome-value { font-weight: 700; font-size: 1.9rem; font-variant-numeric: tabular-nums; margin-top: 2px; }
.sr-tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); margin-top: 12px;
  border-top: 1px solid var(--sr-rule); border-bottom: 1px solid var(--sr-rule); }
.sr-tile { padding: 10px 14px 12px; border-left: 1px solid var(--sr-rule); }
.sr-tile:first-child { border-left: none; }
.sr-tile-head { display: flex; gap: 7px; align-items: center; color: var(--sr-ink); font-size: 0.95rem; font-weight: 700; }
.sr-tile-value { font-size: 1.6rem; font-weight: 700; color: var(--sr-ink); font-variant-numeric: tabular-nums; line-height: 1.2; }
.sr-tile-note { font-size: 0.85rem; color: var(--sr-muted); }
.sr-tile-alert .sr-tile-head, .sr-tile-alert .sr-tile-value, .sr-tile-clock .sr-tile-head, .sr-tile-clock .sr-tile-value { color: var(--sr-red); }

/* Section titles: serif, with the heavy rule that opens each dashboard section. */
.block.sr-section { border-top: 4px solid var(--sr-ink) !important; padding-top: 8px !important; margin-top: 10px; }
.prose.sr-section, .sr-section .prose { border-top: none !important; padding-top: 0 !important; margin-top: 0 !important; }
.sr-section h3 { display: flex; gap: 9px; align-items: center; font-family: var(--sr-serif); font-size: 1.35rem;
  font-weight: 700; margin: 0; color: var(--sr-ink); }
.sr-section h3 .sr-icon { color: var(--sr-blue); }

/* Tables as a records list: grey header, thin rules, no fills. */
.table-wrap table thead th, table thead th { background: #f0f0f0 !important; color: var(--sr-ink) !important; font-weight: 700 !important; }
.dark .table-wrap table thead th, .dark table thead th { background: #2d2e2f !important; }
.table-wrap table td, .table-wrap table th { border-color: var(--sr-rule) !important; font-variant-numeric: tabular-nums; }

/* Buttons: blue for the action, grey for resets, a blue outline for the rest. */
button.primary { background: var(--sr-blue) !important; color: #ffffff !important; border: none !important; }
button.primary:hover { background: var(--sr-navy) !important; }
button.secondary { background: #ffffff !important; border: 2px solid var(--sr-blue) !important; color: var(--sr-blue) !important; }
.dark button.secondary { background: transparent !important; }
button.sr-reset { background: #71767a !important; border: none !important; color: #ffffff !important; }
button.sr-reset:hover { background: #565c65 !important; }
button.lg, button.md { min-height: 42px; max-height: 48px; align-self: end; font-weight: 700 !important; border-radius: 4px !important; }

.sr-chip { display: inline-block; padding: 2px 9px; border-radius: 3px; font-size: 0.88rem; font-weight: 700; }
.sr-chip-inspection { background: var(--sr-chip); color: var(--sr-blue); }
.sr-chip-must { background: var(--sr-red-bg); color: var(--sr-red); }
.sr-chip-letter { background: var(--sr-amber-bg); color: var(--sr-amber); }
.sr-trace { list-style: none; margin: 0; padding: 0; counter-reset: step; }
.sr-step { position: relative; padding: 6px 0 10px 34px; border-left: 2px solid var(--sr-rule); margin-left: 11px; }
.sr-step::before { counter-increment: step; content: counter(step); position: absolute; left: -12px; top: 5px;
  width: 22px; height: 22px; border-radius: 11px; background: var(--sr-chip); color: var(--sr-blue);
  font-size: 0.75rem; font-weight: 700; display: flex; align-items: center; justify-content: center; }
.sr-step-head { color: var(--sr-ink); line-height: 1.4; }
.sr-step-head strong { color: var(--sr-blue); margin-right: 4px; }
.sr-agent-decision-critic .sr-step-head strong { color: var(--sr-red); }
.sr-agent-area-director .sr-step-head strong { color: var(--sr-green); }
.sr-meta { margin-top: 4px; display: flex; flex-wrap: wrap; gap: 5px; align-items: center; }
.sr-reason { font-size: 0.86rem; color: var(--sr-muted); margin-top: 3px; }
.sr-num { font-size: 0.86rem; color: var(--sr-muted); font-variant-numeric: tabular-nums; }
.sr-badges { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.sr-badge { display: inline-block; padding: 2px 10px; border-radius: 3px; font-size: 0.88rem; line-height: 1.55;
  background: var(--sr-chip); color: var(--sr-ink); }
.sr-ok { background: var(--sr-green-bg); color: var(--sr-green); }
.sr-warn { background: var(--sr-amber-bg); color: var(--sr-amber); }
.sr-bad { background: var(--sr-red-bg); color: var(--sr-red); font-weight: 700; }
.sr-model { color: var(--sr-blue); font-weight: 700; }
.sr-tool { background: transparent; color: var(--sr-muted); padding-left: 0; }
.sr-empty { color: var(--sr-muted); padding: 12px 0; }
.sr-filters { font-size: 0.95rem; color: var(--sr-ink); padding: 6px 2px 2px; }
.sr-filters b { font-family: var(--sr-serif); }
.sr-audit { color: var(--sr-ink); margin: 0 0 10px; }
.sr-actions { align-items: end !important; }
.sr-actions button { white-space: nowrap; }
/* The case inspector stays beside the list and scrolls on its own. */
.sr-inspector { background: var(--sr-paper); border: 1px solid var(--sr-rule); border-top: 4px solid var(--sr-ink);
  border-radius: 0; padding: 4px 14px 10px !important; max-height: 860px; overflow-y: auto; overflow-x: hidden;
  flex-wrap: nowrap !important; }
.sr-inspector > .block { flex: none !important; }
.sr-inspector .block.sr-section { border-top: none !important; margin-top: 0; }
.sr-empty-state { color: var(--sr-muted); border: 1px dashed var(--sr-rule); border-radius: 4px; padding: 18px 16px; }
.sr-small p { font-size: 0.9rem; color: var(--sr-muted); margin: 2px 0 6px; }
/* The narrative reads as running text: no line break after a highlight, none inside a word. */
.sr-narrative .textfield { display: block !important; word-break: normal !important; line-height: 1.8; }
.sr-narrative .token-container { display: inline !important; word-break: normal !important; }
.sr-footer { background: #f0f0f0; color: var(--sr-ink); font-size: 0.88rem; padding: 18px 16px; margin-top: 16px;
  display: flex; flex-wrap: wrap; gap: 6px 28px; justify-content: space-between; }
.dark .sr-footer { background: #2d2e2f; }
.sr-footer b { font-family: var(--sr-serif); }
/* One type scale everywhere: Gradio's own labels and the chat use the body face and size, and
   headings written in Markdown (a brief in the chat, a rule in the Evidence view) use the serif. */
.gradio-container p { font-family: var(--font); }
.gradio-container button.lg { font-size: 1.05rem !important; }
/* Every list comes from the crew; an empty table must not offer to add a blank row. */
.gradio-container .add-row-button { display: none !important; }
.sr-chat .message, .sr-chat .message p, .sr-chat .message li { font-size: 1rem !important; line-height: 1.6 !important; }
.sr-md h1, .sr-md h2, .sr-md h3,
.sr-chat .message h1, .sr-chat .message h2, .sr-chat .message h3 { font-family: var(--sr-serif) !important;
  font-weight: 700 !important; color: var(--sr-ink); line-height: 1.3 !important; margin: 6px 0 8px !important; }
.sr-md h1, .sr-chat .message h1 { font-size: 1.35rem !important; }
.sr-md h2, .sr-chat .message h2 { font-size: 1.2rem !important; }
.sr-md h3, .sr-chat .message h3 { font-size: 1.1rem !important; }
.sr-chat .message blockquote { border-left: 4px solid var(--sr-rule); color: var(--sr-muted); font-size: 0.95rem;
  margin: 6px 0; padding: 2px 0 2px 12px; }
.sr-chat .placeholder { color: var(--sr-muted); font-size: 1rem; }
.sr-offline-note { font-size: 0.9rem; color: var(--sr-muted); border-left: 4px solid var(--sr-rule);
  padding: 2px 0 2px 10px; margin: 0 0 10px; }
@media (max-width: 720px) {
  /* On a phone the brand and the role picker stack instead of overlapping. */
  .sr-header { flex-direction: column !important; align-items: stretch !important; gap: 10px !important; }
  .sr-header > * { width: 100% !important; min-width: 0 !important; flex: none !important; }
  .tabs button[role="tab"] { padding: 12px 10px 10px !important; }
  .sr-page h2 { font-size: 1.5rem; }
}
"""

ASK_EMPTY = (
    "**Ask the crew in your own words.** Paste an injury narrative for a brief with the standard, or ask "
    "about a trend, employers that reported more than once, or this week's inspections. The steps each "
    "agent took appear in the routing and audit log."
)
EXAMPLES = [
    "An employee's hand was pulled into the rollers of a laminator while clearing a jam, amputating a fingertip.",
    (
        "Find caught in machinery injuries in Texas since 2022, check which employers reported more than once, "
        "then plan this week's inspections with 40 inspector days."
    ),
    "Check which employers reported more than once, then plan this week's inspections.",
    "Show the trend of falls in construction in Ohio since 2019.",
]
# Column types of the week's list: the decision is drawn as a coloured label.
WEEK_TYPES = ["str", "str", "html", "str", "str", "number", "str", "str", "number", "str", "str"]
WEEK_WIDTHS = [
    "120px",
    "210px",
    "120px",
    "170px",
    "118px",
    "70px",
    "112px",
    "170px",
    "90px",
    "120px",
    "300px",
]


def theme() -> gr.themes.Base:
    return gr.themes.Base(
        primary_hue=FEDERAL, neutral_hue="gray", radius_size="sm", text_size=gr.themes.sizes.text_lg,
        font=[gr.themes.GoogleFont("Source Sans 3"), "system-ui", "sans-serif"],
        # Tables read better in the same face, with tabular figures, than in a code font.
        font_mono=[gr.themes.GoogleFont("Source Sans 3"), "system-ui", "sans-serif"],
    ).set(
        body_background_fill="#ffffff", body_background_fill_dark="#1b1b1b", body_text_color="#1b1b1b",
        block_border_width="1px", block_border_color="#dfe1e2", block_shadow="none", block_label_text_weight="700",
        block_label_text_color="#1b1b1b", block_title_text_weight="700",
        button_primary_background_fill="#005ea2", button_primary_background_fill_hover="#1a4480",
        button_primary_text_color="#ffffff", button_secondary_background_fill="#ffffff",
        button_secondary_border_color="#005ea2", button_secondary_text_color="#005ea2",
        button_secondary_background_fill_hover="#f0f0f0", button_large_text_weight="700",
    )  # fmt: skip


def page(title: str, intro: str) -> gr.HTML:
    """A page title and its introduction, the way a dashboard page opens."""
    return gr.HTML(f'<div class="sr-crumbs">SafeReport Crew &rsaquo; {html.escape(title)}</div><h2>{html.escape(title)}</h2>'
                   f"<p>{intro}</p>", elem_classes="sr-page")  # fmt: skip


ECFR_1904_39 = (
    "https://www.ecfr.gov/current/title-29/subtitle-B/chapter-XVII/part-1904/subpart-E/section-1904.39"
)
INTROS = {
    "week": (
        f'Per <a href="{ECFR_1904_39}" target="_blank" rel="noopener">29 CFR 1904.39</a>, employers report every '
        "work related amputation, in-patient hospitalization and loss of an eye. This page replays one office "
        "week of those reports: the Category 1 reports that must be inspected, a proposed list of inspections and "
        "Rapid Response Investigation letters, and the reasons, for the Area Director to change and approve."
    ),
    "ask": "Paste a report narrative, or ask about trends, repeat employers or this week's inspections, in your own words.",
    "evidence": "The narrative beside the standard it points to, with the words that support the citation and the checks it passed.",
    "trends": (
        "Reports, hospitalizations, amputations and losses of an eye by year, state and industry, and the "
        "events that cause them. Reports cover federal OSHA jurisdiction only; State Plan states report to "
        "their own programs and are marked on the map."
    ),
    "controls": "Which model answers each step, what it may see, what it costs and how well it does.",
    "downloads": "The week's list as CSV; the brief, the letters and the talks as Word files, as you make them.",
}


def section(title: str, icon: str) -> gr.HTML:
    return gr.HTML(f"<h3>{svg(icon, 17)}{html.escape(title)}</h3>", elem_classes="sr-section")


def hint(role: str) -> str:
    return f'<div class="sr-hint">{svg("people", 16)}<span><b>{role}.</b> {html.escape(ROLE_HINTS[role])}</span></div>'


def chips(table: pd.DataFrame) -> pd.DataFrame:
    """The decision as a coloured label: red for Category 1, blue for inspection, amber for a letter."""
    if table.empty:
        return table
    table = table.copy()

    def label(decision: str, category_one: str) -> str:
        kind = "must" if category_one else ("inspection" if decision == "Inspection" else "letter")
        return f'<span class="sr-chip sr-chip-{kind}">{html.escape(decision)}</span>'

    table["Decision"] = [label(d, c) for d, c in zip(table["Decision"], table["Category 1"], strict=True)]
    return table


def role_view(role: str):
    """What a role sees: its home tab, the week page, approval and the admin controls."""
    week = role != "Plant safety manager"
    return (
        gr.Tabs(selected=HOME[role]),
        gr.Tab(visible=True if week else "hidden"),
        gr.Button(visible=role == APPROVER),
        gr.Group(visible=role == "Admin"),
        gr.Button(visible=role in ("Triage officer", APPROVER)),
    )


def signed_in_role(request: gr.Request):
    """With sign in on, the account fixes the role; without it, the picker stays free."""
    user = getattr(request, "username", None) if request is not None else None
    if user in ACCOUNTS:
        return gr.Dropdown(value=ACCOUNTS[user], interactive=False)
    return gr.Dropdown(interactive=True)


EMPTY_CASE = (
    '<div class="sr-empty-state">Pick a report in the list to read its narrative, the cited standard, '
    "the employer's history and the letter here.</div>"
)


def build_app(crew: Crew) -> gr.Blocks:
    week_start, week_end = crew.services.week
    count, last = (
        crew.services.store.con.cursor().execute("SELECT count(*), max(event_date) FROM reports").fetchone()
    )
    with gr.Blocks(title="SafeReport Crew") as app:
        session = gr.State(Session())
        with gr.Row(elem_classes="sr-header", equal_height=False):
            gr.HTML(
                f'<div class="sr-brand"><div class="sr-mark">{svg("critic", 22)}</div><div><h1>SafeReport Crew</h1>'
                f"<p>Severe injury report triage, {count:,} reports from January 2015 to {last:%B %Y}. "
                f"Replaying {week_start:%d %B} to {week_end:%d %B %Y}.</p></div></div>", scale=4,
            )  # fmt: skip
            role = gr.Dropdown(list(ROLES), value=ROLES[0], label="Signed in as", scale=1, min_width=210)
        role_hint = gr.HTML(hint(ROLES[0]))

        with gr.Tabs(selected=HOME[ROLES[0]]) as tabs:
            with gr.Tab("This week's reports", id="week") as week_tab:
                page("This Week's Reports", INTROS["week"])
                with gr.Row(equal_height=False, elem_classes="sr-actions"):
                    state = gr.Dropdown(
                        offline.STATES, value="Texas", label="State (one office's territory)", scale=3
                    )
                    days = gr.Number(40, label="Inspector days this week", minimum=0, precision=1, scale=2)
                    load = gr.Button("Load week", variant="primary", scale=1, min_width=140)
                    reset = gr.Button("Reset", scale=0, min_width=100, elem_classes="sr-reset")
                tiles = gr.HTML()
                with gr.Row(equal_height=False):
                    with gr.Column(scale=3):
                        show_rows = gr.Radio(list(views.FILTERS), value="All", label="Show", container=False)
                        active = gr.HTML(views.filters_line(crew, Session()))
                        table = gr.Dataframe(
                            headers=views.WEEK_COLUMNS, datatype=WEEK_TYPES, interactive=True, wrap=True, max_height=620,
                            static_columns=[i for i, c in enumerate(views.WEEK_COLUMNS) if c not in views.EDITABLE],
                            label="Proposed list: pick a report to inspect it; type a note in the Note column",
                            column_widths=WEEK_WIDTHS,
                        )  # fmt: skip
                        with gr.Row(equal_height=False, elem_classes="sr-actions"):
                            export = gr.Button(
                                "Download Selected Data", variant="primary", scale=0, min_width=240
                            )
                            export_file = gr.File(show_label=False, interactive=False, visible=False, scale=1)
                    with gr.Column(scale=2, elem_classes="sr-inspector"):
                        section("Case inspector", "evidence")
                        q_letter = gr.HTML(EMPTY_CASE)
                        q_narrative = gr.HighlightedText(
                            label="Narrative", show_legend=True, visible=False, elem_classes="sr-narrative",
                            color_map={"activity": "#2f629f", "hazard": "#b3261e", "material": "#8a5a00"},
                        )  # fmt: skip
                        # Read in the order a decision needs: what happened, what checks say, the history,
                        # the letter that would go out, then the rule's own words.
                        q_checks = gr.HTML()
                        q_context = gr.Markdown(elem_classes="sr-md")
                        q_draft = gr.Markdown(elem_classes="sr-md")
                        q_rule = gr.Markdown(elem_classes="sr-md")
                section("Decide", "week")
                with gr.Row(equal_height=True):
                    to_inspect = gr.Dropdown([], multiselect=True, label="Move to inspection")
                    to_letter = gr.Dropdown([], multiselect=True, label="Move to RRI letter")
                    imminent = gr.Dropdown(
                        [], multiselect=True, label="Imminent danger (makes the report Category 1)"
                    )
                with gr.Row(equal_height=False, elem_classes="sr-actions"):
                    capacity = gr.Number(40, label="Inspector days", minimum=0, precision=1, scale=1)
                    rule = gr.Textbox(label="Always inspect these establishments (case, commas and Inc are ignored)",
                                      placeholder="Acme Laminates, Walmart", scale=3)  # fmt: skip
                    changes = gr.Button("Ask for changes", scale=1, min_width=170)
                    approve = gr.Button(
                        "Approve the list", variant="primary", visible=False, scale=1, min_width=170
                    )
                status = gr.Markdown()
                answer = gr.Markdown(elem_classes="sr-md")
                with gr.Row(equal_height=False):
                    with gr.Column(scale=3):
                        section("Reports by geography", "inspection")
                        week_map = gr.Plot(show_label=False)
                        gr.Markdown("Colour shows the decision, size the priority. Travel time is not planned.",
                                    elem_classes="sr-small")  # fmt: skip
                    with gr.Column(scale=2):
                        section("Top 5 events and exposures", "alert")
                        week_events = gr.Plot(show_label=False)
                        section("What each inspector day buys", "trends")
                        sensitivity = gr.Image(show_label=False, interactive=False)
                section("Category 1 triggers", "alert")
                triggers = gr.Dataframe(interactive=False, wrap=True, max_height=300, show_label=False)
                with gr.Accordion("Possible employer matches", open=True) as match_panel:
                    gr.Markdown("Write yes or no in the last column; one answer settles every report with that pair.",
                                elem_classes="sr-small")  # fmt: skip
                    matches = gr.Dataframe(
                        headers=views.MATCH_COLUMNS, interactive=True, wrap=True,
                        static_columns=list(range(len(views.MATCH_COLUMNS) - 1)), show_label=False,
                    )  # fmt: skip
                    save_matches = gr.Button("Save match decisions", scale=0)
                    match_note = gr.Markdown()
                with gr.Accordion("Routing & audit log", open=False):
                    week_trace = gr.HTML()

            with gr.Tab("Ask", id="ask"):
                page("Ask", INTROS["ask"])
                with gr.Row():
                    with gr.Column(scale=3):
                        chat = gr.Chatbot(
                            height=460, show_label=False, elem_classes="sr-chat", placeholder=ASK_EMPTY
                        )
                        box = gr.Textbox(placeholder="Paste a narrative, or ask about trends, repeat employers or this "
                                                     "week's inspections", show_label=False, lines=2, submit_btn="Send")  # fmt: skip
                        gr.Examples(EXAMPLES, inputs=box, label="Try one of these")
                        # Shown only when the answer has one, so the page never holds empty boxes.
                        brief_file = gr.File(
                            label="Inspection brief (Word)", interactive=False, visible=False
                        )
                    with gr.Column(scale=2):
                        chart = gr.Image(label="Chart", interactive=False, visible=False)
                        with gr.Accordion("Routing & audit log", open=False):
                            trace = gr.HTML(views.trace_html([]))

            with gr.Tab("Evidence view", id="evidence"):
                page("Evidence View", INTROS["evidence"])
                source = gr.Dropdown([], label="Report (the pasted narrative and the week's reports)")
                with gr.Row():
                    with gr.Column():
                        narrative = gr.HighlightedText(
                            label="Narrative, with the words read from it", show_legend=True, elem_classes="sr-narrative",
                            color_map={"activity": "#2f629f", "hazard": "#b3261e", "material": "#8a5a00"},
                        )  # fmt: skip
                        questions = gr.Markdown(elem_classes="sr-md")
                        evidence_context = gr.Markdown(elem_classes="sr-md")
                    with gr.Column():
                        checks = gr.HTML()
                        rule_text = gr.Markdown(
                            "Paste a narrative in **Ask** or load a week to see its evidence.",
                            elem_classes="sr-md",
                        )

            with gr.Tab("Trends and prevention", id="trends"):
                page("Trends and Prevention", INTROS["trends"])
                with gr.Row(equal_height=False, elem_classes="sr-actions"):
                    trend_state = gr.Dropdown(["All states", *offline.STATES], value="Texas", label="State")
                    industry = gr.Dropdown(
                        list(views.INDUSTRY_CHOICES), value="Plastics", label="Industry (NAICS)"
                    )
                    hazard = gr.Dropdown(
                        list(views.HAZARD_CHOICES), value="All events", label="Events and exposures"
                    )
                    since = gr.Slider(2015, 2025, value=2019, step=1, label="From")
                    show = gr.Button("Apply", variant="primary", scale=0, min_width=110)
                    trend_reset = gr.Button("Reset", scale=0, min_width=100, elem_classes="sr-reset")
                trend_active = gr.HTML()
                trend_tiles = gr.HTML()
                trend_plot = gr.Plot(show_label=False)
                trend_note = gr.Markdown(elem_classes="sr-small")
                with gr.Row(equal_height=False):
                    with gr.Column(scale=3):
                        section("Reports by geography", "inspection")
                        geo_plot = gr.Plot(show_label=False)
                        gr.Markdown("Grey: State Plan states, whose reports go to their own programs and are not in "
                                    "this file. The outlined state is the one in the filter.", elem_classes="sr-small")  # fmt: skip
                    with gr.Column(scale=2):
                        section("Top 5 events and exposures", "alert")
                        events_plot = gr.Plot(show_label=False)
                        events_note = gr.Markdown(elem_classes="sr-small")
                with gr.Row(equal_height=False, elem_classes="sr-actions"):
                    trend_export = gr.Button(
                        "Download Selected Data", variant="primary", scale=0, min_width=240
                    )
                    trend_file = gr.File(show_label=False, interactive=False, visible=False, scale=1)
                with gr.Accordion("Numbers by year", open=False):
                    trend_table = gr.Dataframe(interactive=False)
                section("Safety talk for the next shift", "people")
                with gr.Row(equal_height=False, elem_classes="sr-actions"):
                    topic = gr.Dropdown(list(views.TALK_TOPICS), value="lockout", label="Topic", scale=2)
                    talk_language = gr.Dropdown(views.TALK_LANGUAGE_CHOICES, value="Spanish (es)", scale=2,
                                                label="Additional worker language (optional, max 1)")  # fmt: skip
                    write = gr.Button("Write the talk", scale=1, min_width=150)
                talk = gr.Markdown(elem_classes="sr-md")
                talk_files = gr.File(label="Word files", file_count="multiple", interactive=False)
                section("Prevention plan", "critic")
                gr.Markdown("What to fund first within a yearly budget, for a plant in the industry and state "
                            "picked above. The costs and effects below are planning assumptions: change them to "
                            "your own quotes.", elem_classes="sr-small")  # fmt: skip
                with gr.Row(equal_height=False, elem_classes="sr-actions"):
                    plan_budget = gr.Number(40000, label="Yearly budget ($)", minimum=0, scale=2)
                    plan_injuries = gr.Number(
                        1.0, label="Severe injuries a year at your plant", minimum=0, scale=2
                    )
                    make_plan = gr.Button("Make the plan", scale=1, min_width=150)
                plan_controls = gr.Dataframe(views.controls_table(), interactive=True, label="Controls")
                plan_answer = gr.Markdown(elem_classes="sr-md")
                plan_table = gr.Dataframe(interactive=False, label="The plan by control")

            with gr.Tab("AI controls and evaluation", id="controls"):
                page("AI Controls and Evaluation", INTROS["controls"])
                with gr.Group(visible=False) as controls:
                    section("AI controls", "controls")
                    with gr.Row():
                        mode = gr.Radio(
                            list(views.MODES), value=views.mode_label(crew.services.mode), label="Routing"
                        )
                        redact = gr.Checkbox(True, label="Hide names and addresses from cloud models")
                        switched_off = gr.CheckboxGroup([s.label for s in crew.services.settings.models],
                                                        label="Simulate an outage")  # fmt: skip
                    apply = gr.Button("Apply", scale=0, min_width=120)
                    controls_note = gr.Markdown()
                section("Models", "branch")
                models = gr.Dataframe(interactive=False, wrap=True)
                section("Data and indexes", "data")
                data = gr.Dataframe(interactive=False, wrap=True)
                section("Evaluation", "critic")
                pareto = gr.Image(
                    label="Cost against accuracy (dashed: the frontier)", interactive=False, height=380
                )
                retrieval = gr.Dataframe(interactive=False, wrap=True)
                coding = gr.Dataframe(interactive=False, wrap=True)
                eval_note = gr.Markdown(elem_classes="sr-small")
                with gr.Accordion("Model calls", open=False):
                    refresh_usage = gr.Button("Refresh", scale=0)
                    usage = gr.Dataframe(interactive=False, wrap=True, max_height=420)

            with gr.Tab("Downloads", id="downloads"):
                page("Downloads", INTROS["downloads"])
                gr.Markdown("The week's list as CSV; the brief, the letters and the talks as Word files.",
                            elem_classes="sr-small")  # fmt: skip
                downloads = gr.File(file_count="multiple", interactive=False, label="Files")

        gr.HTML('<div class="sr-footer"><span><b>SafeReport Crew</b>, built by Seven Team-5374 for IE5374 at '
                "Northeastern University. Every inspection, letter and plan is approved by a person.</span>"
                "<span>Not an official U.S. government website. Data: OSHA Severe Injury Reports and eCFR Title 29, "
                "both public.</span></div>")  # fmt: skip

        # ---- Events ----

        week_outputs = [tiles, table, triggers, matches, sensitivity, status]
        role_outputs = [tabs, week_tab, approve, controls, save_matches]
        role.change(role_view, role, role_outputs).then(hint, role, role_hint)
        app.load(signed_in_role, None, role).then(role_view, role, role_outputs).then(hint, role, role_hint)
        app.load(lambda: (views.models_table(crew), views.data_table(crew), *views.evaluation(crew)), None,
                 [models, data, pareto, coding, retrieval, eval_note])  # fmt: skip

        def sources(sess):
            choices = views.evidence_choices(crew, sess)
            return gr.Dropdown(choices=choices, value=choices[0] if choices else None)

        def after_week(show_label, sess):
            """Everything a change to the week touches: the list, its filters line, the map, the events,
            the pick lists, the match count, the audit log, the Evidence choices and the files."""
            letters, inspections = views.move_choices(crew, sess)
            dangers, flagged = views.imminent_choices(crew, sess)
            loaded = views._triage(crew, sess) is not None
            unresolved = views.unresolved_matches(crew, sess)
            return (chips(views.week_rows(crew, sess, show_label)), views.filters_line(crew, sess, show_label),
                    views.week_map(crew, sess) or views.placeholder_figure(
                        "No location to show for this week." if loaded else "Load a week to see where its reports happened."),
                    views.week_events(crew, sess) or views.placeholder_figure("No event titles for this week."),
                    gr.Dropdown(choices=letters, value=[]), gr.Dropdown(choices=inspections, value=[]),
                    gr.Dropdown(choices=dangers, value=flagged),
                    gr.Accordion(label=f"Possible employer matches ({unresolved} to resolve)" if unresolved
                                 else "Possible employer matches (none to resolve)"),
                    views.week_trace(crew, sess), sources(sess), views.files(crew, sess))  # fmt: skip

        refreshed = [table, active, week_map, week_events, to_inspect, to_letter, imminent, match_panel, week_trace, source,
                     downloads]  # fmt: skip

        def run_week(state_name, inspector_days, sess):
            return (*views.load_week(crew, sess, state_name, inspector_days), inspector_days, sess)

        load.click(run_week, [state, days, session], [*week_outputs, capacity, session]).then(
            after_week, [show_rows, session], refreshed)  # fmt: skip
        # Reset puts every filter back and plans the default week again, so the controls at the top and
        # the list, figures and map below always describe the same week.
        reset.click(lambda: ("Texas", 40, "All", EMPTY_CASE, gr.HighlightedText(value=[], visible=False), "", "", "", ""),
                    None, [state, days, show_rows, q_letter, q_narrative, q_checks, q_rule, q_context, q_draft]).then(
            run_week, [state, days, session], [*week_outputs, capacity, session]).then(
            after_week, [show_rows, session], refreshed)  # fmt: skip
        changes.click(
            lambda t, c, r, ro, up, down, danger, sess: (*views.ask_for_changes(crew, sess, t, c, r, ro, up, down, danger), sess),
            [table, capacity, rule, role, to_inspect, to_letter, imminent, session], [*week_outputs, session],
        ).then(after_week, [show_rows, session], refreshed)  # fmt: skip
        approve.click(lambda ro, sess: (*views.approve(crew, sess, ro), sess), [role, session],
                      [*week_outputs, answer, session]).then(after_week, [show_rows, session], refreshed)  # fmt: skip
        show_rows.change(lambda f, sess: (chips(views.week_rows(crew, sess, f)), views.filters_line(crew, sess, f)),
                         [show_rows, session], [table, active])  # fmt: skip
        export.click(lambda f, sess: gr.File(value=views.download_week(crew, sess, f), visible=True),
                     [show_rows, session], export_file)  # fmt: skip
        save_matches.click(lambda t, ro, sess: views.save_matches(crew, sess, t, ro), [matches, role, session],
                           [matches, match_note])  # fmt: skip

        def picked(sess, evt: gr.SelectData):
            row = evt.row_value or []
            pieces, rule_md, checks_html, context_md, letter_md = views.quick_view(
                crew, sess, str(row[0]) if row else ""
            )
            if not pieces:
                return EMPTY_CASE, gr.HighlightedText(value=[], visible=False), "", "", "", ""
            return (
                "",
                gr.HighlightedText(value=pieces, visible=True),
                checks_html,
                rule_md,
                context_md,
                letter_md,
            )

        table.select(picked, session, [q_letter, q_narrative, q_checks, q_rule, q_context, q_draft])

        def ask_turn(message, history, sess):
            chat_value, box_value, trace_value, picture, brief, sess = views.ask(crew, message, history, sess)
            return (chat_value, box_value, trace_value, gr.Image(value=picture, visible=picture is not None),
                    gr.File(value=brief, visible=brief is not None), sess)  # fmt: skip

        box.submit(ask_turn, [box, chat, session], [chat, box, trace, chart, brief_file, session]).then(
            lambda sess: (sources(sess), views.files(crew, sess)), session, [source, downloads])  # fmt: skip
        source.change(lambda c, sess: views.evidence(crew, sess, c), [source, session],
                      [narrative, rule_text, checks, questions, evidence_context])  # fmt: skip

        def trends(state_name, industry_name, hazard_name, start):
            figure, numbers, note = views.trend_view(crew, state_name, industry_name, hazard_name, start)
            events, caption = views.top_events(crew, state_name, industry_name)
            empty = views.placeholder_figure("No report matches these filters.")
            return (views.trend_filters_line(crew, state_name, industry_name, hazard_name, start),
                    views.trend_tiles(crew, state_name, industry_name, hazard_name, start),
                    figure or empty, numbers, note, events or empty, caption,
                    views.state_map(crew, industry_name, hazard_name, start, state_name))  # fmt: skip

        trend_inputs = [trend_state, industry, hazard, since]
        trend_outputs = [
            trend_active,
            trend_tiles,
            trend_plot,
            trend_table,
            trend_note,
            events_plot,
            events_note,
            geo_plot,
        ]
        # The plant safety manager opens on a filled page, not on empty charts.
        app.load(trends, trend_inputs, trend_outputs)
        show.click(trends, trend_inputs, trend_outputs)
        trend_reset.click(lambda: ("Texas", "Plastics", "All events", 2019), None, trend_inputs).then(
            trends, trend_inputs, trend_outputs)  # fmt: skip
        trend_export.click(lambda *a: gr.File(value=views.download_trend(crew, a[-1], *a[:-1]), visible=True),
                           [*trend_inputs, session], trend_file)  # fmt: skip
        write.click(lambda t, es, st, ind, sess: views.safety_talk(crew, sess, t, es, st, ind),
                    [topic, talk_language, trend_state, industry, session],
                    [talk, talk_files]).then(lambda sess: views.files(crew, sess), session, downloads)  # fmt: skip
        make_plan.click(lambda st, ind, yr, b, n, tab: views.prevention_plan(crew, st, ind, yr, b, n, tab),
                        [trend_state, industry, since, plan_budget, plan_injuries, plan_controls],
                        [plan_answer, plan_table])  # fmt: skip
        apply.click(lambda m, r, off: views.apply_controls(crew, m, r, off), [mode, redact, switched_off],
                    [controls_note, models])  # fmt: skip
        refresh_usage.click(lambda: views.usage_table(crew), None, usage)
    return app


def _check_password(username: str, password: str) -> bool:
    expected = os.environ.get("SAFEREPORT_PASSWORD", "")
    return username in ACCOUNTS and bool(expected) and hmac.compare_digest(password, expected)


def launch(port: int = 7860, live: bool = False, mode: str = "lowest_cost") -> None:
    from safereport.graph import load_services

    crew = Crew.start(load_services(mode=mode, live=live))
    sign_in = bool(os.environ.get("SAFEREPORT_PASSWORD"))
    build_app(crew).launch(
        server_port=port, theme=theme(), css=CSS, head=tab_script(), allowed_paths=[str(crew.folder / "downloads")],
        auth=_check_password if sign_in else None,
        auth_message="Accounts: triage, director, manager, admin." if sign_in else None,
    )  # fmt: skip
