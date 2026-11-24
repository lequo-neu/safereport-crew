# The Colab notebook (issue #38)

`safereport_crew.ipynb` is the course notebook: it installs SafeReport Crew at a pinned commit,
loads OSHA's file, builds the data and indexes, and runs one Texas week through the seven agents,
offline, with no API key and no cost.

**Do not edit the `.ipynb` by hand.** It is assembled from the files in `sections/`, so Hamad and
Khoa can work on their own parts without touching the same JSON:

| File | Notebook parts | Owner | Status |
|---|---|---|---|
| `sections/10_hamad_foundation.py` | 1 to 8: the problem, the agents, settings, runtime, install, OSHA data, build, first look | Hamad | done |
| `sections/20_hamad_texas_week.py` | 9 to 16: the Texas week, agent by agent, handoffs, approval | Hamad | done |
| `sections/30_khoa_router.py` | 17: the router (B7 numbers, #8) | Khoa | placeholder |
| `sections/40_khoa_evaluation.py` | 18: the evaluation numbers from `eval/results/` | Khoa | placeholder |
| `sections/50_khoa_edge_cases.py` | 19: edge cases (short narrative, invented citation) | Khoa | placeholder |
| `sections/90_closing.py` | 20: summary | together | draft |

## Editing a section

A section is a Python file in the "percent" format. The first line names the owner.

```python
# Owner: Khoa (issue #38). ...

# %% [markdown]
# ## 17. The model router (Khoa)
# One short paragraph: what the next cell does and why.

# %%
print("the code")
```

Then rebuild and check:

```bash
python -I notebooks/build_notebook.py
pytest -q tests/test_notebook.py
ruff check . && ruff format --check .
```

`build_notebook.py --check` fails when the `.ipynb` is out of date with the sections. A rebuild
keeps the saved outputs of every code cell whose source did not change.

**Names the earlier sections leave for later ones:** `REPO_DIR` (the pinned copy; its
`eval/results/` holds the measured numbers), `COMMIT`, `USE_EMBEDDINGS`, `run(...)` and
`safereport_cli(...)` (run a command or `safereport <command>` and stop on failure), `pd`,
`display`, `Markdown`, `reports` (all reports), `services`, `graph`, `config` (the finished Texas
run), `state` (its final state), `handoff_table`, `stage1`, `rows` (the plan rows). For a new run, use
a new `run_config()` so the Texas run is not changed.

**Rules for every section** (from #38): a markdown cell before each code cell, offline only (no
`live=True`, no `--live`, no Colab secrets), every number read from a file or computed in the
notebook, never typed in. `tests/test_notebook.py` checks most of these.

## Running it

**On Colab** (the hand-in): open the notebook from GitHub in Colab, choose *Runtime > Run all*,
upload `January2015toNovember2025.zip` when asked, and save with outputs. The steps to check a run
are in [COLAB_TEST_CHECKLIST.md](COLAB_TEST_CHECKLIST.md).

**On a local machine** (the team's test): the notebook clones into a work folder and uses the
current environment's packages. With the project installed and `nbclient` and `ipykernel` added:

```bash
export SAFEREPORT_NOTEBOOK_WORKDIR=/tmp/nbwork                  # where it clones and builds
export SAFEREPORT_NOTEBOOK_REPO_URL=$PWD                         # clone this checkout instead of GitHub
export SAFEREPORT_NOTEBOOK_DATA=$PWD/data/raw/January2015toNovember2025.zip
python -c "import nbformat; from nbclient import NotebookClient as C; nb = nbformat.read('notebooks/safereport_crew.ipynb', 4); C(nb, timeout=3600).execute(); nbformat.write(nb, '/tmp/executed.ipynb')"
```

## Limits and external dependencies

* **OSHA's file** cannot be downloaded by a script; the reader downloads it in a browser. The
  notebook is pinned to the November 2025 release. Since November 2026 OSHA's page links
  `January2015toDecember2025.zip` by default; the November one is still served at
  https://www.osha.gov/sites/default/files/January2015toNovember2025.zip (checked 24 November
  2026, 16,224,511 bytes, the same size and SHA-256 as the file the project was built from). Part 6
  refuses another release by name and by last report date. If OSHA removes the November file,
  the notebook cannot run as pinned; that needs a team decision, not a silent switch.
* **Network at run time:** GitHub (clone), PyPI (install, Colab only), the public eCFR API
  (`fetch-ecfr`), and Hugging Face only when `USE_EMBEDDINGS = True`.
* **The pin.** `REPO_REF` is a commit of `main`; set it to the release tag when the team tags the
  hand-in version. The notebook's own file is not part of that commit; it only installs it.
* **Colab packages.** The project needs pandas 3 (`pandas>=3.1,<4`) and `google-colab` pins
  pandas 2.2.3, so pip prints a dependency-resolver ERROR line during the install. It is a real
  conflict that pip reports but does not block: Colab's own pandas-based extras may misbehave in
  that session; the notebook does not use them. Part 5 stops if pandas was loaded before the
  install, so the notebook never mixes two versions; restart the session and run all again.
* **Stage 2 count.** With `USE_EMBEDDINGS = False` the Texas week sends 23 reports to stage 2;
  B4 (`eval/results/batch_savings.json`) measured 20 with the hybrid search. Both count the same
  thing; with BM25 alone three reports have a retrieval margin under `min_retrieval_margin`.
  Part 12 reads B4's number from the file and lists the difference.
* **Offline answers.** Every model step is answered by the offline rules, so the agents' outputs
  show the flow, not model quality. The model results are in part 17 and the README.
* With `USE_EMBEDDINGS = False` the regulation search is BM25 only, which the README reports as
  weaker; the citations shown differ from an embeddings run.
