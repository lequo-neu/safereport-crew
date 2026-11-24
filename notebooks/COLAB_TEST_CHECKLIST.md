# Colab test checklist (for a run driven with Claude in Chrome)

The goal: run `notebooks/safereport_crew.ipynb` top to bottom on a **fresh** Colab runtime, check
each part, and save it with outputs. A person does the steps marked **(person)**: signing in to
Google, picking the OSHA file in the upload dialog (a browser file dialog cannot be driven), and
sharing the link.

## Before you start

- [ ] **(person)** Download the **November 2025** release in a browser, from its direct address:
      https://www.osha.gov/sites/default/files/January2015toNovember2025.zip (16,224,511 bytes on
      24 November 2026). Do **not** use "Download the full SIR data set" on the SIR page: since
      November 2026 it gives `January2015toDecember2025.zip`, a newer release the notebook refuses.
- [ ] The branch with the notebook is pushed. Open it in Colab by URL:
      `https://colab.research.google.com/github/lequo-neu/safereport-crew/blob/<branch>/notebooks/safereport_crew.ipynb`
      (after the merge, `<branch>` is `main`).
- [ ] **(person)** Signed in to a Google account in this Chrome profile.
- [ ] *Runtime > Disconnect and delete runtime*, so the run starts fresh. CPU runtime is enough.
- [ ] No secret is set: the key icon (Secrets) panel has no notebook access granted. The notebook
      never reads it.

## Run

- [ ] *Runtime > Run all*. If Colab warns that the notebook is not from Google, choose *Run anyway*.
- [ ] Part 4 prints a Python version from 3.11 to 3.13 and `Model API key variables removed from
      this session: 0` (any other number: stop, a key was set in the runtime).
- [ ] Part 5: pip prints a red `ERROR: pip's dependency resolver does not currently take into
      account ...` line saying `google-colab ... requires pandas==2.2.3, but you have pandas 3.x`
      (seen on the first Colab run). This is expected and documented in part 5; the cell still
      succeeds. Write down the exact line for the PR. Any *other* pip error is a failure.
- [ ] Part 5 then prints `pandas 3.x installed, not yet loaded` (or `, loaded`) and ends with
      `SafeReport 0.1.0 at commit <first 12 of REPO_REF>`. If it stops with "pandas ... is loaded in
      this session": *Runtime > Restart session*, then *Run all* again, and note that it happened.
- [ ] Part 6 shows the file picker: **(person)** choose the November zip. The cell prints
      `16,224,511 bytes`, no "Note: this zip is not byte for byte ..." line, and `105,996 reports,
      01 Jan 2015 to 30 Nov 2025, columns checked`.
- [ ] Optional negative check, on a second runtime: choose `January2015toDecember2025.zip` instead.
      The cell must stop with `WrongReleaseError: ... release ending in December 2025 ...` and the
      November address. Nothing is extracted.
- [ ] Part 7 runs `build-data`, `fetch-ecfr`, `build-index --no-dense`, `train-baseline` and `check`
      without a traceback; `check` lists Reports, Indexes and Baseline as `ready`. Note how long each
      took (printed in seconds).
- [ ] Part 8 shows the report count and a table by year.
- [ ] Part 9 prints every model slot as `OfflineBackend`.
- [ ] Part 10 prints the Planner's question about the state.
- [ ] Part 11 shows the handoff table and ends with `The run is paused at: Approve the list, or ask
      for changes?`.
- [ ] Part 12 also prints B4's count read from `eval/results/batch_savings.json` (`B4 (hybrid search): 20
      of 31`) next to this run's (`This run (bm25 search): 23 of 31` on the first Colab run) and a table
      of the reports on which they differ. A different count here is explained by the search setting,
      not a failure; a different count *with* `USE_EMBEDDINGS = True` is worth reporting.
- [ ] Parts 12 to 15 show the stage 1 table, one stage 2 report (Intake, Standards, Analyst), the
      plan, the summary's placeholders with their sources, one RRI letter, and the critic's checks.
- [ ] Part 16 prints the moved report, the decision log (asked for changes, then approved) and
      the final answer; the last table lists the seven agents.
- [ ] No cell ends in a traceback. Search the page (Ctrl+F) for `Traceback`: none. Searching for
      `ERROR` finds only pip's pandas line in part 5 (above) and the explanatory text.

## Checks on the content

- [ ] Search the page for `sk-ant`, `sk-proj`, `AIza` and `hf_`: no match. (The names
      `ANTHROPIC_API_KEY` and so on appear once, in part 4's list of variables it removes; that list
      holds names, not values.)
- [ ] The numbers in the text cells of parts 12 to 16 come from the run (they are printed by code,
      not typed in markdown).
- [ ] Headings show in the table of contents (left panel) in order 1 to 20.
- [ ] Note the runtime's Python version and the total run time for the PR.

## Save and share

- [ ] *File > Download > Download .ipynb* (the version with outputs). It replaces
      `notebooks/safereport_crew.ipynb` in the PR; then `python -I notebooks/build_notebook.py --check`
      must still pass (it compares sources only).
- [ ] **(person)** *File > Save a copy in Drive*, *Share*, "Anyone with the link can view", and copy
      the link for #38. Ask Hamad before posting it.

## If something fails

Write down the part number, the cell's last lines of output and the runtime type, take a screenshot,
and stop. Do not change `REPO_REF`, the settings or any code in Colab to make it pass; fix it in
`notebooks/sections/` and rebuild.
