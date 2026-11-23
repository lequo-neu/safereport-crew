# B5 — Standards, data and Writer review

**Reviewer:** Khoa Tran (`@trankhoa0210`)
**Review date:** 22 November 2026
**Status:** Case-level review complete for the offline evidence available; configuration reconciliation and GUI confirmation are still open. This is an inspection-support QA review, not a finding that an employer violated an OSHA regulation.

## What I checked and how

I started with `docs/LABELING_GUIDE.md`: identify the activity and injury mechanism, choose the most specific applicable standard, and do not turn an ambiguous narrative into a confident violation. I compared that logic with `src/safereport/domain.py`, `graph.py`, and `retrieval.py`. I then reviewed the offline checkpoint evidence for the Texas week, 20 construction narratives, one generated RRI letter, and the four Vietnamese talks. The case-level decisions and source narratives are in the accompanying `khoa_` CSV files.

**Evidence-view limitation:** I reconstructed decisions from saved LangGraph checkpoint history, not a fresh manual opening of every case in the Gradio Evidence view. Kevin should not treat this as a completed UI acceptance check until the 12 corrections and 4 human-review cases have been compared in the exact team configuration.

## Baseline reproduction and testing

I previously ran `.venv/bin/safereport eval-baselines` and compared the principal metrics with `eval/results/phase1_baselines.json`. On 1,000 holdout reports, full OIICS-code accuracy was **59.6%**, group accuracy **78.7%**, and division accuracy **90.7%**. The strict standards Hit@3 for the saved hybrid narrative-plus-code baseline was **41.2% on 51 labeled cases**. These are baseline/retrieval metrics, not final citation correctness. The original 324 tests passed before B5 edits; my local audit log later recorded **326 passed** with Ruff clean. The PR should be judged on a new offline test run on the receiving clone.

For the B5 case review counts, the reproducible source is `eval/results/khoa_b5_review_counts.json`, generated from the two committed case tables by `python scripts/khoa_b5_review_counts.py`. My raw offline checkpoint and test logs are retained in my local evidence archive rather than committed to the repository.

## Texas week — 15 cases checked

The offline BM25 run covered **31 reports** (17–23 November 2025). I found **11 reports with changed citations** and **4 reports sent to a person**, forming 15 distinct cases. Kevin’s team plan says 12 corrections; I did not change the count to match. We need to rerun the same retrieval configuration, index availability and revision, and agree whether “corrections” means distinct reports or individual issues.

