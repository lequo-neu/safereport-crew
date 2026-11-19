# Related products and what we take from them

We looked for tools that already read injury reports with AI, on both sides of our users: the regulator that triages reports and the employer that prevents injuries. Sources were read on 19 November 2026. Vendor pages describe their own products and publish no accuracy figures, so the vendor features below are what the vendors claim, not what anyone measured.

## What exists

| Product | Who uses it | What it does with AI | Source |
|---|---|---|---|
| **OSHA's own triage procedure** (not software, but the process our copilot supports) | OSHA area offices | sorts every severe injury report into three categories: Category 1 must be inspected, Category 2 is inspected or sent a Rapid Response Investigation (RRI) at the Area Director's discretion, Category 3 gets an RRI. An RRI asks the employer for a written investigation and signed abatement proof within five working days; an inadequate reply can lead to an inspection | [OSHA memo, 4 March 2016](https://www.osha.gov/memos/2016-03-04/revised-interim-enforcement-procedures-reporting-requirements-under-29-cfr-190439) |
| **BLS SOII autocoder** | Bureau of Labor Statistics coders | codes injury narratives into OIICS and occupation codes with a neural model, and assigns a code only when the model's confidence passes a set threshold; it covered about 85% of codes in 2019 and about 92% in 2021 to 2022, falling to 81% in 2023 after the move to OIICS 3.02 | [BLS automated coding](https://www.bls.gov/iif/automated-coding.htm), [paper](https://www.bls.gov/iif/automated-coding/deep-neural-networks.pdf), [archived code](https://github.com/USDepartmentofLabor/soii_neural_autocoder) |
| **VelocityEHS VelocityAI** | employers' safety teams | PSIF Insights flags incidents with the potential for a serious injury or fatality; Description Analyzer improves incident descriptions; Root Cause Identifier and Corrective Action Advisor suggest causes and fixes and pass them into the next workflow; the vendor stresses human validation of every suggestion | [VelocityAI](https://www.ehs.com/velocityai/), [PSIF launch, July 2025](https://www.globenewswire.com/news-release/2025/07/01/3108237/0/en/VelocityEHS-Launches-New-PSIF-AI-to-Identify-the-Next-Serious-Injury-or-Fatality-Before-It-Happens.html) |
| **Cority Cortex AI** | employers' safety teams | agents that recommend incident findings, read incident photos and take voice entry, with an AI Control Center for model settings, data access and usage metrics | [Cority](https://www.cority.com/?p=94837) (the page did not load fully; features from search summaries) |
| **Benchmark Gensuite Genny AI** | employers' safety teams | AI built into the whole platform, including a Potentially Serious Incident advisor and agents for multi step compliance workflows | [Genny AI](https://benchmarkgensuite.com/genny-ai/) |
| **OSHA Compliance Assistant (an MCP server)** | anyone with an AI assistant | answers questions about about 30 Part 1910 topics with cited sections and corrective actions, and says it does not replace official OSHA publications | [listing](https://mcpservers.org/servers/contextkits/osha-compliance-assistant) |

A 2024 AIHA session that tested chatbots on OSHA's noise and silica standards warned that a reader who does not know the rules can be given a false sense of accuracy ([AIHA](https://www.aiha.org/news/240521-how-good-are-chatbots-at-summarizing-oehs-regulations)).

## What we take

| Idea | From | How it enters SafeReport Crew | Cost to us |
|---|---|---|---|
| Triage by OSHA's three categories | OSHA procedure | Category 1 criteria become hard rules in the Optimizer (two or more hospitalized, a worker under 18, a similar report from the employer in the last 12 months, a hazard under an emphasis program, imminent danger); Category 2 factors become the priority score (hazardous energy or other program failure, temporary workers, employees still exposed); the Optimizer only chooses among Category 2 reports | small: the rules replace weights we would have invented |
| RRI follow up | OSHA procedure | the RRI letter lists the questions and documents the employer owes within five working days; an extension reviews the employer's reply against that list and proposes an inspection when it falls short | the letter is core; the reply review is an extension |
| Code only when confident | BLS autocoder | the Intake agent auto assigns a code only above a confidence threshold set on the holdout; the rest go to a person; we report accuracy against the share coded, as BLS reports coverage | small: one threshold and one chart |
| Serious injury or fatality potential | VelocityEHS, Gensuite | each report gets a flag for whether the same event could have killed (caught in machinery near the head or torso, a fall from height, a struck by a heavy load), which raises its priority | small: one more Intake field, checked on the answer key |
| Description completeness | VelocityEHS | the Intake agent lists the facts the narrative leaves out (was the machine locked out, was a guard in place, the fall height), and the Writer turns them into the questions of the RRI letter | small |
| Corrective actions in the workflow | VelocityEHS, Cority | the inspection brief and the prevention plan propose controls by the hierarchy of controls, each tied to the cited standard | already planned |
| AI governance view | Cority | an admin page lists the models, their IDs and fallback order, what data each may see in private mode, and token, cost and latency usage | small: the logs already exist |
| Citations checked against the official text | AIHA warning, MCP assistant | already in the design: no citation reaches the user unless the critic finds it in eCFR | already planned |

## What we leave out

* Photo, video and voice input (Cority, VelocityEHS): the reports are text.
* Ergonomics from motion capture: no such data.
* Contractor and OSHA log checks: they work on an employer's own records, which we do not have.

## Where our project differs

The commercial tools serve an employer inside its own incident records. None that we found serves the regulator's side, triaging many employers' reports against inspector capacity, and none publishes how accurate its suggestions are. Our project works on the public reports of all employers, follows OSHA's own triage categories, and measures every step against ground truth: OSHA's codes, our answer key and OSHA's past inspection choices.
