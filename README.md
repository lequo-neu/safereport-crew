# SafeReport Crew

A multi agent copilot that turns OSHA severe injury reports into inspection and prevention decisions.
Final project for IE5374 Applied Generative AI, by **Seven Team-5374**: Quoc Hung Le (Kevin), Hamad Al Sulaimi, Khoa Tran.

The plan is in [docs/PROPOSAL.md](docs/PROPOSAL.md); related products are compared in
[docs/RELATED_PRODUCTS.md](docs/RELATED_PRODUCTS.md); the answer key follows
[docs/LABELING_GUIDE.md](docs/LABELING_GUIDE.md).

## Status

Phase 2 of 4 done. The seven agents run as a LangGraph graph on a deterministic offline backend,
so everything below works locally with no API key. Live model clients are added near the end of
the project, when the keys are used.

| Phase | What it built |
|---|---|
| 0 | answer key, model config, schemas, offline backend |
| 1 | Parquet and DuckDB data layer, eCFR retrieval (BM25 plus FAISS), baseline event coder, employer matching, redaction |
| 2 | the crew: Planner, Intake, Standards, Analyst, Optimizer, Decision critic, Writer; router with escalation and fallback; triage integer program; domain checks; FactLedger; interrupts for questions and approval; live adapters for Anthropic, OpenAI, Google and LM Studio; similar injury search over all narratives |

## Try the crew

```bash
safereport ask "An employee's hand was pulled into the rollers of a laminator while clearing a jam."
safereport ask "Find caught in machinery injuries in Texas since 2022, check which employers reported more than once, then plan this week's inspections with 40 inspector days." --approve
safereport ask "Plan this week's inspections with 40 inspector days." --answer state=Texas --approve
safereport ask "Write a ten minute safety talk on lockout for my night shift, in English and Spanish."
safereport ask "..." --mode private
safereport ask "..." --live          # calls the models whose API keys are set; costs money
safereport employer-pairs            # scores the hand check of employer matching
```

"This week" replays 17 to 23 November 2025 (31 Texas reports), the last full week in the data.
The triage assumptions (priority weights, inspector days per inspection, default days of a
week) live in [config/triage.toml](config/triage.toml). Each run prints the answer and the trace: the agent, the model the router chose and why, and
what each step found. The offline backend answers every model step from fixed rules, so the
picks it makes are a stand in, not a result to report; see [docs/OPEN_ISSUES.md](docs/OPEN_ISSUES.md).

## How a request runs

1. The **Planner** splits the request into sub tasks with their dependencies and stops to ask
   when a required parameter (a state, a start year) is missing.
2. For a week of reports, **stage 1** codes every report without a model (baseline, rules, BM25,
   employer matching); only unclear, severe or borderline reports go to **stage 2**, one LangGraph
   `Send` branch each, where **Intake**, **Standards** and the **Analyst** run on models.
3. The **Optimizer** applies OSHA's Category 1 rules, then a PuLP integer program spends the
   inspector days left; with too few days a relaxed model says how many more are needed.
4. The **Writer** drafts briefs, RRI letters, safety talks (English and Spanish) and answers with
   every number as a FactLedger placeholder.
5. The **Decision critic** checks every citation against eCFR, the OSHA domain rules, every number
   and the plan rules, and sends work back at most twice per loop.
6. The graph pauses for the **Area Director**, who approves or edits rows; the run resumes at the
   Optimizer from the SQLite checkpoint, and each decision goes to the decision log.

## Set up

