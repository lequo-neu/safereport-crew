# Falls program: staffing agencies doing construction work (issue #30)

Advance stage, Hamad. Found in B3 (case K083): a temporary worker fell more than 25 feet, and the
employer is coded NAICS 561320 (temporary help), so the Falls rule, which read construction as
NAICS 23, did not fire.

## What the directive says

CPL 03-00-025 (effective 1 May 2023), read from the PDF on osha.gov on 23 November 2026:

* I: the program is for "falls while working at heights in all industries".
* II.A: "All construction inspections related to falls will be conducted pursuant to this NEP."
* II.B: outside construction, ten listed activities (roof top work, utility lines, tree trimming,
  holiday lights, road signs and billboards, power washing, gutters, chimneys, windows, towers).
* II.C: other work at height outside construction needs area office approval.

The directive never names a NAICS code. Construction is the work being done; OSHA defines it as
"work for construction, alteration, and/or repair, including painting and decorating"
(29 CFR 1910.12(b)). A staffing agency's code says nothing about the work its workers do.

## The rule

Only the Falls entry in `data/reference/emphasis_programs.toml` changes, with a third route next
to the two it had (`Document.match` in `src/safereport/retrieval.py`):

| Route | When | Unchanged? |
|---|---|---|
| anywhere | one of the ten listed activities, any industry | yes |
| industry | NAICS 23 and a fall from height (`fell ... from/off`, `fall to lower level`, `fell ... N feet`) | yes |
| **work** (new) | NAICS 5613 **and** the narrative names construction work **and** an industry fall trigger matches **and** no exclusion matches | new |

* **Construction work** (`work_evidence`): words for work that is plainly construction,
  alteration or repair of a structure: "under construction", "construction site/project/crew",
  "new/residential/commercial construction", scaffold, roofing and shingles, framing and
  sheathing, hanging or installing drywall, siding, insulation, trusses or joists, structural
  steel, rebar, concrete forms, masonry and brick laying, demolition, renovation, remodeling,
  excavation and trenches.
* **Left out on purpose**, because they are as often maintenance as construction: painting,
  installing lights or fixtures, HVAC and duct work, "job site" alone, the bare word
  "construction" (which also appears as "construction materials" or a company name), and the
  employer's name.
* **Exclusions** (`work_exclusions`): OSHA's event title says the worker was struck by a
  falling object, or the narrative says something fell onto the worker. Either means the thing
  fell, not the worker.
* **Evidence.** A report that qualifies this way shows the evidence beside its Category 1
  criterion, for example `CPL 03-00-025: NAICS 561320 employer doing construction work:
  "scaffold"; "fell approximately 18 feet"`. Other programs and routes show the citation alone,
  as before.
* **Scope.** No other program has a work route, and no other industry is affected (tested,
  and measured on the reports below).
* **Old indexes.** A program's rule fields are read from `data/reference` when an index loads
  (`with_current_rules`), so an index built before this change gets the new route without a
  rebuild. Search text and embeddings still come from the index.

## Independent evaluation

`python -I scripts/eval_staffing_falls.py` writes `eval/results/staffing_falls.json` and
`eval/results/staffing_falls_added.csv`. The data is every Severe Injury Report outside the 2025
holdout (the B3 sample sits inside the holdout; the script refuses to run if any B3 report is
outside it). The query is the narrative and OSHA's event title, as in stage 1 of the weekly list.

* **Development, 2015 to 2019.** These reports were read while the construction words were written.
* **Test, 2020 to 2025 (outside the holdout).** Run once, after the rule was fixed.

| | Development 2015 to 2019 | Test 2020 to 2025 | All |
|---|---|---|---|
| Reports | 52,579 | 52,417 | 104,996 |
| Flagged by Falls, old rule | 3,614 | 3,902 | 7,516 |
| Flagged by Falls, new rule | 3,627 | 3,909 | 7,536 |
| **Added** | **13** | **7** | **20** |
| Removed | 0 | 0 | 0 |
| Changed outside NAICS 5613 | 0 | 0 | 0 |
| Staffing (5613) reports | 673 | 447 | 1,120 |
| ... with fall to a lower level wording | 133 | 72 | 205 |
| ... flagged, old → new | 5 → 18 | 2 → 9 | 7 → 27 |
| Construction words and a fall, vetoed as a falling object | 1 | 1 | 2 |

* **What is added.** On the test slice, 7 of 447 staffing reports (1.6%), 4 under 561320 and 3
  under 561311. Five came in through "scaffold", one through "demolition" and one through
  "trench". Every other Falls decision is identical, old against new, on all 104,996 reports.
* **OSHA inspected** 4 of the 7 added test reports (57%, 95% interval 25 to 84). It inspected 10
  of the 64 staffing fall reports the rule still leaves out (16%, 9 to 26), and 47% of the
  construction (NAICS 23) reports the Falls rule flags (1,719 of 3,647). On all 20 added reports
  the rate is 10 of 20 (50%, 30 to 70). That is closer to the construction rate than to the
  other staffing falls. It is past practice, not truth, and 7 reports are few.
