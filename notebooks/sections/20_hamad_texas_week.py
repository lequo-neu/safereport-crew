# Owner: Hamad (issue #38). The Texas week, run through the seven agents offline.

# %% [markdown]
# ## 9. Start the crew, offline
#
# `load_services` loads everything the agents use: the reports, the indexes, the eCFR text, the
# stage 1 coder and the model **router**. Without `live=True`, every model behind the router is the
# project's `OfflineBackend`: fixed rules that return what a model would, so the whole flow runs
# with no key and no cost. The cell stops if any backend is not offline.
#
# **Read the traces below with this in mind.** The router still chooses a model *slot* for each
# step (the trace says `claude` or `gpt_nano`, the model it would call live), but the answer
# comes from the offline rules. Their outputs show how the agents work together; they are not model
# results, and the project never reports them as such. Part 17 covers the real router results.

# %%
from langgraph.types import Command

from safereport.graph import build_graph, load_services, run_config, sqlite_checkpointer


services = load_services(mode="lowest_cost", dense=USE_EMBEDDINGS, live=False)
backends = {name: type(backend).__name__ for name, backend in services.router.backends.items()}
assert set(backends.values()) == {"OfflineBackend"}, f"a backend is not offline: {backends}"
print("Model slots and who answers them:", backends)

week_start, week_end = services.week
print(
    f"Replayed week: {week_start:%A %d %B %Y} to {week_end:%A %d %B %Y}; {services.capacity:g} inspector days by default"
)

graph = build_graph(services, sqlite_checkpointer())  # the checkpointer lets a paused run resume
config = run_config()

# %% [markdown]
# ## 10. The request, and the Planner's question
#
# The request is the one in the README quick start, in plain words. It names no state, so the
# **Planner** does not guess one: the graph **pauses** (a LangGraph *interrupt*) and asks. The run is
# saved by the checkpointer, so it can resume later with the answer, even after a restart.

# %%
REQUEST = "Plan this week's inspections with 40 inspector days."
handoffs: list[dict] = []  # every step of the run: which node ran and what it passed on


def stream(value) -> object:
    """Run the graph until it pauses or ends, recording each node's update."""
    paused = None
    for update in graph.stream(value, config, stream_mode="updates"):
        for node, change in update.items():
            if node == "__interrupt__":
                paused = change[0].value
                continue
            change = change or {}
            trace = change.get("trace", [])
            handoffs.append(
                {
                    "step": len(handoffs) + 1,
                    "node": node,
                    "agents": ", ".join(dict.fromkeys(t["agent"] for t in trace)),
                    "passes on": ", ".join(k for k in change if k != "trace") or "(routing only)",
                    "first trace line": trace[0]["summary"] if trace else "",
                }
            )
    return paused


question = stream({"request": REQUEST})
state = graph.get_state(config).values
print("Planner's tasks:", state["tasks"])
print("Parameters so far:", state["params"])
print("Missing:", question["missing"], "->", question["questions"])

# %% [markdown]
# ## 11. Answer, and let the crew work until it needs a person
#
# We answer *Texas*. The run resumes and goes through stage 1, the parallel stage 2 branches, the
# Optimizer, the Writer and the Decision critic (with any send-backs), and pauses again at the
# **approval** step: the plan is only a proposal until a person approves it.
#
# The table is the run's own record of the **handoffs**: each node in the order it ran, the agents
# it speaks for, and the parts of the shared state it passed on to the next node.

# %%
approval_request = stream(Command(resume={"state": "Texas"}))
state = graph.get_state(config).values

pd.set_option("display.max_colwidth", 90)
handoff_table = pd.DataFrame(handoffs)
display(handoff_table)
print(
    f"{len(handoff_table)} steps; {(handoff_table['node'] == 'branch').sum()} stage 2 branches ran in parallel."
)
print("The run is paused at:", approval_request["question"])

