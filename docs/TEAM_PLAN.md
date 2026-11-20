# Team plan: from phase 3 to submission

Seven Team-5374. Written on 20 November 2026. How we work is in [CONTRIBUTING.md](../CONTRIBUTING.md).

| Who | GitHub | Role from now on |
|---|---|---|
| Hamad Al Sulaimi | `hmdsulaimi` | builds and measures (triage, evaluation), writes the report |
| Khoa Tran | `trankhoa0210` | builds and measures (standards, routing), makes the slides and the demo script |
| Quoc Hung Le (Kevin) | `lequo-neu` | reviews every pull request when asked, owns the repository settings |

The work is split evenly between Hamad and Khoa. Kevin reviews and merges; he does not take tasks
from this list, so nobody waits on him for anything but a review.

## Where we start

Phases 0 to 3 are built, tested and on `main` (see the [README](../README.md)):

* Seven agents on LangGraph, a Gradio app with a page per role, four models behind a router with
  fallback and a free local mode (Gemma 4 E4B on LM Studio). Without `--live` nothing is paid.
* 307 tests pass offline, with no data and no API key.
* Measured on the answer key: the right section in the top 3 rises from 41.2% (no model) to 60.8%
  with GPT 5 nano terms and 70.6% with Claude terms; the experiment cost $0.14 of the $1.50 cap.
* The Texas week (17 to 23 November 2025): 31 reports, 8 Category 1, 20 inspections and 11 RRI
  letters for 40 inspector days; 20 reports take a model branch; the critic corrects 12 standards.
* Two review rounds on 19 and 20 November fixed the Ask page type, the Director's moves, the
  approval summary, inspector day checks, the critic's redrafts, the employer matches panel, the
  Falls emphasis trigger and the safety talk counts.

## Timeline

| Stage | Dates | Goal |
|---|---|---|
| Basic | 20 to 23 November | review what exists in your area, and finish the evaluation the proposal promised |
| Advance | 24 to 25 November | the team picks advanced features, builds and tests them, shows them, merges them |
| Submission | 26 to 28 November | video, report and presentation ready to submit |

The course deadlines come later (check Canvas), so the days after 28 November are a buffer, not a plan.

## Basic stage: 20 to 23 November

Every task ends in a pull request that meets its outputs below and the definition of done in
CONTRIBUTING.md. Each task has its own GitHub issue, named by its code (issues #2 to #13).

### Hamad

**B1. Review the triage logic and the app.**
* Open each of the 8 Category 1 reports of the Texas week in the case inspector and check its
  trigger against [OSHA's 2016 memo](https://www.osha.gov/memos/2016-03-04/revised-interim-enforcement-procedures-reporting-requirements-under-29-cfr-190439).
  Check 20251111409 (dirt and rock fell on a worker), which is now Category 2.
* Agree with Khoa on the weights and inspector days in `config/triage.toml` and write the reason
  for each next to it.
* Walk the README tour with all four roles on a laptop and at phone width. Try every move of the
  Director: a row to inspection and back, a note cleared, a rule removed, an imminent danger flag
  set and removed, Approve with open employer matches.
* Outputs: `docs/reviews/hamad.md` with what you checked and what you found; one issue per defect.

**B2. Inspection priority against OSHA's own choices.**
* ROC AUC of the priority score against whether OSHA inspected, on the 2025 reports, beside the
  baseline "severity alone". Say in the result that past practice is a reference, not the truth.
* Outputs: a command (for example `safereport eval-priority`), `eval/results/inspection_auc.json`
  with the AUC and its 95% interval, a test on the small file, a row in the README results.

**B3. Hand check of the Category 1 rules on 100 reports.**
* Draw 100 reports from the 2025 holdout (a seed in the script), mark for each whether it meets
  a Category 1 criterion and which one, following `docs/LABELING_GUIDE.md`. Khoa checks 15 of them.
* Outputs: `data/labels/category1_check.csv`, a scoring command, recall and false alarms with 95%
  intervals in `eval/results/`, the agreement on the 15 shared cases, a row in the README results.

**B4. What the two stage batch saves.**
* Run the Texas week with every report through stage 2 and with the two stages, offline. Count
  the model calls, the estimated cost and the decisions that change.
* Outputs: a command, `eval/results/batch_savings.json`, a row in the README results.

### Khoa

**B5. Review the data, the standards and the Writer.**
* Reproduce `safereport eval-baselines` and compare with `eval/results/phase1_baselines.json`.
* Check the 12 standards the critic corrects in the Texas week, and the 4 left for a person, in
  the Evidence view against `docs/LABELING_GUIDE.md`.
* Read 20 of the 33 construction reports the new falling object filter (`retrieval.py`,
  `FALLING_THING`) takes out of the Falls program: each must be an object falling on a worker.
* Check an RRI letter against OSHA's practice (five working days, root cause, abatement
  verification, posting certificate), and the talk translations in any language you read well.
* Outputs: `docs/reviews/khoa.md` with what you checked and what you found; one issue per defect.

**B6. Seeded errors for the domain checks.**
* Copy the answer key with wrong citations put in on purpose (a guarding section for a jam, a
  press section outside presses, a forklift section for a car, an invented section; at least 20).
* Outputs: `data/labels/seeded_errors.csv`, a scoring command, errors caught and correct labels
  wrongly rejected in `eval/results/seeded_checks.json`, a row in the README results.

**B7. Router accuracies measured outside the answer key.**
* Label the standard for 50 reports of the 2025 holdout that are not in the key, following the
  labelling guide. Hamad checks 15 of them.
* Run each model once on them with `--live` (Khoa is the only person who runs paid calls in this
  stage; stay inside the cap) and give the router these accuracies in place of its priors.
* Outputs: `data/labels/router_slice.csv`, `eval/results/router_slice.json`, the measured values
  in `config/models.toml` with their source, the agreement on the 15 shared cases, the money spent.

**B8. The router on the Pareto chart, and a cap on parallel calls.**
* Add the router's own point to the cost against accuracy chart on the Evaluation page.
* Add a cap on parallel calls per provider (set in `config/models.toml`), as the proposal promised.
* Outputs: the chart point with a test, the cap with a test that runs more branches than the cap.

## Advance stage: 24 to 25 November

1. By 24 November at noon, each of us adds at least one feature to the "Advance features" issue:
   what it does, which user need (N1 to N15 in the README) it serves, and how it will be tested.
   Candidates already in the proposal: the prevention plan for a plant (N13), the RRI reply
   review, Part 1926 for construction, recounting repeats inside a run after match answers.
2. We pick the features together in the issue thread, or in a short meeting if someone asks for one.
3. Each feature is built on its own branch with tests, shown to the team (a short video or a call),
   and merged by 25 November at night.

## Submission stage: 26 to 28 November

**Hamad: the report.** Problem, users and needs, data and answer key, architecture, triage logic,
evaluation with every number taken from `eval/results/`, limits, AI use. PDF in `docs/report/`.

**Khoa: the slides and the demo script.** 8 to 12 slides and a live demo script that follows the
README tour, with a backup run recorded offline in case the network fails on the day.

**Both: the video.** Each records the part of the demo they built; Khoa puts it together.

Kevin reviews all three before 28 November at night.

## If time runs short

We cut in this order: the advance features, then B8's parallel call cap. B2, B3, B6 and B7 stay:
they are the evidence that the project goes beyond the baseline.