| OSHA report | First pick → final pick | My assessment |
|---|---|---|
| `20251111432` | `1910.218` → `1910.147` + `1910.218` | **Needs follow-up.** Cleaning hydraulic chain tongs: hazardous energy plausible, but NAICS 237110 suggests construction; 1910.147 expressly excludes construction employment. Retained 1910.218 is forging-specific, unsupported by narrative. Confirm activity/jurisdiction and mechanism. |
| `20251111436` | `1910.28` → `1910.28` | **Likely incorrect final citation.** Rope pulled around capstan caused finger pinch, not a worker fall. 1910.28 lacks established relevance here; machine nip-point/energization controls and construction rules need investigation. RRI letter inherits the weak citation. |
| `20251111439` | `1910.28` → `1910.22` | **Plausible correction.** Tripped on mat and fell at same level. 1910.22 walking-working surfaces more relevant than fall-to-lower-level 1910.28; verify specific paragraph and floor-mat facts. |
| `20251111443` | `1910.28` → `1910.28` | **Human warning oversimplified.** Metal scale fell from raised crane load onto foot. Worker did not fall, but 1910.28(c) addresses falling-object protection; cannot reject 1910.28 solely because worker did not fall. Confirm precise standard/coverage and appropriate crane rules. |
| `20251111449` | `1910.28` → `1910.28` | **Likely false-positive human warning.** Worker jumped from trailer and fell to ground; the event is a fall. Need distinguish deliberate jump, exposure and applicable 1910 fall protection, not automatically reject for vehicle source. |
| `20251111462` | `1910.218` → `1910.147` + `1910.218` | **Needs follow-up.** Die setup on 45-ton punch press and inadvertent actuation: energy isolation is plausible, but 1910.218 refers to forging machines and is not substantiated by the punch-press narrative. Check whether 1910.217 applies to this power press, plus 1910.147. |
| `20251111502` | `1910.262` → `1910.147` + `1910.262` | **Needs follow-up.** Cleaning roller machine supports 1910.147 investigation; preserved 1910.262 (textile industry) is unsupported for a tubing-services employer. Check machinery type and coverage. |
| `20251111522` | `1910.266` → `1910.147` + `1910.266` | **Needs follow-up.** Clearing machine clog supports hazardous-energy investigation; preserved 1910.266 governs logging, not established for a textile employer. Verify appropriate guarding standard. |
| `20251111525` | `1910.28` → `1910.28` | **Needs follow-up.** Steel beam slipped from powered truck forks, striking hand. Worker did not fall; 1910.28(c) may be relevant only if its falling-object conditions are met, but material handling and powered-industrial-truck requirements require assessment. |
| `20251111583` | `1910.28` → `1910.22` | **Plausible correction.** Worker slipped and fell inside railcar; if same-level, 1910.22 is plausible. Check whether there was an elevation change. |
| `20251111604` | `1910.28` → `1910.22` | **Plausible correction.** Worker tripped over box and fell to floor; 1910.22 same-level walking-working surfaces is plausible. |
| `20251111606` | `1910.219` → `1910.147` + `1910.219` | **Plausible with qualifications.** Removing belt while servicing pulley creates hazardous-energy/nip-point concern; 1910.147 primary and 1910.219 secondary plausible if general-industry application holds. |
| `20251111613` | `1910.178` → `OSH Act 5(a)(1)` | **Needs follow-up.** Valet truck rolled backward and injured employee. Removing powered-industrial-truck 1910.178 is sound; General Duty Clause is not automatically proven by narrative. Determine feasible specific control and recognized-hazard evidence. |
| `20251111619` | `1910.28` → `1910.23` | **Plausible correction.** Worker missed ladder step and fell. 1910.23 ladder standard is a more relevant candidate than 1910.28, which excludes portable ladders from its scope. Verify ladder type. |
| `20251111622` | `1910.217` → `1910.212(a)(3)(ii)` | **Needs follow-up.** Bale press/bagger unexpectedly started during bale removal. 1910.217 mechanical press is not proven; replacement 1910.212(a)(3)(ii) may be too specific without point-of-operation evidence. Evaluate servicing and unexpected startup under 1910.147 where applicable. |

**What this exposed:** The Critic can recognize a hazardous-energy activity and still carry an unrelated old primary into the secondary field. Examples in the table include `1910.218` (forging machines), `1910.262` (textiles) and `1910.266` (logging). A citation being syntactically valid is not evidence that its scope matches this incident. I also found that the fall-only warning is too coarse: §1910.28 contains falling-object provisions in paragraph (c). A person not falling is not, by itself, enough to rule out §1910.28.

**Code change tested:** On incident `20251111554`, a pallet-wrapping machine injured a worker at a chain and sprocket. The original guard only caught an invalid `1910.217` citation when it was the *primary*. My change checks both cited columns and removes an invalid press-only *secondary* without discarding an otherwise valid primary. I added a domain-level regression test and a graph-level regression test. This fixes that specific failure, **not** the more general problem of keeping unrelated secondary standards after an energy-control revision.

**Another workflow discrepancy:** `20251111445` had `1910.180` in the selective run and `1910.179` when every report entered Stage 2. The worker reportedly fell from a truck-mounted crane. Neither difference proves an OSHA violation or establishes the correct fall rule. Equipment type, activity and the relevant Part 1910/1926 scope still need checking.

