# Owner: Hamad (issue #38). Introduction, setup, OSHA data and the build.

# %% [markdown]
# # SafeReport Crew
#
# **A multi-agent copilot that helps an OSHA area office decide, for each severe injury report, whether
# to send an inspector or a letter.**
#
# IE5374 Applied Generative AI, final project of Seven Team-5374: Quoc Hung Le (Kevin), Hamad Al
# Sulaimi, Khoa Tran. Code: [github.com/lequo-neu/safereport-crew](https://github.com/lequo-neu/safereport-crew).
#
# **How to run this notebook.** Choose *Runtime > Run all*. One cell asks you to upload OSHA's
# public data file (step 6 explains how to get it). Everything else runs by itself.
#
# **Cost and keys.** The notebook is offline. No API key is read or needed, and no model is
# called: every model step is answered by the project's fixed offline rules, and the notebook
# checks this before it runs the crew. Nothing costs money.
#
# | Part | What it shows | Owner |
# |---|---|---|
# | 1 to 8 | the problem, the seven agents, install, OSHA data, building the data and indexes | Hamad |
# | 9 to 16 | one real week of Texas reports run through the seven agents, step by step | Hamad |
# | 17 | the model router: accuracy per model and step, and why each step goes where it goes | Khoa |
# | 18 | the evaluation numbers, read from `eval/results/` | Khoa |
# | 19 | edge cases the system handles | Khoa |
# | 20 | summary | together |

# %% [markdown]
# ## 1. The problem
#
# When a US worker is hospitalized, loses a limb or loses an eye at work, the employer must report it
# to OSHA within 24 hours. Each report is a short free-text story ("an employee's hand was pulled
# into the rollers while clearing a jam"). For every report, an OSHA area office chooses between:
#
# * an **on-site inspection**: an inspector visits. Inspector days are scarce; or
# * an **RRI letter** (Rapid Response Investigation): the employer investigates and replies within
#   five working days.
#
# Some reports *must* be inspected under OSHA's **Category 1** rules (for example two or more workers
# hospitalized, or a hazard covered by a National Emphasis Program). The rest compete for the
# inspector days left. Today staff read every story, look up the employer's history and search the
# regulations by hand.
#
# SafeReport Crew does that reading, checking and planning, then hands a **proposed** list to a
# person, who approves it or asks for changes. Nothing is sent without that approval.

# %% [markdown]
# ## 2. The seven agents, and why each one exists
#
# The crew is a [LangGraph](https://langchain-ai.github.io/langgraph/) graph. Each agent does one job
# that a person in the area office does today, and passes a structured result to the next one.
#
# | Agent | Kind | What it does | Why it is a separate agent |
# |---|---|---|---|
# | **Planner** | reasoning | splits the request into tasks and asks for what is missing (for example the state) | a vague request must not be guessed; asking is cheaper than a wrong week |
# | **Intake** | reasoning | reads each story: activity, hazard, injury, an OSHA event code with a confidence, and the facts the story leaves out | every later step depends on what happened, read the same way each time |
# | **Standards** | retrieval | searches the federal regulations (29 CFR 1910 from eCFR) and cites the section and paragraph | an inspection or letter must name the rule; it comes from the official text, not from memory |
# | **Analyst** | data | the employer's past reports, similar past injuries, how common the hazard is in the industry | a repeat report from the same employer within a year is a Category 1 reason to inspect |
# | **Optimizer** | optimization | applies Category 1 first, then an integer program (PuLP) spends the inspector days left | choosing which reports get the scarce days is a budget problem, solved exactly |
# | **Writer** | generation | the summary and the RRI letters; every number is a placeholder filled from a ledger of recorded facts | text is where a model would invent numbers; here it cannot |
# | **Decision critic** | checking | checks each citation against eCFR and OSHA's own rules, each number and the plan rules, and sends work back | a second, independent check before a person sees the list |
#
# **Two stages.** Stage 1 codes every report of the week with fast rules and a trained classifier,
# without a model. Only reports that are unclear, severe or close to the cut go to stage 2, where
# Intake, Standards and Analyst run on each of them in parallel branches. Part 16 counts how many
# went each way in the week shown here.