# %% [markdown]
# ## 12. Stage 1: every report, coded without a model
#
# Stage 1 is the fast path. For each report of the week it codes the event with the trained
# classifier, checks the Category 1 rules, matches the employer against past reports, and searches
# the regulations (BM25, plus embeddings when `USE_EMBEDDINGS = True`). Its result per report decides
# whether that report needs a stage 2 branch: it does when the coder is unsure, when the two best
# regulation sections score too close together, when the injury is severe, or when the report is
# near the cut of the plan (a Category 1 report only when the coder is unsure).


# %%
def stage1_row(report_id: str, item: dict) -> dict:
    intake = item["intake"]
    return {
        "report": report_id,
        "employer": item["report"]["employer"][:40],
        "hazard (Intake)": intake["hazard_type"],
        "event code": intake["event_code"],
        "confidence": round(intake["confidence"], 2),
        "Category 1": "; ".join(f"{c['criterion']} ({c['evidence']})" for c in item["category_one"]) or "-",
        "standard (stage 1 search)": item["pick"].get("primary", ""),
        "stage 2 branch": report_id in state["stage2"],
    }


stage1 = pd.DataFrame([stage1_row(rid, item) for rid, item in state["stage1"].items()])
display(
    Markdown(
        f"**{len(stage1)} Texas reports** in the week. {stage1['Category 1'].ne('-').sum()} meet a Category 1 "
        f"criterion; {stage1['stage 2 branch'].sum()} were sent to a stage 2 branch, {(~stage1['stage 2 branch']).sum()} "
        "were clear enough for stage 1 alone."
    )
)
display(stage1)

# %% [markdown]
# **How this count compares with B4.** The B4 evaluation (`eval/results/batch_savings.json`) measured
# the same Texas week and counted the same thing: the reports the fan-out sends to a stage 2 branch.
# Its count can differ from the one above because it depends on the regulation search: B4 ran with
# the search named in the file's `method.retrieval`, and this notebook uses the one set by
# `USE_EMBEDDINGS`. A report goes to stage 2 when the scores of its two best sections are closer
# than the router's `min_retrieval_margin`, and the two searches score sections differently. The
# cell reads B4's numbers from the file and lists the reports on which the two runs differ, with
# the inputs the fan-out read for them in this run.

# %%
b4 = json.loads((REPO_DIR / "eval" / "results" / "batch_savings.json").read_text())
assert (b4["week"]["start"], b4["week"]["end"]) == (str(week_start), str(week_end)), "not the same week"
b4_branches = set(state["stage1"]) - set(b4["reports_skipped_by_two_stages"])
here = set(state["stage2"])
router_settings = services.settings.router
print(
    f"B4 ({b4['method']['retrieval']} search): {b4['two_stages']['reports_through_stage2']} of {b4['two_stages']['reports']} reports through stage 2"
)
print(f"This run ({'hybrid' if USE_EMBEDDINGS else 'bm25'} search): {len(here)} of {len(state['stage1'])}")
print(
    f"Thresholds: min_confidence {router_settings.min_confidence}, min_retrieval_margin {router_settings.min_retrieval_margin}"
)
differ = sorted(here ^ b4_branches)
if differ:
    display(
        pd.DataFrame(
            [
                {
                    "report": rid,
                    "stage 2 here": rid in here,
                    "stage 2 in B4": rid in b4_branches,
                    "coder confidence": round(state["stage1"][rid]["intake"]["confidence"], 3),
                    "retrieval margin here": round(state["stage1"][rid]["margin"], 4),
                }
                for rid in differ
            ]
        )
    )

# %% [markdown]
# ## 13. Stage 2: one report through Intake, Standards and Analyst
#
# One stage 2 report, chosen as the one with the highest stage 1 priority, shown in full. Each
# branch hands the Optimizer three things:
#
# * **Intake**: what happened, the event code with a confidence, and the facts the story leaves
#   out (they become questions in the RRI letter);
# * **Standards**: the cited section and paragraph, with the official text, and the other
#   candidates it weighed;
# * **Analyst**: the employer's past reports, possible repeats, how common the hazard is in this
#   industry, and similar past injuries.
#
# Here the citation comes from the offline rules and, with `USE_EMBEDDINGS = False`, a keyword search
# alone, so read it as an example of what is passed on, not of how accurate the search is. A wrong
# section is what the Decision critic is there to catch (part 15); the measured accuracy is in parts
# 17 and 18.

