# AI usage

Where AI tools touched this project, what they did, and how the team checked it.

## Building the project

* **Code, tests and documents** were written with an AI coding assistant (Claude Code) working
  under the team's direction, one phase at a time. The team set the scope and the decisions;
  every phase was checked by the test suite (lint, unit and end to end tests, a run without the
  data as in CI) and by an independent review before the next phase began.
* **Reading OSHA directives.** The emphasis program scopes in `data/reference/emphasis_programs.toml`
  were read from the directives themselves (amputations, heat, falls, warehousing, primary metals)
  with text extraction and checked by Khoa and Hamad; the primary metals entry was then narrowed to
  the 18 NAICS codes of its Appendix B and its health hazards. The one line hazard summaries are our own
  words; programs whose directive was not read are marked `verified = false` and never force an
  inspection.

## The answer key (`data/labels/answer_key.csv`)

* **Draft labels** for the 60 manufacturing reports came from an automated tool. Each label was
  then reviewed by all three of us against `docs/LABELING_GUIDE.md`; 15 cases were reviewed twice.
* **Agreement.** On those 15, both reviewers kept the same CFR section in 13 (86.7%). Because the
  drafts share one source, this measures how often a reviewer accepted the draft, not
  independent labelling, and we report it that way.
* **Settled and corrected.** The two disagreements, C05 and C07, were settled together
  (`data/labels/settlements.csv`). C20 was corrected by Hamad after review: the press was locked
  out, so the label moved from 1910.147 to "no specific standard (general duty)".
* **Use.** The key is the final test set: no prompt, weight or threshold is tuned on its cases.
  Every rate on it is reported with a 95% Wilson interval, because 51 cases with a standard give
  wide intervals.
* **Still to state:** the name of the drafting tool. If it is one of the four models the project
  evaluates, that model's standards score is reported separately.

## The employer pair check (`data/labels/employer_pairs_check.csv`)

150 name pairs (100 the matcher calls the same employer, 50 it leaves as possible) were labelled
yes or no, with the labeller named in each note. The "same" rule held for 100 of 100 pairs; 45 of
the 50 possible pairs were the same employer.

## The Basic stage evaluations

Each task records here which AI tool helped and how the result was checked.

* **B2, inspection priority against OSHA's choices** (Hamad, pull request #15). The code, tests
  and write up were drafted with Claude Code and checked by Hamad: the AUCs against scikit-learn,
  DeLong's covariance against a brute force version and a bootstrap, the 1,000 holdout IDs and
  OSHA's raw inspection field. Kevin reran the command on another machine and got the same JSON
  and per report CSV. No model is called and nothing was paid.
* **B4, what the two stage batch saves** (Hamad, pull request #16). Drafted with Claude Code and
  checked by Hamad: the call counts from the per agent log, the 31 reports of the week, and the
  one decision field that differs. Kevin reran it on another machine: the same calls, decisions
  and changed citation, and a cost estimate within one token. Offline, nothing was paid.
* **B1, review of the triage logic and the app** (Hamad, the B1 pull request). The Arabic
  revision: an AI assistant drafted suggestions and questions; Hamad, a native speaker, read all
  26 lines against the English and decided each change. Claude Code drafted the rest of
  `docs/reviews/hamad.md` (B1): the Category 1 checks against OSHA's memo and directives (read
  from osha.gov), the weights evidence from the 2015 to 2024 reports, a scripted browser
  walkthrough (Playwright, offline) at laptop and phone width, and automated checks of the Arabic
  Word file in Microsoft Word and the week's CSV in Excel. Hamad decided which findings are defects and which are
  questions. Hamad read the Arabic lockout Word file on screen in Microsoft Word and confirmed it
  (22 November). Not checked by a person yet: the walkthrough screenshots. Nothing was paid.
