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
  `eval/results/`. Khoa's 15 have not been labelled yet.
  **The fresh round (Kevin on #4, 23 November):** Hamad labels all 100 again by hand from a blank
  copy, with the AI-assisted file closed and new notes. That round is blind to the file but not to
  an earlier reading: before it, Hamad had seen the AI first pass (made on 21 November) and the
  AI-assisted file built from it. For it Claude Code set up the blank copy, made the review page
  refuse any file or note carrying the AI-assisted mark, and added keyboard and voice commands
  (the browser's speech recognition turns the reviewer's own spoken answers into the same clicks;
  nothing is filled in), and extended the scoring command: the employer history counts, the
  narrative against the `hospitalized` count, imminent danger cases apart, and a check that only
  complete hand labels with no AI-assisted mark are written to `eval/results/`. The AI first pass
  is then compared with the fresh labels as agreement only, in `eval/provisional/`. No model call
  went through the app for any of this; nothing was paid.

## The safety talk translations

The Spanish, Chinese, Tagalog, Vietnamese and Arabic texts of the four safety talks were drafted
with an AI assistant. No team member is a native speaker of all five, so each needs a native
speaker's review before a plant prints it; the README says so beside the feature.

## The product's own use of models

* At run time the crew calls up to four models (Claude Sonnet 5.5, GPT 5 nano, Gemini 3.5 Flash,
  Gemma 4 E4B on LM Studio) through a router; without keys every step answers from fixed rules
  (`src/safereport/offline.py`), which are never reported as model results.
* Employer names, addresses and names of people are replaced by placeholders before any text goes
  to a cloud model.
* Paid experiments are capped at the team's budget of $1.50 and every reply is cached
  (`outputs/model_cache.sqlite`, not committed); `safereport eval-live` records what was spent.
