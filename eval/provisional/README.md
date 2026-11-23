# B3: an automated, AI-assisted first pass (provisional, not the hand check)

**These are not human labels and not the rules' accuracy.** The hand check of issue #4 still
needs a person's labels in `data/labels/category1_check.csv` (still blank) and Khoa's 15 in
`data/labels/category1_check_Khoa.csv` (still blank). Nothing here goes in `eval/results/`, and
`scripts/score_category1_check.py` refuses to write AI-provisional scores there.

## How the provisional labels were made (21 November 2026)

The crew's own rules were **not** used to label: scoring rules against their own output agrees
by construction. Each column came from a source independent of the crew's code, and every
reading was written down before the crew's output was computed.

| Column | Source | Independent of the crew's code? |
|---|---|---|
| `two_or_more_hospitalized` | OSHA's `hospitalized` count (settled rule 7) | No: the rule reads the same field |
| `similar_report_within_12_months` | `scripts/category1_history_by_guide.py`: the guide's written procedure over OSHA's raw file; possible matches are `cannot_tell` | Yes (it does not import `employers.py`) |
| `worker_under_18`, `emphasis_program_hazard` | Claude (an AI model) reading each narrative against the guide and the program scopes: Appendix B of CPL 03-00-027, the heat NEP's tables, CPL 03-00-025 (Falls), CPL 03-00-026 (Warehousing, 2026) and CPL 02-00-161 (Trenching) | Yes |
| `imminent_danger` | Rule 5 as written: `cannot_tell` (past event) for all 100 | Not a judgment |

Every row carries its evidence, a confidence and the source of each column. 36 rows are flagged
for a person.

**The per-case file is not committed yet.** 7 of the 36 flagged cases are among the 15 Khoa labels
blind, and a person reviewing a case should not see the AI's answer first. The per-case labels,
the history matches and the scores are kept off GitHub until both 15-case sets are returned
(23 November, noon) and the targeted human review below is done.

## What can be said from it

| Criterion | Rules against the provisional labels | What it shows |
|---|---|---|
| Employer history | 12 of 12 yes and 84 of 84 no agree; the rules say no on the 4 possible-only matches | **The code does what the written rule says** (an independent implementation agrees on every case both can decide). Whether the 4 possible matches are the same employer needs a person. |
| Emphasis program | 12 of 17 AI yes; 2 of 75 AI no flagged by the rules; 8 `cannot_tell` | Agreement with one AI reader, **not accuracy** |
| Category 1 | 24 of 27 AI yes (95% Wilson 72% to 96%); 2 of 64 AI no flagged (1% to 11%); 9 `cannot_tell` | Agreement with one AI reader, **not accuracy** |
| Two or more hospitalized | 1 of 1, 0 of 99 | Nothing: the same field as the rule |
| Worker under 18 | no case in the sample says yes | Recall cannot be measured on this sample |
| Imminent danger | all `cannot_tell` | Not measurable (rule 5) |

The disagreements on emphasis programs are of three kinds, each a question for a person: a
trench collapse, which the crew cannot force because the Trenching NEP is marked unverified;
caught-in-machinery injuries in an Appendix B industry with no amputation, which the crew's
words miss; and amputations from a hand tool or a dropped roll, which the crew counts.

## Still needs people

1. Human labels: all 100 by hand, or (if Kevin agrees on #4) a blind, targeted review of the 36
   flagged cases plus a random spot-check of the others, scored with `--source human`.
2. Khoa's 15 and Hamad's same 15, labelled blind, for agreement (`--second`).
3. The 4 possible employer matches.

## The 36 flagged cases (criterion only, no answer)

29 outside the shared 15; the other 7 are listed after the exchange.

| Criterion to review | Cases |
|---|---|
| Employer history | K019, K025, K026, K034, K040, K045, K054, K061, K071, K093, K100 |
| Emphasis program | K018, K023, K024, K031, K046, K050, K055, K058, K059, K062, K066, K070, K079, K087, K091 |
| Both | K003, K067, K080 |

## Reproduce

    python scripts/category1_history_by_guide.py --out <dir>/category1_history_by_guide.json
    python scripts/score_category1_check.py --labels <provisional csv> --source ai-provisional --out <dir>/score.json

Both run offline; nothing is paid.
