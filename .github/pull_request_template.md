## What this changes

<!-- The task number from docs/TEAM_PLAN.md (for example B2) and, in one or two sentences, what a user can now do or see. -->

Closes #

## How I checked it

<!-- Commands you ran and pages you tried. -->

- [ ] `ruff check .` and `ruff format --check .` pass
- [ ] `pytest -q` passes, with tests for what this adds (offline, no key, no data download)
- [ ] Every new number comes from a file in `eval/results/` with the command that wrote it (in the Basic stage, the README row goes in this description, not in the README)
- [ ] No `.env`, key, raw data, processed data, index or `outputs/` file is in the diff
- [ ] Nothing was tuned on the answer key

## Money

<!-- Paid calls made for this change, and their cost. Write "none" when you used only offline runs or --live --mode private. -->

## What to look at

<!-- Where Kevin should look first, and anything you are unsure about. -->