* **The two vetoes were right.** Both were "struck by falling object" reports where a plank or a
  beam fell (2019054533, 2020054295).
* **Examples (test slice), from `staffing_falls_added.csv`:**
  * 2023109382: bracing a foundation wall, fell head first into a 9 foot deep trench. Plainly
    construction.
  * 2025076516: installing wood backing in an elevator shaft from the drywall crew's baker
    scaffold, fell into the shaft. Plainly construction.
  * 20241211812: two temporary workers fell 14 to 15 feet when a steel scaffold collapsed. The
    work is not named.
  * 2024032445: removing oxidation with a torch from scaffolding, fell off. This may be
    maintenance, not construction.
* **False positive concerns.** "Scaffold" brought in 5 of the 7 test additions (8 of 20 in
  all), and it is the weakest word: scaffolds are also used for maintenance and cleaning
  (2024032445), and one report names no work at all (2022109105, stepping off a scaffold 3 feet
  up). The development slice has a borderline case of another kind: 2015107889, sweeping a
  loading dock at a building under construction, a 4 foot fall. These
  observations came from Claude Code reading the 20 narratives before any label; the hand
  labels below replace them. The scaffold pattern was not changed after the test run or after
  the labels. Narrowing it is a decision for the team, and it should be measured on new reports.
* **Not adopted, measured:** the employer's name ("... Contracting", "Construct Corps") would
  have added 3 development reports and no test report.

## Hand labels of the 20 added reports (issue #37)

Hamad labelled each added report by hand, from the narrative and OSHA's event fields only (the
rule's matched words, OSHA's inspection flag and any AI reading were kept out of the workbook):
was the worker doing construction work, and did the worker fall to a lower level? Answers are
yes, no or cannot_tell, with a confidence and a reason. The labels are in
`data/labels/staffing_falls_added_Hamad.csv` and, beside each report, in
`eval/results/staffing_falls_added.csv`; `python -I scripts/score_staffing_falls_labels.py`
writes the precision to `hand_labels` in `eval/results/staffing_falls.json`.

cannot_tell is neither right nor wrong, so precision is given three ways. The headline is the
strict one, which counts cannot_tell as not confirmed.

| | Development 2015 to 2019 | Test 2020 to 2025 |
|---|---|---|
| Added reports labelled | 13 | 7 |
| yes / no / cannot_tell | 12 / 1 / 0 | 4 / 1 / 2 |
| **Precision, strict** (yes of all) | 12 of 13, 92% (67 to 99) | **4 of 7, 57% (25 to 84)** |
| Precision, decided (yes of yes + no) | 12 of 13, 92% (67 to 99) | 4 of 5, 80% (38 to 96) |
| Precision, lenient (yes + cannot_tell of all) | 12 of 13, 92% (67 to 99) | 6 of 7, 86% (49 to 97) |

Ranges are 95% Wilson intervals. The development figure is optimistic: those reports were read
while the construction words were written. The test figure is the measure of the rule.

* **Not yes, test:** 2024032445 no (torch work on metal from scaffolding, shop work, not
  construction); 2022109105 and 20241211812 cannot_tell (a fall from a scaffold, 3 feet and
  14 to 15 feet, but the task is not named). These are the two doubtful reports named in #36 and
  the collapsed scaffold among the examples above.
* **Not yes, development:** 2015107889 no (sweeping a loading dock floor at a building under
  construction: cleaning, not construction).
* **By evidence word:** all 3 test reports not labelled yes came in through "scaffold", which
  added 5 of the 7 test reports; 2 of those 5 are yes. Every test addition through another word
  (demolition, trench) is yes, and so are the 3 development additions through "scaffold". The
  pattern was not changed after the labels; a narrower one is a later change, measured on
  reports not used here.
* **One labeller.** The labels are Hamad's alone, with no second reader, so labeller agreement
  is not known; the two cannot_tell answers are low confidence and another reader could decide
  them either way, which is what the strict to lenient range shows.

## Limits

* Precision rests on 7 test reports, so the interval is wide (25 to 84 strict), and on one
  labeller. Recall is not measured: the labels cover only what the rule adds, not the staffing
  fall reports it leaves out. The OSHA inspection rate is past practice, not truth.
* A pasted narrative has no OSHA event title, so the falling-object veto there rests on the
  narrative alone.
* Words, not understanding. A narrative that names construction work only in other words
  ("installing metal panels on a residential roof", "a new medical center construction") is
  missed, and a staffing report that mentions a scaffold or a trench in passing is caught.
  "A worker fell onto the employee below" is vetoed as if a thing had fallen.
* K083 (B3) is not caught by this rule: its narrative names a piping system and a hole, not
  construction work, and the employer's name was rejected as evidence. The rule was not tuned
  to it, and the B3 results (`eval/results/category1_check.json`) are the Basic stage rule and
  are not rerun here. Rerunning `scripts/score_category1_check.py` now would use the new rule.
  The same holds for the B2 inspection AUC, whose holdout has 7 staffing reports.