### Team configuration and B4 regression reconciliation

Kevin reproduced the Texas week with the team's hybrid retrieval configuration and confirmed 12 corrected reports and 4 human-review cases. My earlier BM25-only reconstruction identified 11 changed reports and 4 human-review cases. The difference comes from retrieval configuration rather than an unexplained counting error. BM25-only and hybrid runs do not select exactly the same reports: 20251111432 and 20251111436 appeared only in the BM25 review, while 20251111554, 20251111445 and 20251111512 appeared only in the hybrid comparison. All case-level conclusions remain conditional on the actual injury mechanism and applicable OSHA standard.

For the construction filter, my earlier review reconstructed 32 exclusions, while the later full 2015–2025 construction replay found 33. The older count should remain labeled as a different reconstruction, not presented as the current team result. The four potential worker-fall exclusions still warrant regression tests and are tracked in GitHub issue #29 for the Advance stage.

I reran `python -I scripts/eval_batch_savings.py` after the B5 critic change. For report 20251111462, involving die setup on a 45-ton punch press, both evaluation paths now select 1910.147 rather than 1910.212(a)(3)(ii). This is consistent with investigating hazardous-energy control during servicing; it is not a determination of an OSHA violation.

The rerun retained 56 versus 78 model calls, a saving of 22 calls (28.2%). No inspection decisions, Category 1 classifications or priority scores changed. The one remaining between-path citation difference is report 20251111512 (1910.212 versus 1910.243). The regenerated `eval/results/batch_savings.json` includes the updated result and minor token-estimation differences.

An unresolved critic limitation remains: `mechanical_press_only` can receive only the generic machine description "press" from Intake and incorrectly reject 1910.217 even for a genuine punch press. This requires a separate issue and regression test; the current B5 correction does not fully resolve it.

## Construction `FALLING_THING` filter — 20 excluded narratives

I read 20 excluded construction reports against the precise intended exclusion: **an object falls onto a worker**, not merely a sentence containing the word “fell.” The reviewed CSV records both whether an object struck the worker and whether the worker fell.

- **16** described an object striking/pinning the worker without an explicitly described worker fall.
- **1** (`2016064867`) described **both** a worker falling from a step ladder and an object striking the worker; excluding it entirely from Falls loses a genuine worker-fall case.
- **3** (`2017076368`, `2019010486`, `2019065999`) described worker falls without a supported object-on-worker injury. These should not be excluded solely by the falling-object filter.

Thus **17/20** contain an object-on-worker event, but **four cases require a Falls-program retention check** (three worker-only falls plus one mixed event). This is a purposive check of 20 selected narratives, not an estimated overall error rate. My helper reconstructed **32 exclusions**, whereas the plan records **33**; the count mismatch is a version/query/filter question, not a confirmed repository bug.

**Suggested fix for a separate issue:** Preserve fall events when `worker_fell` is true, even when `object_fell_onto_worker` is also true. Add regression tests for these four report narratives before changing `retrieval.py`. I have not changed the shared filter in B5.

## RRI Writer — inspected draft

The inspected letter concerns report `20251111436` (C.A. Senecal Electric Services, 17 November 2025), where a finger was trapped between rope and capstan. The draft calls for an internal investigation, root cause, corrective action/abatement proof and a certificate of posting. Those are the substantive RRI elements expected by OSHA’s 4 March 2016 memo.

**Hold the letter as written:** The draft cites `1910.28`, although the recorded hazard is a capstan nip point, not an established fall exposure. It also says “within five working days of this letter,” whereas OSHA’s memo describes five working days **after the initiating RRI call** for the investigation and abatement verification. The call date was not in the evidence, so no definite reply-by date can be validated. I would add a specific question about guarding, unexpected movement and safe rope-handling procedures, and avoid naming a paragraph until applicability is verified.

## Vietnamese safety talks — native-language wording

