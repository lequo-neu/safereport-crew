# Independent review brief: Phases 0 and 1

This brief is for a reviewer who has not seen how the work was done. It says what exists, what
to check in each file, and what "ready for Phase 2" means. Report findings; do not fix them.

## Ground rules

* Read only. Do not edit, create or delete files in the project, and do not commit.
* No paid model calls and no new downloads; everything needed is already on disk.
* Run Python only through the project environment: `source .venv/bin/activate` in the project
  folder (Python 3.12). Built data is in `data/processed/` and `indexes/`.
* Items already listed in `docs/OPEN_ISSUES.md` are known; report them only if the file
  misstates them or if they are worse than it says.

## What the project is

SafeReport Crew is a multi agent copilot over OSHA's 105,996 Severe Injury Reports (2015 to
November 2025). Phase 0 built the answer key, model config, schemas and an offline model backend.
Phase 1 built the data layer (Parquet and DuckDB), retrieval over eCFR Part 1910 (BM25 plus FAISS),
a TF IDF and logistic regression event coder, employer matching and redaction. Phase 2 will add
seven LangGraph agents on top of these pieces. Plan: `docs/PROPOSAL.md`.

## Start here

```bash
source .venv/bin/activate
ruff check . && ruff format --check .
pytest -q
safereport check
safereport eval-baselines
```

Expected now: ruff clean, all tests pass (dense retrieval tests skip when the embedding model is not cached), `safereport check` shows reports, indexes and baseline
ready, and `eval-baselines` reproduces `eval/results/phase1_baselines.json`.

## Files and what to check

### Answer key (Phase 0)

| File | Check |
|---|---|
| `data/labels/to_label_{Kevin,Hamad,Khoa}.csv`, `settlements.csv` | the reviewed labels and the two settled disagreements (C05, C07) |
| `src/safereport/labels.py`, `scripts/merge_labels.py` | the merge keeps agreed labels, uses settlements for disagreements, and stops on an unsettled one; `answer_key.csv` is exactly what the merge produces |
| `data/labels/answer_key.csv` | 60 cases, 52 with a standard; every citation exists in Part 1910; `accepted_sections` holds the primary (and the secondary when there is one) |
| `docs/LABELING_GUIDE.md` | the rules the labels follow; spot check 10 labels against the guide and the narrative |

### Config, schemas, backend (Phase 0)

| File | Check |
|---|---|
| `config/models.toml`, `src/safereport/config.py` | four models from four providers, IDs with a check date, no guessed prices, a fallback chain that only names configured models |
| `src/safereport/schemas.py` | `Report.from_csv_row` maps OSHA's columns correctly; `Citation` accepts only our formats; `AnswerKeyCase` validation is sound |
| `src/safereport/backends.py` | the offline backend is deterministic and raises the scripted failures in order |

### Data layer (Phase 1)

| File | Check |
|---|---|
| `src/safereport/data.py` | `id` is unique and `osha_id` keeps OSHA's number; the split column (train 2015 to 2024, holdout from `data/splits/holdout_2025.csv`, recent); `oiics_version`; the SQL guard and the locked file access in `ReportStore`; the OIICS guard (`check_coding`) and `event_group_v3`; `yearly_trend` (same months, zero years, estimated share) |
| `data/splits/holdout_2025.csv` | 1,000 ids, all from 2025, none used in training |

### Employer matching and redaction (Phase 1)

| File | Check |
|---|---|
| `src/safereport/employers.py` | only identical normalized names (or a person's decision) count as "same"; away from the site the industry must match; possible matches never count in `repeats_within` |
| `src/safereport/redaction.py` | every placeholder restores exactly; employer, address lines, city, ZIP, titled and role named people are hidden; lower case common words survive |

### Retrieval (Phase 1)

| File | Check |
|---|---|
| `src/safereport/ecfr.py` | paragraph citations on well formed sections (try 1910.212, .147, .178, .217, .23, .28, .134); `exact` is False only where the path is doubtful |
| `src/safereport/retrieval.py` | section profiles plus paragraph hits fused with equal weights; `part_for` sends NAICS 23 to Part 1926 (or notes the fallback); emphasis programs apply only by industry and trigger; `terms` reaches the query; the OpenMP setting that stops torch and faiss crashing |
| `data/reference/general_duty.toml`, `emphasis_programs.toml` | names, directive numbers and dates match OSHA's list; the comments say plainly which parts are our own |

### Baseline and evaluation (Phase 1)

| File | Check |
|---|---|
| `src/safereport/baseline.py` | trained only on OIICS 3 reports outside the holdout; confidence is a normalized score; `recode_to_oiics_3` keeps OSHA's code from 2024 and marks older ones as estimated |
| `src/safereport/evaluation.py`, `eval/results/` | the scores are computed as described and match the files |
| `tests/` | the tests check behaviour rather than restate the code; the real data tests skip cleanly without the data (CI) |

## Numbers to verify against the data

These appear in `docs/PROPOSAL.md` or `README.md`. Each should be reproducible from the built data.

| Claim | Where |
|---|---|
| 105,996 reports; 86,518 hospitalized; 27,978 amputations; 34,472 in manufacturing (32.5%) | proposal |
| 33.5% of reports and 46.7% of manufacturing reports inspected | proposal |
| 173 reports a week nationwide in 2024; 28.5 in Texas | proposal |
| 76% of manufacturing employers (name and state) filed one report | proposal |
| 70,593 employer strings; Walmart 340 spellings over 891 reports | proposal |
| 2025 up 4.5% on the same eleven months of 2024 | proposal, README |
| two or more hospitalized inspected 68.8%; manufacturing amputations 58.8%; temporary worker 49.7% | proposal |
| 13 of 15 shared cases on the same section (86.7%) | proposal |
| baseline 59.6% / 78.7% / 90.7%; 51% coded at 80% accuracy for confidence 0.7 | README, eval results |
| retrieval 40.4% / 50.0% at 3 (hybrid, narrative and codes) | README, eval results |
| recoded 2023 against real 2024: total variation 0.064 (2024 against 2025: 0.047) | README, eval results |

## Ready for Phase 2 means

1. Every check above passes, or each failure is listed with its effect.
2. The interfaces Phase 2 will call behave as their docstrings say: `ReportStore` (filters,
   `yearly_trend`, `report`, `reports_between`), `EmployerIndex.history` and `repeats_within`,
   `redact` and `restore`, `IndexRegistry.search` (sections, `margin`, `emphasis`, `terms`),
   `EventBaseline.predict`, `OfflineBackend`, `load_model_settings`.
3. Nothing in the holdout or the answer key was used to fit or tune anything.
4. The proposal and README do not claim something the code does not do.

## How to report

A short list, most severe first. For each finding: the file and line, what is wrong, an input
that shows it, how sure you are, and a one line fix. Then one line per area you checked and
found clean, and a final verdict: ready, ready with listed caveats, or not ready.
