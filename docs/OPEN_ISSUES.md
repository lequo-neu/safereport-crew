# Open issues before Phase 3

Updated on 19 November 2026, after the team decisions and the second independent review.

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
11. **Model IDs move.** `gpt-5-nano` is listed by one third party for retirement on 11 December
    2026, and `gemini-3.5-flash` forwards to 3.6 Flash. Recheck before the demo.

## Still open

* **Router accuracies.** The router still chooses by the priors in `config/models.toml` (0.90
  for Claude on retrieval, 0.75 for GPT 5 nano). The live numbers come from the final test set,
  so routing on them would select models on the test set. Proposal: measure the router's
  accuracies on reports outside the key (for example a labelled slice of the 2025 holdout), and
  report the key only as the final score.

* **Version control.** The folder is not a git repository yet; the team still has to agree on
  the repository and the v0.1 release.
* **Name of the drafting tool** for the answer key, for `docs/AI_USAGE.md`.
