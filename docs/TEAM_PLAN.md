# Team plan: from phase 3 to submission

Seven Team-5374. Written on 20 November 2026. How we work is in [CONTRIBUTING.md](../CONTRIBUTING.md).

> **This plan is a floor, not a ceiling.** We encourage every member to contribute beyond it
> whenever you see a way to make the project better: a sharper test, a clearer page, a feature a
> user would miss. Open an issue or a pull request and tell the team; good ideas are welcome from
> anyone, at any stage.

| Who | GitHub | Role from now on |
|---|---|---|
| Hamad Al Sulaimi | `hmdsulaimi` | builds and measures (triage, evaluation), folds the results into the shared documents, shares the submission work with Khoa |
| Khoa Tran | `trankhoa0210` | builds and measures (standards, routing), shares the submission work with Hamad |
| Quoc Hung Le (Kevin) | `lequo-neu` | reviews and merges every pull request, owns the repository settings and tags the submitted commit |

The work is split evenly between Hamad and Khoa. Kevin reviews and merges and takes no task from
this list, so nobody waits on him for anything but a review. From 24 November the fold in of the
results (#19) is Hamad's, by pull request.

The safety talk translations get a native speaker's review, as the README and proposal promise:
Hamad reads the Arabic (in B1) and Khoa the Vietnamese (in B5).

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
CONTRIBUTING.md. Each task has its own GitHub issue, named by its code (issues #2 to #14).

**Shared dates inside the stage.** B3 and B7 depend on each other: each needs 15 cases checked by
the other person.

| When | What |
|---|---|
| 22 November, noon | Hamad sends Khoa the 15 cases of B3 to check; Khoa sends Hamad the 15 cases of B7 |
| 23 November, noon | each returns the 15 checked cases |
| 23 November, night | every Basic pull request is merged |

**Results go in their own files, not in the README.** B2, B3, B4, B6 and B7 each write only their
own file in `eval/results/` (and `data/labels/`). The pull request description gives the sentence
or table row the README should show. When the last Basic pull request is merged, Hamad updates
`README.md`, `docs/PROPOSAL.md` and `docs/OPEN_ISSUES.md` from those files in one pass, so five
pull requests never edit the same table.

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
* Native speaker review of the Arabic safety talks (`ar` in `src/safereport/talk_languages.py`):
  read all four topics, and open one Word file to check that it reads right to left. The README
  and the proposal promise this review before a plant uses a translation.
* Outputs: `docs/reviews/hamad.md` with what you checked and what you found, the corrected Arabic
  text in a pull request if anything is wrong; one issue per defect.

**B2. Inspection priority against OSHA's own choices.**
* ROC AUC of the priority score against whether OSHA inspected, on the 2025 reports, beside the
  baseline "severity alone". Say in the result that past practice is a reference, not the truth.
* Outputs: a command (for example `safereport eval-priority`), `eval/results/inspection_auc.json`
  with the AUC and its 95% interval, a test on the small file, the README row in the PR description.

**B3. Hand check of the Category 1 rules on 100 reports.**
* Draw 100 reports from the 2025 holdout (a seed in the script), mark for each whether it meets
  a Category 1 criterion and which one, following `docs/LABELING_GUIDE.md`. Khoa checks 15 of them.
* Outputs: `data/labels/category1_check.csv`, a scoring command, recall and false alarms with 95%
  intervals in `eval/results/`, the agreement on the 15 shared cases, the README row in the PR
  description. The 15 cases go to Khoa by 22 November at noon.

**B4. What the two stage batch saves.**
* Run the Texas week with every report through stage 2 and with the two stages, offline. Count
  the model calls, the estimated cost and the decisions that change.
* Outputs: a command, `eval/results/batch_savings.json`, the README row in the PR description.

### Khoa

**B5. Review the data, the standards and the Writer.**
* Reproduce `safereport eval-baselines` and compare with `eval/results/phase1_baselines.json`.
* Check the 12 standards the critic corrects in the Texas week, and the 4 left for a person, in
  the Evidence view against `docs/LABELING_GUIDE.md`.
* Read 20 of the 33 construction reports the new falling object filter (`retrieval.py`,
  `FALLING_THING`) takes out of the Falls program: each must be an object falling on a worker.
* Check an RRI letter against OSHA's practice (five working days, root cause, abatement
  verification, posting certificate).
* Native speaker review of the Vietnamese safety talks (`vi` in `src/safereport/talk_languages.py`):
  read all four topics and open one Word file. Kevin can give a second reading on request.
* Outputs: `docs/reviews/khoa.md` with what you checked and what you found, the corrected
  Vietnamese text in a pull request if anything is wrong; one issue per defect.

**B6. Seeded errors for the domain checks.**
* Copy the answer key with wrong citations put in on purpose (a guarding section for a jam, a
  press section outside presses, a forklift section for a car, an invented section; at least 20).
* Outputs: `data/labels/seeded_errors.csv`, a scoring command, errors caught and correct labels
  wrongly rejected in `eval/results/seeded_checks.json`, the README row in the PR description.

**B7. Router accuracies measured outside the answer key.**
* Label the standard for 50 reports of the 2025 holdout that are not in the key, following the
  labelling guide. Hamad checks 15 of them; send them by 22 November at noon.
* Run each model once on them with `--live` (Khoa is the only person who runs paid calls in this
  stage; stay inside the cap) and give the router these accuracies in place of its priors.
* If Gemini 3.5 Flash fails again with 503 or 429 errors, as it did on 19 November: retry it once,
  only if the budget left allows. If it still fails, record it as unavailable (date and error) in
  the result file, keep its prior in `config/models.toml` marked "not measured", and update the
  measured values for Claude and GPT 5 nano only.
* Outputs: `data/labels/router_slice.csv`, `eval/results/router_slice.json`, the measured values
  in `config/models.toml` with their source, the agreement on the 15 shared cases, the money spent,
  the README row in the PR description.

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

All four tasks belong to Hamad and Khoa together. You split them between you as you see fit, and
write who does which part in each issue by 26 November at noon, so nothing is done twice or
left out.

**S1. The report.** Problem, users and needs, data and answer key, architecture, triage logic,
evaluation with every number taken from `eval/results/`, limits, AI use. PDF in `docs/report/`.

**S2. The slides and the demo script.** 8 to 12 slides and a live demo script that follows the
README tour, with a backup run recorded offline in case the network fails on the day.

**S3. The video.** The demo, each part shown by the person who built it, put together in one video.

**S4. The submission.** Everything handed in, in the form the course asks for (check Canvas):
* a fresh clone of `main` passes the README quick start and `pytest -q`;
* Kevin tags the submitted commit (for example `v1.0.0`) when you ask him, so the code handed in
  is the code we tested;
* the report, the slides, the video link and the repository link are submitted, and a screenshot
  or the confirmation of each submission is attached to the issue.

Kevin reviews S1 to S3 before 28 November at night and checks S4 with you.

## If time runs short

We cut in this order: the advance features, then B8's parallel call cap. B2, B3, B6 and B7 stay:
they are the evidence that the project goes beyond the baseline.
