# Colab test checklist (for a run driven with Claude in Chrome)

The goal: run `notebooks/safereport_crew.ipynb` top to bottom on a **fresh** Colab runtime, check
each part, and save it with outputs. A person does the steps marked **(person)**: signing in to
Google, picking the OSHA file in the upload dialog (a browser file dialog cannot be driven), and
sharing the link.

## Before you start

- [ ] **(person)** Download `January2015toNovember2025.zip` from https://www.osha.gov/severe-injury-reports
      ("Download the full SIR data set") to this computer.
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
- [ ] Part 5 ends with `SafeReport 0.1.0 at commit <first 12 of REPO_REF>` and no error. If Colab
      asks to restart the session: *Runtime > Restart session*, then *Run all* again.
- [ ] Part 6 shows the file picker: **(person)** choose the zip. The cell prints the size and
      `columns checked`.
- [ ] Part 7 runs `build-data`, `fetch-ecfr`, `build-index --no-dense`, `train-baseline` and `check`
      without a traceback; `check` lists Reports, Indexes and Baseline as `ready`. Note how long each
      took (printed in seconds).
- [ ] Part 8 shows the report count and a table by year.
- [ ] Part 9 prints every model slot as `OfflineBackend`.
- [ ] Part 10 prints the Planner's question about the state.
- [ ] Part 11 shows the handoff table and ends with `The run is paused at: Approve the list, or ask
      for changes?`.
- [ ] Parts 12 to 15 show the stage 1 table, one stage 2 report (Intake, Standards, Analyst), the
      plan, the summary's placeholders with their sources, one RRI letter, and the critic's checks.
- [ ] Part 16 prints the moved report, the decision log (asked for changes, then approved) and
      the final answer; the last table lists the seven agents.
- [ ] No cell shows a red error. Search the page (Ctrl+F) for `Traceback` and `Error`: none outside
      the explanatory text.

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
