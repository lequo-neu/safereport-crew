# Evaluation

`safereport eval-baselines` writes the Phase 1 numbers to `eval/results/`:

* `phase1_baselines.json`: event coding on the 2025 holdout (accuracy by code level and the
  coverage curve), the OIICS 3 recoding check, and standards retrieval on the answer key;
* `retrieval_<setup>.csv`: the sections found for each of the 52 cases with a standard.

Nothing is tuned on the answer key or the holdout; the floors in the tests sit below the
measured numbers to catch a regression. Later phases add the agent and router runs, seeded
domain checks, inspection priority, two stage batch savings and the Pareto chart.

`python -I scripts/eval_staffing_falls.py` (issue #30) writes `staffing_falls.json` and
`staffing_falls_added.csv`: the Falls program before and after the work route for staffing
agencies, on every report outside the 2025 holdout (2015 to 2019 for development, 2020 on as the
test slice). `python -I scripts/score_staffing_falls_labels.py` (issue #37) then adds Hamad's hand
labels of the 20 added reports (`data/labels/staffing_falls_added_Hamad.csv`) to both files and the
precision per slice; rerun it after the evaluation, which writes both files without the labels.
See [docs/FALLS_STAFFING.md](../docs/FALLS_STAFFING.md).