* **B3, hand check of the Category 1 rules** (Hamad, pull request #20). Claude Code wrote the
  sampling script and its test, drafted the labelling guide from the rules Kevin settled on #4,
  and wrote the scoring command, a guide-based employer history check and their tests. It also
  made an AI-assisted first pass over the 100 cases (`eval/provisional/`): the hospitalized count
  as rule 7 says, employer history from the guide's written procedure, and Claude's own reading of
  each narrative for the under-18 and emphasis program criteria. That pass is not a human label:
  it is kept out of `eval/results/` and out of `data/labels/`, and its per-case answers stay off
  GitHub until the hand labels are done; it is then compared with them as a separate line.
  Cost: the pass was made in a Claude Code session, not through the crew's model keys. No model
  call went through the app (the crew's spend ledger, `outputs/model_cache.sqlite`, has no
  record), so nothing counts toward the $1.50.
  On 22 November Claude Code also built a local review page for labelling one case at a time
  (the report, OSHA's codes, the same-state reports in the history window and the guide's
  rules; never the crew's output or OSHA's inspection field), and a bulk-save script that writes
  only rows passing the guide's checks, with a backup and a row-by-row check afterwards.
  **Hamad's earlier 100 labels are AI-assisted, not blind hand labels.** Hamad personally
  reviewed all 100 cases in Excel, corrected the classifications he disagreed with, and finalized
  all 100 labels; the file he reviewed was built from the AI first pass, and 76 of the 100 notes
  begin with the same text as that pass, so they are not independent of it. Every row's notes say so.
  Claude Code made formatting-only changes to fit the guide: the reason for each `cannot_tell`
  in the guide's `column: reason` form; imminent danger `cannot_tell` (rule 5) where the file
  said "no" (65 cases); and, where the file's overall answer contradicted its own criteria
  (25 cases), the overall answer that follows the criteria, on Hamad's decision. They are not the
  blind check Kevin set on #4: scored only as `--source ai-provisional`, kept out of
  `eval/results/`. (Khoa's 15 were labelled separately, by Khoa.)
  **The fresh round (Kevin on #4, 23 November):** Hamad labelled all 100 again by hand, in a
  note, and pasted the answers to Claude Code, which copied them into the label file unchanged
  (on his instruction it deleted the citation on K023 and K058, labelled "no"), scored them and
  drafted the results in `docs/reviews/hamad.md` from the scoring output. It wrote no label or
  evidence. Hamad then gave the reasons for his `cannot_tell` answers; Claude Code checked them
  against the reports and the program list, wrote them into `notes` in the guide's form, and put
  the facts it checked (dates, NAICS codes) in `docs/reviews/hamad.md`, not in his notes. It also
  extracted the `evidence` for his yes answers from the reports (the narrative's words and
  OSHA's fields), which Hamad approved, and checked the four missing citations against the
  directives' scope (CPL 03-00-027 Appendix B; CPL 03-00-025 section II, read from the PDF).
  On those findings Hamad changed K046 and K087 from yes to no and added the citation on K059;
  Claude Code applied his decisions, recorded the earlier values, and re-scored. The round is not blind to an earlier reading: Hamad had seen the AI first
  pass (21 November) and the AI-assisted file built from it. Before the round Claude Code set up
  a blank copy and a review page with keyboard and voice commands (not used in the end), and
  extended the scoring command: the employer history counts, the narrative against the
  `hospitalized` count, imminent danger cases apart, and a check that only complete hand labels
  with no AI-assisted mark are written to `eval/results/`. The AI first pass is compared with the
  hand labels as agreement only, in `eval/provisional/`. No model call went through the app;
  nothing was paid.
  **A second, separate Claude pass (22 November).** Besides the first pass above, a separate
  Claude pass labelled 85 of the 100 cases (all but Khoa's 15) in a simplified sheet (the four
  criteria, imminent danger, Category 1, citation and confidence; no notes or evidence), dated
  22 November, 23:49. A spreadsheet of Hamad's that matched it on 84 of those 85 cases was not
  used: Claude Code flagged the overlap on 23 November, and Hamad then labelled the 100 again in
  the note described above, having seen that pass before. It is not scored or committed.
  **Kevin's ruling on #20 (23 November, evening).** On Kevin's instruction the employer history
  column (`similar_report_within_12_months`) is no longer Hamad's hand label: Claude Code ran
  `scripts/category1_history_by_guide.py` (the guide's written rule over OSHA's file, no crew
  code, no model call) and copied its answers into the label file: 12 yes, 84 no, and its 4
  possible-only matches left `cannot_tell`. Each row's `notes` names the script and keeps Hamad's
  earlier hand label; each yes carries the earlier report's ID and date in `evidence`, marked
  "(scripted)". Claude Code then recomputed `category_one` by the guide's rule and applied
  Kevin's two other rulings mechanically: the amputation program read from CPL 03-00-027 for all
  of 2025 (a note on the six reports before 27 June; CPL 03-00-022's list was not read), and
  K083's citation (CPL 03-00-025 II.A) and low confidence. Hamad decided K069 on its merits
  himself (`cannot_tell`, with his reason); Claude Code wrote no narrative label. It re-scored
  with `--source human` and redrafted the results in `docs/reviews/hamad.md` and the README from
  `eval/results/category1_check.json`. Khoa's 15 are unchanged. Nothing was paid.

* **B5, standards and Vietnamese talks** (Khoa). ChatGPT assisted with the review write-up, case-table preparation, and small code/test edits. Khoa compared the injury narratives with the labelling guide, checked OSHA's published standards and RRI procedure, and ran the offline test suite. Unresolved citation applicability and configuration differences are noted in `docs/reviews/khoa.md`, not treated as verified facts.

## The Advance stage

* **Issue #30, the Falls program for staffing agencies** (Hamad). Claude Code read CPL 03-00-025
  from the PDF on osha.gov (text extraction), wrote the work route, the construction words, the
  tests, the evaluation script and `docs/FALLS_STAFFING.md`. The construction words were written
  from 29 CFR 1910.12(b) and checked against staffing reports from 2015 to 2019 only. The rule
  was then fixed and run once on 2020 onward, and not changed after it. Two changes came before
  that run, from tests written for it, not from data: a veto for "fell ... onto the worker", and
  corrected test narratives. The B3 sample and the 2025 holdout were not read for the rule, and
  the B3 results were not rerun. K083 was checked once, after the rule was fixed, to say in the
  docs that it is not caught. The false positive concerns in the doc are Claude Code's reading of
  the 20 added narratives, not labels, and no precision is claimed from them. No model call
  went through the app; nothing was paid.
* **Issue #37, hand labels of the 20 reports #30 adds** (Hamad). Hamad labelled all 20 by hand
  (construction_fall, confidence, reason) in a workbook Claude Code built with the narrative and
  OSHA's event fields only: no AI answer, no suggestion, and neither the rule's matched words nor
  OSHA's inspection flag. Claude Code checked the returned workbook (all 20 reports, allowed
  values, reasons present, read-only columns unchanged), copied the labels unchanged into
  `data/labels/staffing_falls_added_Hamad.csv`, and wrote the scoring script, its tests and the
  doc text. It did not change any label. The rule was not changed after the labels.
* **Issue #38, the Colab notebook: foundation and Texas week** (Hamad). Claude Code wrote parts 1
  to 16 of `notebooks/safereport_crew.ipynb` (as section files in `notebooks/sections/`), the
  script that assembles them, `tests/test_notebook.py`, the notebook README and the Colab test
  checklist, from the README, the graph code and a local run. Every number the notebook shows is
  printed by a cell from the run or the data, not written in its text. It was run end to end on a
  local machine from a fresh clone of the pinned commit. On Google Colab, Claude in Chrome ran it
  (commit 1b504c7) in a fresh runtime, following `notebooks/COLAB_TEST_CHECKLIST.md`; Hamad
  supervised the run and checked the outputs. Khoa's parts (17 to 19) are placeholders. No model
  call went through the app; nothing was paid.
* **Issue #41, the prevention plan** (Kevin). Claude Code wrote `src/safereport/prevention.py`,
  the prevention node, the Writer's template, the Trends page section, `config/prevention.toml`,
  `data/reference/safety_pays.toml`, `tests/test_prevention.py` and `docs/PREVENTION_PLAN.md`.
  The Safety Pays costs were read from osha.gov (the estimator text page and the background page)
  by a fetch agent and copied with their source; the map from OSHA's nature titles to Safety Pays
  types is Claude Code's, written from the list of titles in the file. The controls' yearly costs
  and effect ranges are planning assumptions Claude Code proposed for the demo, not measured
  values; they are marked as assumptions in the config, the app and the answer, and the user can
  change them. The plan reads every report, as the Trends page does; nothing was tuned on the
  answer key or the 2025 holdout, and no Category 1 rule or triage weight changed.
  No model call went through the app; nothing was paid.

## The safety talk translations

The Spanish, Chinese, Tagalog, Vietnamese and Arabic texts of the four safety talks were drafted
with an AI assistant. Hamad reviewed the Arabic line by line as a native speaker (B1), and Khoa
reviewed the Vietnamese (B5, read again by Kevin). The Vietnamese forklift talk adds one rule the
other languages do not have: do not stand under a raised load. The Spanish, Chinese and Tagalog
texts still need a native speaker's review before a plant prints them; the README says so beside
the feature.

## The product's own use of models

* At run time the crew calls up to four models (Claude Sonnet 5.5, GPT 5 nano, Gemini 3.5 Flash,
  Gemma 4 E4B on LM Studio) through a router; without keys every step answers from fixed rules
  (`src/safereport/offline.py`), which are never reported as model results.
* Employer names, addresses and names of people are replaced by placeholders before any text goes
  to a cloud model.
* Paid experiments are capped at the team's budget of $1.50 and every reply is cached
  (`outputs/model_cache.sqlite`, not committed); `safereport eval-live` records what was spent.

## B6: Seeded citation error evaluation

ChatGPT assisted with seed preparation, scoring implementation,
regression tests and interpretation of the results.

The 24 seeded errors were committed before evaluation.
All results were generated using existing offline domain
checks and eCFR citation verification.

The original answer key and domain rules remained unchanged.
No paid model calls were made.

### B7: independent router evaluation (#8)

ChatGPT assisted Khoa with the sampling and validation scripts,
reference-label QA, regulatory research, measured-router integration,
regression tests, and debugging.

The original reviewer drafts were preserved. Kevin and Hamad
confirmed the three disputed cases in issue #8. Additional
adjudication recommendations were AI-assisted and recorded
separately from the original reviewer labels.

A provisional offline retrieval baseline was examined before
the final label freeze. This limits the claim of fully blind
adjudication. No live model answers were examined before freezing
the reference CSV.

The initial offline regression suite passed 432 tests.

After the reference labels were frozen, Khoa ran the offline
hybrid baseline and GPT-5 Nano evaluation on the 35 eligible
reports. Strict Hit@3 was 12/35 offline and 17/35 with Nano.
The paired comparison found five improvements, no deterioration,
and an exact McNemar p-value of 0.0625.

Gemini 3.5 Flash failed at B7-017 after 10 completed cases.
An additional rerun encountered the same failure. Gemini 3.6
Flash passed a separate synthetic diagnostic but its evaluation
stopped at B7-004 because of a rate limit after two completed cases.
Both experiments are preserved in the evaluation results.

ChatGPT assisted with diagnosing provider failures and testing
a correction for Gemini thinking-token accounting. Five dedicated
mocked tests passed. The provider correction and its tests are
deferred to a separate follow-up rather than included in B7.

Gemini recovery is deferred. Neither Gemini version is assigned
measured accuracy. Claude was not evaluated because credentials
were unavailable. Gemma remains unmeasured.

GPT-5 Nano's measured strict Hit@3 replaces its retrieval prior.
Other step types and unmeasured models retain their priors.
These assumptions are not equivalent to measured accuracy.

Recorded local expenditure was $0.0559263, including diagnostic
calls and incomplete evaluations. Gemini prices remain unconfirmed,
and historical thinking-token consumption is not fully reconciled.
Using the previously reported team expenditure of $0.14,
estimated combined spending was $0.1959263.

The draft PR was not opened before the live experiments as
originally planned. The frozen dataset and original answer key
were not modified during the live evaluations.

### B7 follow-up: November 24, 2026

ChatGPT assisted with the Claude result reconciliation,
paired McNemar comparisons, measured routing configuration,
Gemini diagnostic and regression tests.

Claude completed all 35 eligible cases using my own API key.
The original frozen labels were not changed.

The final personal-key Gemini 3.5 Flash diagnostic returned
HTTP 503 UNAVAILABLE on B7-017. Gemini remains unmeasured,
and further B7 retries were stopped.

Only the retrieve accuracies for Claude and GPT-5 Nano
are measured. Other model and step priors remain unchanged.

### B7 review correction: November 24, 2026

Following Kevin's review of PR #42, ChatGPT assisted
with the measured-first model selection correction,
merge conflict resolution and regression tests.

For lowest-cost and best-quality routing, available
measured models now take precedence over unmeasured
priors for the same step. When no available model has
a measurement, the existing prior-based policy applies.

All 32 diagnostic routing decisions selected Claude
for retrieval with all four backends registered.
All 30 targeted regression tests passed.

The original routing thresholds, frozen reference
labels, measured accuracies, private mode and
provider-failure fallback chain remain unchanged.

No additional paid model calls were made.

### B8: router cost and accuracy comparison (#9)

ChatGPT assisted Khoa with the evaluation design, source-data
validation, router replay implementation, visualization,
Gradio integration, regression tests and interpretation.

The evaluation uses the frozen B7 reference slice of 50 reports,
of which 35 have an eligible reference standard. The original
answer key, frozen labels, B7 results, routing configuration
and production routing policy were not changed.

The production Router.choose() method was exercised with all
four configured backends registered offline. Sixteen synthetic
signal combinations were checked under each of the lowest-cost
and best-quality routing modes.

All 32 selections chose Claude using measured retrieval accuracy.
The router replay therefore reproduces Claude's 22/35 strict
Hit@3 result (62.9%, Wilson 95% interval 46.3% to 76.8%) and
historical evaluation cost of $0.061832.

The router point is a retrospective replay, not an independent
live evaluation. The same B7 slice supplied the measured routing
accuracies. Synthetic routing signals are not observed report-level
signals. No additional accuracy or cost advantage over Claude
alone is demonstrated.

Gemini and Gemma remain unmeasured and are excluded from the
cost-accuracy chart. Historical costs are reused from B7.
No additional model calls were made and nothing was paid.

A separate B7/B8 chart and evaluation table were added to the
Admin page, preserving the original 51-case answer-key benchmark.
Claude and the router share their actual chart coordinates.

Khoa ran the reproduction command twice and obtained identical
JSON fingerprints. All 20 dedicated B8 tests and all 486
repository tests passed locally. Ruff linting and formatting
checks passed. Dedicated tests also prevent backend calls
during the replay.

#### B8: review corrections (PR #45)

Following Kevin's review, Khoa merged the latest main
and resolved the views.py import conflict, preserving
both the prevention feature and the router chart.

ChatGPT assisted with correcting chart annotations,
removing the whole-file configuration fingerprint,
reusing the shared Wilson interval function, and adding
four regression tests.

The new tests cover multiline chart labels, routine
configuration metadata updates, the three frozen evidence
fingerprints and rejection of changed measured model IDs.

The regenerated B8 result differs only by the removal
of the config/models.toml fingerprint. Measured accuracy,
confidence intervals, historical costs and routing
decisions remain unchanged.

Configuration metadata may now change without invalidating
the replay. Model identity and measured accuracy checks
remain in place.

Khoa verified that all 24 dedicated B8 tests and all 503
repository tests passed. Ruff linting and formatting
passed, and repeated execution reproduced identical JSON.

No additional model calls or paid inference were required.