I reviewed all four Vietnamese talk topics in `src/safereport/talk_languages.py`: lockout, machine guarding, falls and forklift. I also opened a generated lockout Word document and checked the visible diacritics and text layout; the other three Word files have not received a separate visual sign-off.

Issues in the original wording were practical rather than cosmetic. `Mép nào cũng có thể ngã` makes the edge itself the thing falling. Telling a pedestrian merely to “look the forklift driver in the eye” does not confirm that the driver will stop. The lockout paragraph should mention isolation of **stored energy**, not only an attempted start. The new `vi` copy fixes those three points and improves machinery guarding language, while leaving the other languages and `{{topic_reports}}` / `{{since}}` placeholders unchanged. It still needs a final read in the newly rendered Word output after merging.

The four opening counts seen in the exported talks (**5,289; 8,752; 7,544; 2,182**) have not been independently reconciled to a cohort, date range and event definition here. I am not treating them as checked statistics. The underlying lead text continues to use dynamic placeholders, not hard-coded counts.

## Kevin’s additional B4 case — `20251111512`

Kevin asked why a powered miter saw thumb amputation during trim cutting (NAICS 321991) receives **`1910.212` after Stage 1** and **`1910.243` on the model branch**. My provisional choice **between those two** is `1910.212`: it generally covers guarding of power saws, while `1910.243` focuses on portable powered tools and its circular-saw rule describes guarding above/below a base plate or shoe. A typical bench-mounted miter saw should not be treated as a hand-held circular saw merely because it is movable. The more specific woodworking machinery standard **`1910.213` should also be checked**, because our label guide favors a specific machine standard when its scope fits. The incident narrative alone does not specify the model, mounting, guard design or guard defect. Accordingly I cannot certify an exact violation or paragraph. My separate BM25 result for this case picked `1910.266` (logging), which needs a retrieval-quality check against Hamad’s B4 configuration; it does not change Kevin’s Stage 1 vs model-branch comparison.

## Findings for Kevin to prioritize

1. **Corrected in this B5 branch:** Unsupported `1910.217` secondary on a non-press machine; domain and LangGraph regression tests.
2. **Separate issue needed:** Four construction Falls records appear to be over-excluded (`FALLING_THING`), including one mixed injury mechanism.
3. **Separate issue needed:** Fall-family validation conflates fall hazards and falling-object provisions, producing misleading human warnings.
4. **Separate issue needed:** Energy-control revision can retain unrelated industry-specific secondary citations.
5. **Separate issue needed:** The sample RRI letter inherits an unsupported hazard citation and may anchor the reply deadline to the wrong event.
6. **Verify, not declare defective:** 11 vs 12 Texas corrections, 32 vs 33 construction exclusions, and Stage 1 vs model-branch differences on `20251111512`.

## Remaining B5 acceptance checks

Before Kevin merges: run full Ruff and pytest offline, confirm the baseline JSON and issue counts with the same configuration as `main`, open the Evidence view for the agreed cases, regenerate one Vietnamese Word file from the edited source and inspect it, and open one GitHub issue per confirmed defect (checking for duplicates first). No change is proposed to shared triage weights, the README, the proposal, or B4 evaluation results.

## Sources

- `docs/TEAM_PLAN.md`; `CONTRIBUTING.md`; `docs/LABELING_GUIDE.md` and the two `khoa_` case tables committed with this review.
- `eval/results/phase1_baselines.json` and `eval/results/khoa_b5_review_counts.json` (from `python scripts/khoa_b5_review_counts.py`).
- OSHA machine guarding: https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.212
- OSHA woodworking machinery: https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.213
- OSHA portable powered tools: https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.243
- OSHA falling-object provisions: https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.28
- OSHA hazardous energy (scope and exclusions): https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.147
- OSHA RRI procedures, 4 March 2016, Section VI(B): https://www.osha.gov/memos/2016-03-04/revised-interim-enforcement-procedures-reporting-requirements-under-29-cfr-190439