# %% [markdown]
# ## 3. Settings
#
# The only cell you may want to edit.
#
# * `REPO_REF` pins the exact version of the code, so the notebook gives the same results every
#   time. It is a commit of `main`; it becomes the release tag once the team tags the hand-in
#   version.
# * `USE_EMBEDDINGS = False` builds a keyword (BM25) search only, which is quick on a free Colab
#   CPU. `True` adds a small embedding model (BAAI/bge-small-en-v1.5) to the regulation search and
#   the similar injury search. It needs a few hundred MB and takes much longer on a CPU; a GPU
#   runtime helps. The results then differ from the BM25 run.
# * `DATA_SOURCE` is `"upload"` (a file picker) or `"drive"` (a file in your Google Drive).

# %%
REPO_URL = "https://github.com/lequo-neu/safereport-crew.git"
# The commit of main on 24 November 2026; replace it with the release tag once the team tags one.
REPO_REF = "fc755be90fbafbb8ec0333741d2279d459ca2ac6"
USE_EMBEDDINGS = False
DATA_SOURCE = "upload"  # "upload" or "drive"
DRIVE_FILE = "/content/drive/MyDrive/January2015toNovember2025.zip"  # used when DATA_SOURCE == "drive"

# %% [markdown]
# ## 4. Check the runtime
#
# The project supports Python 3.11 to 3.13. This cell also removes any model API key variables from
# this session, so no step below can reach a paid model even by mistake. It prints only how many it
# removed, never a value.

# %%
import os
from pathlib import Path
import subprocess
import sys


IN_COLAB = "google.colab" in sys.modules  # Colab loads it when the runtime starts
if not (3, 11) <= sys.version_info[:2] <= (3, 13):
    raise RuntimeError(f"SafeReport needs Python 3.11 to 3.13; this runtime has {sys.version.split()[0]}")

# On a local machine (used by the team's tests), these environment variables point at a folder.
WORK_DIR = (
    Path("/content") if IN_COLAB else Path(os.environ.get("SAFEREPORT_NOTEBOOK_WORKDIR", "notebook_work"))
)
WORK_DIR = WORK_DIR.resolve()
WORK_DIR.mkdir(parents=True, exist_ok=True)
REPO_URL = os.environ.get("SAFEREPORT_NOTEBOOK_REPO_URL", REPO_URL)
REPO_DIR = WORK_DIR / "safereport-crew"

KEY_VARIABLES = [
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
]
removed = [name for name in KEY_VARIABLES if os.environ.pop(name, None) is not None]
print(f"Python {sys.version.split()[0]}, {'Google Colab' if IN_COLAB else 'local machine'}")
print(f"Working folder: {WORK_DIR}")
print(f"Model API key variables removed from this session: {len(removed)}")

# %% [markdown]
# ## 5. Install SafeReport Crew at the pinned version
#
# This clones the public repository and checks out `REPO_REF`. On Colab it then installs the package
# and its dependencies with pip (a few minutes). The `models` extra, which holds the paid model
# clients, is **not** installed.
#
# If Colab shows *"You must restart the runtime"* after the install, choose *Runtime > Restart
# session* and run all again: the clone and install are skipped the second time.


# %%
def run(*command: str, cwd: Path | None = None) -> None:
    """Run a command, print its output as it comes, and stop the notebook if it fails."""
    process = subprocess.Popen(
        command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=child_env()
    )
    for line in process.stdout:
        print(line, end="")
    if process.wait() != 0:
        raise RuntimeError(f"failed with exit code {process.returncode}: {' '.join(command)}")


