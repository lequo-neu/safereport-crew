# The prevention plan (N13, #41)

**What it answers.** A plant safety manager gives a yearly budget and gets the controls to fund
first: a lockout program, machine guarding, fall protection, housekeeping and forklift training.
It is the last need of the README that was still phase 4. It runs in the **Trends and prevention**
page (section "Prevention plan") and in **Ask**, for example "Make a $40,000 prevention plan for a
plastics plant in Texas".

## How it works

1. **Plants like yours.** The Analyst reads the severe injury reports of the industry and state
   picked on the Trends page, from the year picked there (2019 by default). If they are fewer than
   10, it widens to the industry nationwide, then to every industry, as the safety talk does, and
   says so.
2. **Which control addresses which injury.** Each report goes to one control by its OIICS 3 event
   code, the same codes the Trends page filters on (estimated from the narrative before 2024):
   652 struck or caught during maintenance, cleaning or testing goes to the lockout program; 653
   caught in running equipment in normal operation to machine guarding; 41 falls to a lower level
   to fall protection; 43 falls on the same level to housekeeping. Of the reports left, those whose
   source is a powered forklift (8621) go to forklift training. A report counts once; the others
   are shown as events none of these controls address.
3. **What an injury costs.** Each report's nature of injury maps to an OSHA Safety Pays type, and
   its cost is the Safety Pays average direct cost plus the indirect cost (NCCI lost time claims,
   policy years 2015 to 2017; `data/reference/safety_pays.toml`). For every type used the direct
   cost is $10,000 or more, so the indirect cost is 1.1 times it.
4. **Your plant.** The manager enters how many severe injuries a year the plant has (1 by
   default). The expected cost a control addresses is that number, times its share of the reports,
   times its average cost per injury.
5. **The plan.** Each control has a yearly cost and an effect range, the low and the high share of
   its injuries it prevents (`config/prevention.toml`, editable in the app). The Optimizer solves a
   small integer program (PuLP CBC, as for the week's inspections) that funds the set preventing
   the most expected injury cost within the budget, once at the low end of every range and once at
   the high end. The Writer drafts the answer from ledger facts only, and the critic checks that
   every number came from a tool and that neither plan costs more than the budget.

## The demo: a plastics plant in Texas, $40,000 a year

190 severe injury reports in NAICS 326 in Texas since 2019; 54 of them are events none of the five
controls address.

| Control | Reports | Share | Cost per injury | Prevented a year (1 severe injury a year) | Yearly cost |
|---|---|---|---|---|---|
| lockout program | 60 | 32% | $166,607 | $21,045 to $42,090 | $12,000 |
| machine guarding | 43 | 23% | $175,703 | $15,906 to $31,811 | $25,000 |
| fall protection | 15 | 8% | $120,972 | $2,865 to $6,685 | $10,000 |
| housekeeping | 7 | 4% | $117,561 | $866 to $2,166 | $4,000 |
| forklift training | 11 | 6% | $150,152 | $1,739 to $4,347 | $6,000 |

With $40,000 both ends fund the lockout program and machine guarding for $37,000, which prevents an
expected $36,951 to $73,902 of injury cost a year. Net of the $37,000, that is about even at the
low end and $36,902 at the high end. As the budget changes:

| Budget | Funded (same at both ends) | Prevented a year, low to high |
|---|---|---|
| $5,000 | housekeeping | $866 to $2,166 |
| $10,000 | fall protection | $2,865 to $6,685 |
| $15,000 | lockout program | $21,045 to $42,090 |
| $20,000 | lockout program and forklift training | $22,784 to $46,437 |
| $30,000 | lockout program, fall protection and forklift training | $25,649 to $53,122 |
| $40,000 | lockout program and machine guarding | $36,951 to $73,902 |
| $60,000 | all five | $42,421 to $87,099 |

The lockout program is in every plan from $15,000 on, because maintenance and cleaning injuries
are a third of the reports and 39 of those 60 are amputations. The plan maximizes the cost
prevented within the budget, not the net value, so at the low end several plans cost more than they
prevent ($5,000, $10,000, $30,000 and $60,000 above); the answer gives the net value at both ends
so the manager sees it.

## Limits

* **The costs and effects of the controls are planning assumptions** we set for the demo, not
  measured values: replace them with the plant's quotes and judgement. The plan is solved at both
  ends of every range to show how much rests on them; with the demo values the choice is the same
  at both ends for every budget above.
* The injury mix is that of reported severe injuries (hospitalizations, amputations, loss of an
  eye) in the federal file, not the plant's own injuries; State Plan states are mostly missing.
* Safety Pays averages are national claim costs from 2015 to 2017, not adjusted for inflation.
  OSHA notes the employer always pays the indirect cost, while how much of the direct cost it pays
  depends on its insurance.
* One control per report: a forklift injury during maintenance counts for the lockout program.
  Controls do not overlap or interact in the model.
* Nothing was tuned on the answer key or the 2025 holdout; no Category 1 rule or triage weight
  changed. Tests: `tests/test_prevention.py` (offline; the count check against the Trends page
  needs the data).
