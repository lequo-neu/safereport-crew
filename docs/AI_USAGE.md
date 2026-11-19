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

## The product's own use of models

* At run time the crew calls up to four models (Claude Sonnet 5.5, GPT 5 nano, Gemini 3.5 Flash,
  Gemma 4 E4B on LM Studio) through a router; without keys every step answers from fixed rules
  (`src/safereport/offline.py`), which are never reported as model results.
* Employer names, addresses and names of people are replaced by placeholders before any text goes
  to a cloud model.
* Paid experiments are capped at the team's budget of $1.50 and every reply is cached
  (`outputs/model_cache.sqlite`, not committed); `safereport eval-live` records what was spent.
