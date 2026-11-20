# How we work

The rules Seven Team-5374 agreed on for SafeReport Crew. The tasks and dates are in
[docs/TEAM_PLAN.md](docs/TEAM_PLAN.md).

## Getting started

1. Accept the GitHub invitation to `lequo-neu/safereport-crew`.
2. Clone the repository and follow the README quick start: install, download the OSHA file in a
   browser, build the data and indexes, run `safereport check`.
3. Run `pytest -q` and `ruff check .` once before you change anything: everything must pass.

## Branches and pull requests

* `main` is protected: changes arrive by pull request. Kevin, who owns the repository settings,
  may still push small fixes to documents and settings directly, and says so in the team chat.
* One branch per task, named `<name>/<task>-<topic>`, for example `hamad/b2-inspection-auc`.
* Open the pull request early as a draft if you want comments; mark it ready when it meets the
  definition of done below.
* A pull request needs the CI check to pass and Kevin's approval. Ask for his review in the pull
  request (Reviewers) and say in the description what to look at.
* Merge with "Squash and merge". The branch is deleted after the merge.
* Before you start a day of work, update from `main` (`git pull --rebase origin main` on your branch).

## Definition of done

A task is done when its pull request:

* meets the outputs written for it in docs/TEAM_PLAN.md;
* passes `ruff check .`, `ruff format --check .` and `pytest -q`, with tests for what it adds,
  and the tests run offline with no API key and no data download;
* says what changed for a user, and every number it adds comes from a file in `eval/results/`
  with the command that wrote it. In the Basic stage a pull request does not edit the README,
  proposal or open issues tables: it puts the row in its description, and Kevin updates those
  files in one pass at the end of the stage (see docs/TEAM_PLAN.md);
* lists in the description how you checked it (commands run, pages tried).

## Data, keys and money

* Never commit `.env`, API keys, `data/raw/`, `data/processed/`, `indexes/` or `outputs/`. They are
  in `.gitignore`; check `git status` before every commit. GitHub push protection blocks known keys.
* Never paste a key in a chat, an issue or a pull request.
* Without `--live` nothing is paid. Only the person named in the plan runs paid calls in a stage.
* The $1.50 cap is counted on each machine (`outputs/`), so it does not add up across laptops by
  itself. Write what you spent in your pull request; the team total must stay under $1.50.
* Prefer `--live --mode private`: it uses only Gemma on LM Studio on your machine, for free.

## Measuring honestly

* The answer key (`data/labels/answer_key.csv`) is the final test set: no prompt, weight, threshold
  or rule is tuned on its cases. Tune on other reports and score the key once at the end.
* Every rate comes with its 95% Wilson interval and its number of cases.
* Say when a number is estimated, comes from the offline rules, or rests on a prior.
* Hand labels follow `docs/LABELING_GUIDE.md`; a second person checks a share of them and we report
  the agreement.

## Writing

* Code, comments, documents and interface text are in English, in plain words.
* Name things by what a user understands (an inspector day, a letter), not by how the code is built.
* Record any AI tool you use for the project in `docs/AI_USAGE.md`, and check what it wrote.

## Talking to each other

* Stuck for more than half a day: say so in the team chat with what you tried.
* A decision that changes someone else's work (a schema, a config value, a shared file): raise it
  in the chat first, or ask for a short meeting.
* Bugs and ideas go in GitHub issues, so nothing is lost in chat history.
