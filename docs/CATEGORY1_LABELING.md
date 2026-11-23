# Labeling guide: does a report meet OSHA's Category 1 criteria?

> **Task B3, issue #4.** The labeling rules below are settled: Kevin locked them in on issue #4
> on 21 November 2026 (the seven rules are quoted in "The settled rules"). Each criterion says
> where its rule comes from: **OSHA memo** (the memo's own words) or **Settled** (one of the seven
> rules). `docs/LABELING_GUIDE.md` covers the standards labels; this file covers the Category 1
> hand check only.

We check by hand whether each of 100 reports from the 2025 holdout meets one of OSHA's Category 1
criteria, the reports an area office must inspect. The source is OSHA's memo of 4 March 2016,
[Revised Interim Enforcement Procedures for Reporting Requirements under 29 C.F.R. 1904.39](https://www.osha.gov/memos/2016-03-04/revised-interim-enforcement-procedures-reporting-requirements-under-29-cfr-190439),
section 5, "Category 1". These labels measure the crew's Category 1 rules
(`src/safereport/triage.py`): how many real Category 1 reports they catch (recall) and how many
they flag wrongly (false alarms).

## The settled rules

From Kevin's comment on issue #4, 21 November 2026:

1. **cannot_tell** is allowed. Recall and false alarms are scored only on the cases we can
   decide. The cannot_tell share is reported separately, with its reasons. A cannot_tell case
   counts as neither right nor wrong.
2. **SVEP and repeat offenders**: the SIR file does not link to OSHA's citation records, so this
   criterion is cannot_tell (reason: needs violation history). The gap is noted in
   `docs/reviews/hamad.md`.
3. **Emphasis programs**: label against the national programs only. Local and regional programs
   (LEP, REP) are listed as a gap.
4. **Employer history**: the same rule as the app. An earlier report counts only when the
   employer match is confirmed (the same name, or a match a person accepted). A "possible" match
   is cannot_tell, not yes.
5. **Imminent danger**: cannot_tell unless the text says the hazard is still there. It is
   reported apart from the rules' recall, because the app leaves it to a person's flag.
6. **No tuning on the sample**: the rules are scored as they are on `main` today (commit
   `fd15b06`). If the 100 cases show a rule should change, that goes in a new issue, and a
   changed rule is not re-scored on the same 100.

From Kevin's later comment on issue #4, 21 November 2026:

7. **The hospitalized count**: go by the `hospitalized` field, the one the rules and the app
   read, so the hand check scores the same input the crew sees. When the narrative disagrees,
   write it in `notes` (for example "narrative: 2 hospitalized, count says 1"). The number of such
   cases goes in `docs/reviews/hamad.md` as a data quality note, with the ID of any that would
   change Category 1.

## The files

| File | Who | What |
|---|---|---|
| `data/labels/category1_check.csv` | Hamad | the 100 reports, K001 to K100 |
| `data/labels/category1_check_Khoa.csv` | Khoa | 15 of the same reports (marked `checked_by = Khoa` in the first file), with no labels |

Both come from `scripts/make_category1_sample.py`: a simple random draw from
`data/splits/holdout_2025.csv` with **seed 42**. Running it again on the same OSHA file gives
the same reports in the same order. It refuses to overwrite a file that exists, so a second run
never loses labels.

## How to label

* **Label by hand, on your own.** Do not ask an AI tool for a label. Do not look at the other
  person's labels until both files are done: the 15 shared cases measure how far we agree.
* **Do not look at what the crew or OSHA decided.** The file leaves out the rule output and
  whether OSHA inspected. Do not open a report in the app's case inspector or week list before
  you label it: both show the Category 1 result.
* **Do not open `eval/provisional/` until your labels are done.** It describes an AI-assisted
  first pass; it is compared with the hand labels afterwards, not used to make them.
* **Judge the report as the area office would on the day it arrived**, from the narrative and
  OSHA's fields, not from what happened later.
* **When the file cannot tell you, write `cannot_tell`, and give the reason in `notes`**, as
  `column: reason`, for example `similar_report_within_12_months: possible match, "ABC Roofing"
  vs "A B C Roofing Services"`. Do not guess. The reasons are reported with the results.

## The columns

| Column | Given or yours | What it holds |
|---|---|---|
| `case`, `sir_id`, `event_date`, `employer`, `city`, `state`, `naics` | given | the report |
| `hospitalized`, `amputation`, `loss_of_eye` | given | OSHA's counts |
| `narrative`, `event`, `source`, `nature`, `body_part` | given | the story and OSHA's codes |
| `checked_by` | given (first file only) | `Khoa` on the 15 shared cases |
| `two_or_more_hospitalized` | **yours** | `yes`, `no` or `cannot_tell` |
| `worker_under_18` | **yours** | `yes`, `no` or `cannot_tell` |
| `similar_report_within_12_months` | **yours** | `yes`, `no` or `cannot_tell` |
| `emphasis_program_hazard` | **yours** | `yes`, `no` or `cannot_tell`, national programs only |
| `imminent_danger` | **yours** | `yes` or `cannot_tell` (see criterion 6) |
| `category_one` | **yours** | from the first four criteria: `yes` if any is `yes`; `no` if all four are `no`; else `cannot_tell` |
| `emphasis_program` | yours, when `emphasis_program_hazard` is `yes` | the program's citation, for example `CPL 03-00-027` |
| `evidence` | yours, when any criterion is `yes` | the words or the field that show it; for employer history, the earlier report's ID and date |
| `confidence` | **yours** | `high`, `medium` or `low`, as in `docs/LABELING_GUIDE.md` |
| `notes` | yours; required for every `cannot_tell` | the reason for each `cannot_tell`; "fatality" if the narrative says the worker died; a narrative that disagrees with the `hospitalized` count (rule 7); a possible local or regional program |

`category_one` leaves out imminent danger and repeat offenders: the rules do not decide them
(settled rules 2 and 5), so they are reported apart and do not change `category_one`.

## OSHA's six Category 1 criteria

The memo says an inspection is conducted "if any one of the conditions below is reported", and
lists six. The file has a column for five of them; the fourth cannot be judged from a report.

**1. Fatalities and two or more hospitalized.** *OSHA memo:* "All fatalities and reports of 2 or
more in-patient hospitalizations". *Settled (rule 7):* write `yes` when the `hospitalized`
count is 2 or more, and `no` when it is 0 or 1, whatever the narrative says. When the narrative
disagrees with the count, write it in `notes`, for example "narrative: 2 hospitalized, count
says 1". A death is not a column: write "fatality" in `notes`.

**2. A worker under 18.** *OSHA memo:* "Any injury involving a worker under 18." Write `yes` only
when the narrative gives the injured worker's age as under 18, or calls the worker a minor. A
patient, customer or bystander under 18 is not a worker. OSHA's file has no age field, so
`no` means "nothing in the report says so".

**3. A similar history within 12 months.** *OSHA memo:* "The employer has a history of the same
or similar hazards or incidents within the past 12 months." *Settled (rule 4):* apply the app's
own matching rule (`employers.py`, `history` and `repeats_within`) by hand. Search the OSHA file
`data/raw/January2015toNovember2025.csv` (Excel's filter works), not the app. The file is not
committed: if you do not have it, download "the full SIR data set" in a browser from
https://www.osha.gov/severe-injury-reports (see `data/raw/README.md`).

* **Where and when.** Earlier reports in the **same state**, with `EventDate` in the 365 days
  before this report's `event_date`. The report itself does not count.
* **The name.** Write both names in lower case, turn `&` into "and", drop punctuation, and drop
  the words inc, incorporated, llc, co, corp, corporation, company, ltd, limited, lp, llp, plc,
  the and dba. "Tyson Foods, Inc." becomes "tyson foods".
* **Confirmed**, which can make a `yes`: the two names are then identical, **and** either the
  city is the same, or the first three digits of the NAICS code are the same.
* **Possible**, which is `cannot_tell`: a near spelling ("wal mart" and "walmart"), an acronym
  ("abc" and "american building contractors"), one name inside the other, or the same name in
  another city with a different three digit NAICS. Give the two names in `notes`.
* **Similar**: the earlier report's `Event` code starts with the same digit as this report's
  (4 falls, 6 contact with objects and equipment, and so on). An earlier report with no event
  code counts.

Write `yes` with the earlier report's ID and date in `evidence`; `no` when no confirmed or
possible earlier report is similar; `cannot_tell` when the only candidates are possible matches.
A report by the same employer in another state is not looked for, as in the app.

**4. Repeat offenders.** *OSHA memo:* "Repeat offenders (history of egregious, willful,
failure-to-abate, or repeated citations; and employer on SVEP)." *Settled (rule 2):* this needs
OSHA's citation history and the Severe Violator Enforcement Program list, and the SIR file does
not link to them. It is `cannot_tell` for every report (reason: needs violation history), so
there is no column and nothing to write. If a narrative happens to mention earlier citations,
say so in `notes`.

**5. A hazard under an emphasis program.** *OSHA memo:* "Report of a hazard covered by a local,
regional, or national emphasis program." *Settled (rule 3):* label against the national programs
the crew encodes (`data/reference/emphasis_programs.toml`); read the program's scope before you
write `yes`, and give its citation in `emphasis_program`.

| Citation | National program | Scope in the crew |
|---|---|---|
| CPL 03-00-027 | Amputations in manufacturing | read from the directive: 91 NAICS codes |
| CPL 03-00-024 | Outdoor and indoor heat | read from the directive |
| CPL 03-00-025 | Falls | read from the directive: all construction falls from height, ten activities outside construction |
| CPL 03-00-026 | Warehousing and distribution centers | read from the directive |
| CPL 03-00-018 | Primary metal industries | read from the directive: health hazards in NAICS 331 and 324199, not burns or machine injuries |
| CPL 03-00-008 | Combustible dust | from the title |
| CPL 02-00-161 | Trenching and excavation | from the title |
| CPL 03-00-021 | PSM covered chemical facilities | from the title |
| CPL 03-00-023 | Respirable crystalline silica | from the title |
| CPL 03-00-009 | Lead | from the title |
| CPL 02-02-076 | Hexavalent chromium | from the title |
| CPL 03-00-020 | Shipbreaking | from the title |

A suspected local or regional program does not change the label: write it in `notes`
("possible LEP: ..."), and it is listed as a gap.

**6. Imminent danger.** *OSHA memo:* "Any imminent danger." *Settled (rule 5):* narratives
describe what already happened, so write `cannot_tell` (reason: past event) unless the text says
the hazard is still there and could kill or seriously injure someone now; then write `yes` and
quote the words in `evidence`. It is reported apart from the rules' recall.

## When you finish

Save the file under the same name (CSV, UTF-8) and send it back. Khoa returns his 15 by
23 November at noon. The scoring command, `scripts/score_category1_check.py`, compares the rules as they are on
`main` with these labels: recall and false alarms with 95% Wilson intervals, per criterion and
overall, on the cases that are not `cannot_tell`; the `cannot_tell` share with its reasons;
imminent danger apart; the employer history counts (for #18); the narratives that disagree
with the `hospitalized` count (rule 7); and the agreement on the 15 shared cases. It writes to
`eval/results/` only a file in which every row is labelled and none is marked as AI-assisted.