# %%
chosen = max(state["stage2"], key=lambda rid: state["stage1"][rid]["priority"])
branch_result = state["stage2"][chosen]
report, intake, pick = branch_result["report"], branch_result["intake"], branch_result["pick"]

display(
    Markdown(
        f"**Report {chosen}**, {report['employer']}, {report['city'].title()}, NAICS {report['naics']}\n\n> {report['narrative']}"
    )
)
display(Markdown("**Intake**"))
display(
    pd.Series(
        {
            "activity": intake["activity"],
            "hazard": intake["hazard_type"],
            "machine or hazard": intake["machine_or_hazard"],
            "injury": intake["injury"].strip(),
            "event code": f"{intake['event_code']} (confidence {intake['confidence']:.2f})",
            "facts the story leaves out": "; ".join(intake["missing_facts"]) or "-",
        }
    ).to_frame("value")
)
display(Markdown("**Standards**"))
display(
    pd.Series(
        {
            "cited": f"{pick['primary']} {pick.get('secondary') or ''}".strip(),
            "paragraph": pick.get("paragraph", ""),
            "paragraph text": (pick.get("paragraph_text") or "")[:300],
            "other candidates": ", ".join(branch_result["candidates"][1:]),
            "emphasis programs": ", ".join(branch_result["emphasis"]) or "-",
        }
    ).to_frame("value")
)
display(Markdown("**Analyst**"))
display(
    pd.Series(
        {
            "employer's past reports (same name)": branch_result["history_same"],
            "possible matches to confirm": branch_result["history_possible"],
            "repeats within a year": len(branch_result["repeats"]),
            "share of this hazard in the industry": f"{branch_result['industry_share']:.1%}",
        }
    ).to_frame("value")
)
similar = pd.DataFrame(branch_result["similar"])
if not similar.empty:
    display(similar[["report_id", "event_date", "state", "narrative"]])

# %% [markdown]
# ## 14. Optimizer: Category 1 first, then the inspector days
#
# Every Category 1 report is inspected. The integer program then spends the inspector days left on
# the reports with the highest priority per day. Each row carries the reason a person will read.
# If the days are too few even for Category 1, a relaxed model says how many more are needed
# (`shortfall`).

# %%
triage = state["findings"]["triage"]
plan = triage["plan"]
rows = pd.DataFrame(triage["rows"])
display(
    Markdown(
        f"**{(rows['decision'] == 'inspection').sum()} inspections and {(rows['decision'] == 'rri_letter').sum()} RRI letters**, "
        f"using {plan['days_used']:g} of {triage['capacity']:g} inspector days; shortfall {plan['shortfall']:g} days."
    )
)
display(rows[["report_id", "employer", "decision", "priority", "days", "standard", "reason"]])

# %% [markdown]
# ## 15. Writer and Decision critic
#
# The **Writer** never types a number. Its drafts hold placeholders such as `{{inspections}}`, and
# each placeholder is filled from a **ledger** of facts that a tool recorded, with the tool's name
# as the source. Below: the placeholders of the week's summary with their sources, and one RRI
# letter as it would be sent.
#
# The **Decision critic** then checks each citation against the eCFR text and OSHA's own rules,
# each number, and the plan rules. A problem it can fix goes back to the Writer or the Optimizer (at
# most twice); one it cannot goes to a person, listed under the answer.

# %%
from safereport.ledger import FactLedger


def render(draft: dict) -> str:
    ledger = FactLedger()
    for key, (value, source, same_months) in draft["facts"].items():
        ledger.add(key, value, source, same_months=same_months)
    return ledger.render(draft["template"])


