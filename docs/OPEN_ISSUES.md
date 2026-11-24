# Open issues

Updated on 19 November 2026, after the team decisions and the second independent review, and
on 23 November 2026 with what the Basic stage checks (B1 to B5) found.

## Decided by the team (19 November 2026)

1. **Live model experiments.** The keys were copied into this project's `.env` (gitignored) with
   a cap of $1.50. Every reply is cached in `outputs/model_cache.sqlite` and every paid call is
   charged against the cap (`src/safereport/spend.py`). To keep the answer key a final test set,
   the terms prompt was checked for format on reports outside the key, then scored once per
   model with `safereport eval-live --model <name> --score`. Gemini 3.5 Flash (which now forwards
   to 3.6 Flash) returned 503 and 429 errors for most calls, so GPT 5 nano took its place as the
   cheap model; Claude Sonnet 5.5 ran once after it. Strict top 3 rose from 21 of 51 cases
   (41.2%) to 31 with GPT 5 nano (60.8%, paired p 0.021) and 36 with Claude (70.6%, p 0.0003);
   Claude against nano is 7 gained and 2 lost (p 0.18). The experiment cost $0.14. Details in
   the README and `eval/results/live_terms_summary.json`.
2. **Answer key.** The 60 cases stay as the final test set (51 with a standard, 9 without). No
   prompt, weight or threshold is tuned on them, and every rate is shown with a 95% Wilson
   interval. The drafting step and the reviews are described in `docs/AI_USAGE.md`.
3. **Case C20.** Hamad changed C20 in `data/labels/to_label_Hamad.csv` to "no specific standard
   (general duty)": the press was locked out and the pinch came while pushing out a die by hand.
   `answer_key.csv` was rebuilt from the three files.
4. **Emphasis program scopes.** The five largest directives were read. Amputations: the 91 NAICS
   codes of Appendix B. Heat: 55 four digit codes. Falls: construction, plus the ten listed
   activities anywhere. Warehousing: the seven NAICS codes, with the hazard families the
   directive names (forklifts, struck by and caught in, slips and falls, lifting, heat, fire,
   racks and docks), which flag 36 of the 42 warehousing reports of the 2025 holdout. Primary
   metals: the 18 codes of Appendix B (324199 and 17 codes in 331) with its health hazards
   (exposures, fumes, carbon monoxide, silica, lead, heat stress, noise), not every report in 331.
5. **Employer matching.** 150 pairs were labelled: the "same" rule held for 100 of 100 pairs and
   45 of the 50 possible pairs were one employer (P118, Cosco against Costco, is one of the five
   that were not). The matches panel groups possible matches by name pair, and one decision
   settles every report with that pair (`DecisionStore` in `src/safereport/employers.py`).

## Fixed after the second review (19 November 2026)

* **The weekly list skipped the citation and domain checks.** The critic now checks the standard
  of every report in the week, and a correction goes through the Optimizer, so the list, its CSV
  and the letters carry it. On the Texas week it corrected 9 of 31 standards (13 with
  embeddings) in one round; before, `revise` would have failed with a `KeyError`.
* **A correction could walk into a worse standard.** When a suggestion named the General Duty
  Clause in words, `revise` took the next candidate instead (a valet vehicle that ran over a
  worker ended on 1910.217, presses). Suggestions now cite `OSH Act 5(a)(1)`, and a fallback
  candidate must pass the domain rules.
* **Lines that failed a check could reach the answer.** After the last retry, a line that compares
  unequal periods or cites a section eCFR does not have is left out, as an untraced number was,
  and domain warnings that remain are listed for a person.
* **The Planner saw a pasted narrative before redaction.** Names, phones and addresses are now
  hidden from the Planner whenever the call can reach a cloud model, fallbacks included; state
  names stay visible and placeholders in the plan are put back.
* **A pasted narrative had no event code or date for the Analyst.** The industry share uses the
  code the Intake agent read, and the report is dated to the last day of the replayed week.
* **A trend over one year crashed, and an empty range would have too.** One year now says there is
  nothing earlier to compare with; an empty range says no report matches.