def child_env() -> dict[str, str]:
    """The environment for commands: no API keys, and the pinned source first on the path."""
    env = {k: v for k, v in os.environ.items() if k not in KEY_VARIABLES}
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO_DIR / "src"), env.get("PYTHONPATH", "")]))
    return env


if not (REPO_DIR / ".git").exists():
    run("git", "clone", "--quiet", REPO_URL, str(REPO_DIR))
run("git", "fetch", "--quiet", "origin", cwd=REPO_DIR)
run("git", "-c", "advice.detachedHead=false", "checkout", "--quiet", "--detach", REPO_REF, cwd=REPO_DIR)
COMMIT = subprocess.run(
    ["git", "rev-parse", "HEAD"], cwd=REPO_DIR, capture_output=True, text=True, check=True
).stdout.strip()

extras = "[embeddings]" if USE_EMBEDDINGS else ""
marker = REPO_DIR / f".notebook_installed_{COMMIT[:12]}{extras}"
if IN_COLAB and not marker.exists():
    run(sys.executable, "-m", "pip", "install", "--quiet", "-e", f"{REPO_DIR}{extras}")
    marker.touch()
elif not IN_COLAB:
    print("Local machine: the dependencies of the current environment are used; nothing is installed.")

# The kernel was started before the install, so put the pinned source first on its path.
sys.path.insert(0, str(REPO_DIR / "src"))
import safereport


print(f"SafeReport {safereport.__version__} at commit {COMMIT[:12]} from {Path(safereport.__file__).parent}")
assert Path(safereport.__file__).resolve().is_relative_to(REPO_DIR.resolve()), (
    "safereport is not the pinned copy"
)

# %% [markdown]
# ## 6. Load OSHA's severe injury reports
#
# The data is OSHA's public **Severe Injury Reports** file (January 2015 to November 2025). OSHA's
# site blocks scripted downloads, so get it in a browser once:
#
# 1. Open <https://www.osha.gov/severe-injury-reports>.
# 2. Click **Download the full SIR data set**. You get `January2015toNovember2025.zip` (about 16 MB).
# 3. Run the next cell and choose that file in the picker (or set `DATA_SOURCE = "drive"` and put the
#    file at `DRIVE_FILE` in your Google Drive).
#
# The zip or the CSV inside it are both accepted. The cell only reads the one expected CSV from the
# zip, checks its columns, and skips the upload when the file is already in place.

# %%
import csv
import hashlib
import shutil
import zipfile

from safereport.data import COLUMNS  # the columns the project reads from OSHA's file


CSV_NAME = "January2015toNovember2025.csv"
RAW_DIR = REPO_DIR / "data" / "raw"
RAW_CSV = RAW_DIR / CSV_NAME


