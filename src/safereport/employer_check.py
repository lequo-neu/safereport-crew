"""The hand check of employer matching: draw name pairs, let people label them, score the rule.

"same" pairs are different spellings that normalize to one name in a state; the matcher counts
them as the same employer, and a repeat among them can force an inspection. "possible" pairs are
near names the matcher leaves for a person. The team fills `same_employer` with yes or no in
data/labels/employer_pairs_check.csv; `score` then reports the precision of the "same" rule and
how many possible pairs really were one employer.
"""

from __future__ import annotations

import csv
from pathlib import Path
import random

from rapidfuzz import fuzz, process

from safereport.config import PROJECT_ROOT
from safereport.data import ReportStore
from safereport.employers import POSSIBLE_NAME, normalize_name


PAIRS_FILE = PROJECT_ROOT / "data" / "labels" / "employer_pairs_check.csv"
FIELDS = [
    "pair",
    "rule",
    "state",
    "name_a",
    "name_b",
    "city_a",
    "city_b",
    "naics_a",
    "naics_b",
    "same_employer",
    "notes",
]


def draw_pairs(
    store: ReportStore, same: int = 100, possible: int = 50, seed: int = 42
) -> list[dict[str, str]]:
    rows = store.frame("SELECT DISTINCT state, employer, city, naics FROM reports WHERE employer <> ''")
    rows["norm"] = rows["employer"].map(normalize_name)
    rng = random.Random(seed)  # noqa: S311 (a reproducible sample, not a secret)
    same_pairs, possible_pairs = [], []
    for (state, norm), group in rows.groupby(["state", "norm"]):
        spellings = group.drop_duplicates("employer")
        if norm and len(spellings) > 1:
            a, b = spellings.sample(2, random_state=rng.randint(0, 10**6)).to_dict("records")
            same_pairs.append(("same", state, a, b))
    for state, group in rows.groupby("state"):
        names = group.drop_duplicates("norm")
        norms = names["norm"].tolist()
        for position, name in enumerate(norms[:400]):
            for other, _score, index in process.extract(name, norms[position + 1 :], scorer=fuzz.token_set_ratio,
                                                       score_cutoff=POSSIBLE_NAME, limit=2):  # fmt: skip
                if name != other and min(len(name), len(other)) >= 4:
                    a = names.iloc[position].to_dict()
                    b = names.iloc[position + 1 + index].to_dict()
                    possible_pairs.append(("possible", state, a, b))
    chosen = rng.sample(same_pairs, min(same, len(same_pairs))) + rng.sample(
        possible_pairs, min(possible, len(possible_pairs))
    )
    return [
        {"pair": f"P{n:03d}", "rule": rule, "state": state, "name_a": a["employer"], "name_b": b["employer"],
         "city_a": a["city"], "city_b": b["city"], "naics_a": a["naics"], "naics_b": b["naics"],
         "same_employer": "", "notes": ""}
        for n, (rule, state, a, b) in enumerate(chosen, start=1)
    ]  # fmt: skip


def write_pairs(pairs: list[dict[str, str]], path: Path = PAIRS_FILE) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(pairs)


def score(path: Path = PAIRS_FILE) -> dict[str, object]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    labelled = [r for r in rows if r["same_employer"].strip().lower() in ("yes", "no")]
    result: dict[str, object] = {"pairs": len(rows), "labelled": len(labelled)}
    for rule in ("same", "possible"):
        done = [r for r in labelled if r["rule"] == rule]
        yes = sum(r["same_employer"].strip().lower() == "yes" for r in done)
        result[rule] = {
            "labelled": len(done),
            "really_same": yes,
            "share": round(yes / len(done), 3) if done else None,
        }
    return result
