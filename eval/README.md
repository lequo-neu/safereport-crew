# Evaluation

`safereport eval-baselines` writes the Phase 1 numbers to `eval/results/`:

* `phase1_baselines.json`: event coding on the 2025 holdout (accuracy by code level and the
  coverage curve), the OIICS 3 recoding check, and standards retrieval on the answer key;
* `retrieval_<setup>.csv`: the sections found for each of the 52 cases with a standard.

Nothing is tuned on the answer key or the holdout; the floors in the tests sit below the
measured numbers to catch a regression. Later phases add the agent and router runs, seeded
domain checks, inspection priority, two stage batch savings and the Pareto chart.