summary_draft = state["drafts"]["triage:summary"]
display(
    pd.DataFrame(
        [{"placeholder": k, "value": v[0], "recorded by": v[1]} for k, v in summary_draft["facts"].items()]
    )
)
letters = sorted(k for k in state["drafts"] if k.startswith("triage:letter_"))
print(f"{len(letters)} RRI letters drafted. The first one:\n")
if letters:
    print(render(state["drafts"][letters[0]]))

# %%
critic_lines = [t for t in state["trace"] if t["agent"] == "Decision critic"]
print(
    f"Decision critic: {len(critic_lines)} checks recorded; Writer send-backs: {state.get('writer_retries', 0)}"
)
for line in critic_lines:
    print(" -", line["summary"])
issues = pd.DataFrame(state.get("issues", []))
if issues.empty:
    print("No open issue for a person.")
else:
    display(Markdown("**Left for a person to check** (route `person`):"))
    display(issues[["report", "rule", "message", "suggestion"]])

# %% [markdown]
# ## 16. A person decides
#
# The run is paused at the approval step. First the Area Director **asks for a change**: one report
# planned for a letter is moved to an inspection. The graph resumes at the Optimizer with that rule,
# re-plans within the same days, and the Writer and critic run again. Then the Area Director
# **approves**, and the decision is logged with who made it.

# %%
letter_rows = rows[rows["decision"] == "rri_letter"]
if letter_rows.empty:
    print("Every report is already planned for an inspection; no change to ask for.")
else:
    moved = letter_rows.iloc[0]["report_id"]
    before = dict(plan["decisions"])
    stream(
        Command(
            resume={
                "action": "changes",
                "by": "Area Director (notebook)",
                "force_inspection": [moved],
                "notes": {moved: "notebook demo: inspect this one"},
            }
        )
    )
    state = graph.get_state(config).values
    after = state["findings"]["triage"]["plan"]["decisions"]
    changed = {rid: f"{before[rid]} -> {after[rid]}" for rid in after if before.get(rid) != after[rid]}
    print(f"Moved {moved} to an inspection. Rows that changed: {changed}")
    print(f"Inspector days used: {state['findings']['triage']['plan']['days_used']:g}")

stream(Command(resume={"action": "approve", "by": "Area Director (notebook)"}))
state = graph.get_state(config).values
display(
    pd.DataFrame(
        [{k: v for k, v in entry.items() if k in ("at", "by", "action")} for entry in state["decision_log"]]
    )
)
display(Markdown(state["answer"]))

# %% [markdown]
# ### What each agent contributed to this week
#
# Counted from the run's trace and state above, so the numbers are this run's, not typed in.

# %%
trace = pd.DataFrame(state["trace"])
final_plan = state["findings"]["triage"]["plan"]["decisions"]
contribution = {
    "Planner": f"{len(state['tasks'])} task(s); asked for {question['missing']}",
    "Intake": f"{len(state['stage1'])} reports coded in stage 1, {len(state['stage2'])} read again in a branch",
    "Standards": f"{len(state['stage2'])} citations with section and paragraph",
    "Analyst": f"{sum(len(b['similar']) for b in state['stage2'].values())} similar past injuries, "
    f"{sum(len(b['repeats']) for b in state['stage2'].values())} repeats found",
    "Optimizer": f"{sum(v == 'inspection' for v in final_plan.values())} inspections, "
    f"{sum(v == 'rri_letter' for v in final_plan.values())} letters",
    "Writer": f"{len(state['drafts'])} drafts, every number from the ledger",
    "Decision critic": f"{len(state.get('issues', []))} issue(s) left for a person",
}
per_agent = trace.groupby("agent").size().rename("trace lines").to_frame()
per_agent["model slots used"] = trace.groupby("agent")["model"].apply(
    lambda m: ", ".join(sorted(set(m) - {""})) or "none"
)
per_agent["contribution"] = pd.Series(contribution)
display(per_agent.reindex([*contribution, *(a for a in per_agent.index if a not in contribution)]).fillna(""))

# Names the later sections can use: services, graph, config, state, handoff_table, stage1, rows.