* **A model reply with two JSON objects failed** (Claude corrected itself and wrote a "final
  answer"). The parser takes the last complete object, and a reply that cannot be used is still
  charged to the budget, so the cap counts every token paid for.
* **`load_services(dense=False)` still used embeddings for similar injuries**, while the default
  used none for standards. Both now follow one switch, on when the embedding model is cached.
  The citation index reads every eCFR part on disk.

## Known limits we can live with (and will state)

6. **OIICS changed in January 2024.** The data layer refuses event filters over a period that
   spans the change. Trends across 2024 use OIICS 3 codes estimated by the baseline for older
   reports, marked as estimated. The recoded 2023 groups differ from the real 2024 groups by a
   total variation of 0.064, against 0.047 between the real 2024 and 2025.
7. **Category 1 criteria the data cannot show.** There is no age field, so "a worker under 18"
   comes only from the narrative, and "imminent danger" is a judgement. Reports with two or more
   hospitalized were inspected 68.8% of the time, so past practice and the written rule differ.
8. **Redaction of bare names is a heuristic.** Titles, role words and capitalized word pairs the
   narratives never write in lower case are hidden; a name made of common words ("Rose Hill")
   still passes. OSHA's narratives do not name workers, so this matters only for pasted text.
9. **Old style eCFR sections.** Seven sections in an older format (1910.106, .110, .269, .109, .6,
   .180, .399) give some paragraphs a doubtful path; those are cited by section only. None is in
   the answer key.
10. **Retrieval without a model is weak.** With BM25 and embeddings, the primary section is in the
    top 3 for 41.2% of the 51 cases (95% CI 28.8 to 54.8). With a model's terms it is 60.8% to
    70.6%, so the offline mode is a fallback, not the way to cite standards.
11. **Model IDs move.** Rechecked on 23 November 2026: OpenAI's deprecations page lists
    `gpt-5-nano` (snapshot 2025-08-07) for shutdown on 11 December 2026, after the demo, so the ID
    stays for this project; a later run would move to the replacement OpenAI names there. Google
    lists `gemini-3.5-flash` as deprecated, with requests routed to 3.6 Flash and no shutdown date.
    `claude-sonnet-5-5` is current. Recheck once more on the demo day.

## Found while building the app (Phase 3)

* **The Standards agent cited a paragraph nobody had checked.** For a laminator jam it cited
  1910.147(a)(2)(iii)(A), the cord and plug exemption. Retrieval is measured at section level, so
  the crew now cites the section, quotes its opening, and shows the closest paragraph apart for a
  person to check. The runner up section is no longer called a secondary citation.
* **A dead provider slowed every call.** Each call retried it after two seconds. A model that
  fails every retry with an outage is now skipped for 60 seconds (`cooldown_seconds`).
* **Typed decisions in the table were error prone.** Rows now move with two pick lists, and the
  employer rule ignores case, commas and suffixes such as Inc.
* **Offline letters cite the top BM25 section** (about 41% right on the key). With `--live`, the
  Standards agent adds model terms (61% to 71%).

* **The week asked for a person to sign letters unread.** A picked row now shows its narrative,
  checks, employer history (with why an earlier report does or does not count as a repeat) and
  the letter as it will be sent, on the same page as the approval.
* **A state map of report counts would mislead**, so there is none: State Plan states are
  almost absent from this federal file (California 539 reports, Texas 17,491) and there is no
  employment to divide by.

* **Edge cases found in UI testing.** Negative, blank or absurd inspector days are refused before
  planning (zero stays allowed: a week without spare days is real, and the plan then says how
  many days the Category 1 reports need). An empty week (Wyoming, 17 to 23 November 2025) says
  so and cannot be approved. A safety talk needs one of the four topics.

## Found in the Basic stage checks (23 November 2026)

From `docs/reviews/hamad.md` (B1, B3), `docs/reviews/khoa.md` (B5) and the B2 and B4 results.
None of them changed a Category 1 rule during the Basic stage; rule changes are Advance work,
measured outside the 2025 holdout.

* **Repeat offenders and SVEP.** OSHA's fourth Category 1 criterion needs the employer's citation
  history and the Severe Violator Enforcement Program list. The SIR file does not link to OSHA's
  citation records, so neither the crew nor the hand check can tell.
* **Local and regional emphasis programs are not encoded.** The crew encodes twelve national
  programs; a report covered only by a local or regional program is missed and not counted as a
  miss. The Region 6 (Texas) programs are a candidate for Advance (#10).
* **Imminent danger is left to a person's flag.** No narrative rule decides it, and the hand check
  reports it apart (`cannot_tell` on all 100).
* **Employer history is checked only within the same state.** An earlier report from the same
  company in another state does not count.
* **The employer history criterion and OSHA's choices (#18).** It marks 94 of the 1,000 holdout
  reports as Category 1, and OSHA inspected 19 of them (20%), below the 30% overall rate; it is
  the main reason putting Category 1 first lowers the AUC. Whether "employer" means the company
  or the establishment (Dollar Tree, B1) is decided in Advance; the rule stays as written.
* **Emphasis program gaps**, all Advance: warehousing NAICS 491110 for retail post offices (#26)
  and the trenching program (#27), from B1; staffing employers doing construction work at height
  (#30), from B3. All four Category 1 misses and three false alarms of B3 come from the emphasis
  program criterion. #30 is addressed by a narrow work route for NAICS 5613 measured outside the
  holdout ([docs/FALLS_STAFFING.md](FALLS_STAFFING.md)); it does not catch K083, and the B3
  numbers stay those of the Basic rule.
* **CSV downloads on Windows (#17)** had blank rows and two failing tests; fixed in #21 (downloads
  are written as their text is).
* **The B1 walkthrough screenshots** are kept on Hamad's machine (`.local/b1/screenshots/`), not
  in the repository; the steps and results are in `docs/reviews/hamad.md`.
* **An invalid 1910.217 as the secondary citation** (B5): the press check looked only at the
  primary. Fixed in #31: it checks both, and removes the secondary without dropping a valid
  primary. On the B4 week, 20251111462 (die setup on a punch press) now ends on 1910.147.
* **Critic and Writer gaps found in B5**, all Advance: the fall check flags 1910.28 for a person whenever
  the worker did not fall, though 1910.28(c) covers falling objects (#32); an energy control
  correction keeps an unrelated industry standard as the secondary (#33); the RRI letter keeps a
  weak citation and dates the reply from the letter, not the call (#34); the press check reads
  only the Intake's word "press", so a real punch press can lose 1910.217 (#35).
* **The construction Falls filter** (#29, Advance): 4 of 20 reports it leaves out describe a
  worker who fell, one of them with an object that struck the worker too.
* **Report 20251111512** (thumb amputation on a powered miter saw): stage 1 cites 1910.212 and the
  model branch 1910.243. Khoa's provisional choice between the two is 1910.212, with 1910.213
  (woodworking machinery) still to check; the narrative does not say how the saw was mounted or
  guarded, so it stays for a person.

## Still open

* **A fall standard for an injury that was not a fall** (added on 19 November 2026, with the
  team's agreement; B5 found that it also flags falling object cases that 1910.28(c) covers, see #32). A section of 1910.22, .23, .28, .29 or .140 needs an injury where the worker
  fell. Measured once on the answer key, the rule flagged 2 of the 10 fall cases (C14, C32): the
  offline Intake reads "heel caught on a cart" as a machine. The rule was not adjusted to those
  cases; it is a check for a person (an amber badge, a line under the answer) and the critic does
  not change the citation. On the Texas week it flags 4 reports: rope around a capstan, scale off
  a crane load and a beam on a forklift are right; a worker who jumped off a trailer did fall.

* **Router accuracies.** The router still chooses by the priors in `config/models.toml` (0.90
  for Claude on retrieval, 0.75 for GPT 5 nano). The live numbers come from the final test set,
  so routing on them would select models on the test set. Proposal: measure the router's
  accuracies on reports outside the key (for example a labelled slice of the 2025 holdout), and
  report the key only as the final score. This is B7 (#8).

* **Name of the drafting tool** for the answer key, for `docs/AI_USAGE.md`.