def install_osha_file(source: Path) -> None:
    """Copy the CSV, or extract it from OSHA's zip, into data/raw of the pinned copy."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print(
        f"{source.name}: {source.stat().st_size / 1e6:.1f} MB, sha256 {hashlib.sha256(source.read_bytes()).hexdigest()[:16]}..."
    )
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            members = [m for m in archive.infolist() if Path(m.filename).name == CSV_NAME]
            if len(members) != 1:
                raise ValueError(f"the zip does not hold {CSV_NAME}; is it OSHA's full SIR data set?")
            if members[0].file_size > 500e6:
                raise ValueError("the CSV in the zip is unexpectedly large; refusing to extract it")
            with archive.open(members[0]) as src, RAW_CSV.open("wb") as dst:
                shutil.copyfileobj(src, dst)
    elif source.suffix.lower() == ".csv":
        shutil.copyfile(source, RAW_CSV)
    else:
        raise ValueError("expected OSHA's .zip or the .csv inside it")


def find_osha_file() -> Path:
    if not IN_COLAB:
        return Path(os.environ["SAFEREPORT_NOTEBOOK_DATA"])
    if DATA_SOURCE == "drive":
        from google.colab import drive

        drive.mount("/content/drive")
        return Path(DRIVE_FILE)
    from google.colab import files

    uploaded = files.upload()
    if len(uploaded) != 1:
        raise ValueError("upload exactly one file: OSHA's zip or its CSV")
    name, content = next(iter(uploaded.items()))
    path = WORK_DIR / "upload" / Path(name).name
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(content)
    return path


if RAW_CSV.exists():
    print(f"{CSV_NAME} is already in place; skipping the upload.")
else:
    install_osha_file(find_osha_file())

with RAW_CSV.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
    header = next(csv.reader(handle))
missing = set(COLUMNS) - {name.strip() for name in header}
if missing:
    RAW_CSV.unlink()
    raise ValueError(f"this is not OSHA's SIR file; missing columns {sorted(missing)}. Run the cell again.")
print(f"{RAW_CSV.relative_to(REPO_DIR)}: {RAW_CSV.stat().st_size / 1e6:.1f} MB, columns checked")

# %% [markdown]
# ## 7. Build the data and the indexes
#
# These are the project's own commands (`safereport <command>`, see the README quick start), run in
# order. Each one is skipped when its output already exists, so running the notebook again is quick.
#
# | Command | What it builds |
# |---|---|
# | `build-data` | `reports.parquet`: every report with clean columns, and the fixed 2025 holdout split |
# | `fetch-ecfr` | the text of 29 CFR 1910 as of a fixed date, from the public eCFR API (no key) |
# | `build-index` | the search indexes over the regulations and OSHA's emphasis programs (`--no-dense`: BM25 only) |
# | `train-baseline` | the stage 1 event coder (TF-IDF and logistic regression), trained outside the holdout |
# | `check` | lists the model settings and what is built |

# %%
import json
import time


def safereport_cli(*args: str) -> None:
    started = time.perf_counter()
    print(f"$ safereport {' '.join(args)}")
    run(sys.executable, "-m", "safereport.cli", *args, cwd=REPO_DIR)
    print(f"({time.perf_counter() - started:.0f} s)\n")


def index_matches_setting() -> bool:
    manifest = REPO_DIR / "indexes" / "manifest.json"
    return (
        manifest.exists() and bool(json.loads(manifest.read_text()).get("embedding_model")) == USE_EMBEDDINGS
    )


steps = [
    (["build-data"], REPO_DIR / "data" / "processed" / "reports.parquet"),
    (["fetch-ecfr"], REPO_DIR / "data" / "raw" / "ecfr" / "title-29-part-1910.xml"),
    (["build-index"] + ([] if USE_EMBEDDINGS else ["--no-dense"]), None),
    (["train-baseline"], REPO_DIR / "indexes" / "event_baseline.joblib"),
]
for args, output in steps:
    done = index_matches_setting() if output is None else output.exists()
    if done:
        print(f"safereport {args[0]}: already built, skipped")
    else:
        safereport_cli(*args)
safereport_cli("check")

# %% [markdown]
# ## 8. A first look at the data
#
# Counted from the built file, not typed in: how many reports there are, how many OSHA inspected, and
# how the reports are split. The **holdout** is 1,000 reports of 2025 kept aside for the final
# evaluation; no rule or threshold is tuned on them.

# %%
from IPython.display import Markdown, display
import pandas as pd


reports = pd.read_parquet(REPO_DIR / "data" / "processed" / "reports.parquet")
inspected = reports["inspected"].astype(bool)
display(
    Markdown(
        f"**{len(reports):,} reports**, {reports['event_date'].min()} to {reports['event_date'].max()}. "
        f"OSHA inspected {inspected.sum():,} of them ({inspected.mean():.1%})."
    )
)
display(reports.groupby("split").size().rename("reports").to_frame())
by_year = reports.groupby("year").agg(reports=("id", "size"), inspected=("inspected", "mean"))
by_year["inspected"] = (by_year["inspected"] * 100).round(1).astype(str) + "%"
display(by_year.T)