Python 3.11 to 3.13.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,embeddings]"
```

`embeddings` adds sentence-transformers (with torch) and FAISS for dense retrieval; without it
retrieval runs on BM25 alone.

## Build the data and indexes

1. Download the OSHA Severe Injury Reports as described in [data/raw/README.md](data/raw/README.md).
2. Build everything (a few minutes the first time; the embedding model is downloaded once):

```bash
safereport build-data
safereport fetch-ecfr
safereport build-index
safereport train-baseline
```

| Command | What it writes | Notes |
|---|---|---|
| `build-data` | `data/processed/reports.parquet` | 105,996 reports with a `split` column: train (2015 to 2024), holdout (the 1,000 2025 reports listed in `data/splits/holdout_2025.csv`), recent (other 2025) |
| `fetch-ecfr` | `data/raw/ecfr/title-29-part-1910.xml` | eCFR as of 10 November 2026, public API, no key |
| `build-index` | `indexes/` | paragraphs of Part 1910, the General Duty Clause and 12 emphasis programs (`data/reference/`), BM25 plus `BAAI/bge-small-en-v1.5` embeddings in FAISS |
| `train-baseline` | `indexes/event_baseline.joblib` | TF IDF and logistic regression on OIICS event codes, scored on the holdout |

`train-baseline` also writes `data/processed/event_codes_v3.parquet`, an OIICS 3 event code for
every report (OSHA's own from 2024, estimated before; see below). `safereport eval-baselines`
scores every baseline and writes the numbers to [eval/results](eval/results). Tests that need the
built data are skipped when it is missing; everything else runs offline with no API key.

## Phase 1 results

Measured on 19 November 2026; full numbers in [eval/results/phase1_baselines.json](eval/results/phase1_baselines.json).

| What | Result |
|---|---|
| Event coding baseline on the 1,000 report 2025 holdout | full code 59.6%, two digit group 78.7%, one digit division 90.7% |
| Same baseline, coding only when confidence is at least 0.7 | 51% of reports coded, 80% of them right (at 0.9: 19% coded, 93% right) |
| Standards retrieval without a model, top 3, narrative and OSHA codes (strict / lenient) | BM25 29.4% / 31.4%; BM25 plus embeddings 41.2% (95% interval 28.8 to 54.8) / 51.0% (37.7 to 64.1) |

The key has 51 cases with a standard (C20 was corrected to no specific standard by the team),
so one case moves a rate by about 2 points and every rate is reported with its 95% Wilson
interval in `eval/results/phase1_baselines.json`.

**OSHA changed its event codes in January 2024.** From 2024 the reports use OIICS 3: about 65% of
the 2024 codes never appear before, and the same code can mean something else (group 64 is
"caught in machinery" in OIICS 2 and "struck by a falling object" in OIICS 3). So:

* the baseline is trained on OIICS 3 reports (2024, and 2025 outside the holdout), not on 2015 to 2024;
* the data layer refuses an event code or event title filter over a period that spans January 2024;
* `event_group_v3` filters across all years using the baseline's OIICS 3 code for older reports,
  marked as estimated. The recoded 2023 groups differ from the real 2024 groups by a total
  variation of 0.064, against 0.047 between the real 2024 and 2025.

Retrieval without a model is weak because narratives say "forklift" and "rollers" while the rules
say "powered industrial truck" and "nip points". In Phase 2 the Standards agent adds terms in the
language of the rules before searching (the `terms` argument of `IndexRegistry.search`).

## Live results: model terms for the Standards agent

Each model ran once over the 51 cases, with the same retrieval (BM25 plus embeddings, narrative
and OSHA codes) and a prompt checked for format on reports outside the key, so nothing was tuned
on the key. "Gained" and "lost" count the cases the run gets and the baseline misses, and the
reverse; p is the exact McNemar test on those pairs. Numbers in
[eval/results/live_terms_summary.json](eval/results/live_terms_summary.json).

| Top 3, strict | Hits of 51 | Rate (95% interval) | Gained / lost | p |
|---|---|---|---|---|
| No model (baseline) | 21 | 41.2% (28.8 to 54.8) | | |
| GPT 5 nano terms | 31 | 60.8% (47.1 to 73.0) | 13 / 3 | 0.021 |
| Claude Sonnet 5.5 terms | 36 | 70.6% (57.0 to 81.3) | 16 / 1 | 0.0003 |

* At the top position, Claude finds the primary section for 26 cases (51.0%) against 12 without a
  model; lenient top 3 (primary or secondary) is 38 (74.5%).
* Claude against GPT 5 nano: 7 cases gained, 2 lost (p 0.18), so on 51 cases the gap between the
  two models is not settled.
* Cost per call was about $0.0016 for Claude and $0.0009 for GPT 5 nano, which spends about 2,300
  reasoning tokens per call. The whole experiment cost $0.14 of the team's $1.50 cap.
* Gemini 3.5 Flash (forwarding to 3.6 Flash) returned 503 and 429 errors for most calls on 19
  November and was not scored.

```bash
safereport eval-live --model claude --smoke 3   # format check on reports outside the key
safereport eval-live --model claude --score     # one run over the key (cached, capped)
safereport live-summary                         # every scored run against the baseline, no calls
```

## Check

```bash
safereport check
pytest -q
ruff check . && ruff format --check .
```

`python scripts/merge_labels.py` rebuilds `data/labels/answer_key.csv` from the three label files
and `data/labels/settlements.csv`.

## License

MIT, Seven Team-5374.
