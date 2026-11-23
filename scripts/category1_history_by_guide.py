"""Criterion 3 of the B3 hand check, as docs/CATEGORY1_LABELING.md writes it, over OSHA's file.

    python scripts/category1_history_by_guide.py --labels data/labels/category1_check.csv \
        --out eval/provisional/category1_history_by_guide.json

For each case: earlier reports in the same state in the 365 days before it, with the employer's
name normalised as the guide says (lower case, & to "and", punctuation dropped, inc, llc and the
like dropped). Confirmed: the same name and the same city or 3-digit NAICS. Possible: a near
spelling, an acronym, one name inside the other, or the same name elsewhere. Similar: the same
first digit of the event code (or no code). The answer is yes (a confirmed, similar report),
cannot_tell (only possible ones), or no.

It is written from the guide's text and does not import `employers.py`, so agreeing with the
crew shows that the code does what the written rule says. It is a machine reading of the rule,
not a person's label: possible matches are left for a person.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import re
from typing import Any

from rapidfuzz import fuzz

from safereport.config import PROJECT_ROOT


RAW = PROJECT_ROOT / "data" / "raw" / "January2015toNovember2025.csv"
DROP = {"inc", "incorporated", "llc", "co", "corp", "corporation", "company", "ltd", "limited", "lp", "llp",
        "plc", "the", "dba"}  # fmt: skip
NEAR = 90  # what counts as a near spelling: the guide gives no number, so this cut is ours


def norm(name: str) -> str:
    """The guide's normalisation. Punctuation is dropped, not spaced, so "U.S." equals "US"."""
    words = re.sub(r"[^a-z0-9\s]", "", name.lower().replace("&", " and ")).split()
    return " ".join(w for w in words if w not in DROP)


def day(text: str) -> date:
    return datetime.strptime(text.strip(), "%m/%d/%Y").date()


def possible(a: str, b: str) -> str:
    """Why two different normalised names may be one employer ('' when they look different)."""
    if a.replace(" ", "") == b.replace(" ", ""):
        return "same letters, different spacing"
    short, long_ = sorted((a, b), key=len)
    if len(short) >= 4 and re.search(rf"\b{re.escape(short)}\b", long_):
        return "one name inside the other"
    if " " not in short and len(short) >= 2 and short == "".join(w[0] for w in long_.split()):
        return "acronym"
    if fuzz.ratio(a, b) >= NEAR:
        return f"near spelling ({fuzz.ratio(a, b):.0f})"
    return ""


def history(case: dict[str, str], event: str, earlier: list[dict[str, str]]) -> dict[str, Any]:
    """The answer for one case, from OSHA rows of the same state (the case itself may be among them)."""
    when, name, digit = day(case["event_date"]), norm(case["employer"]), (event or "")[:1]
    start = when - timedelta(days=365)
    confirmed, maybe, other = [], [], []
    for r in earlier:
        if r["ID"] == case["sir_id"] or not (start <= day(r["EventDate"]) < when):
            continue
        theirs = norm(r["Employer"])
        near = (
            r["City"].strip().upper() == case["city"].strip().upper()
            or r["Primary NAICS"][:3] == case["naics"][:3]
        )
        if theirs == name:
            kind = "confirmed" if near else "possible: same name, another city and another 3-digit NAICS"
        elif why := possible(name, theirs):
            kind = f"possible: {why}"
        else:
            continue
        item = {"id": r["ID"], "date": r["EventDate"], "employer": r["Employer"], "city": r["City"],
                "naics": r["Primary NAICS"], "event": r["Event"], "match": kind}  # fmt: skip
        if r["Event"] and r["Event"][:1] != digit:
            other.append(item)
        elif kind == "confirmed":
            confirmed.append(item)
        else:
            maybe.append(item)
    if confirmed:
        last = max(confirmed, key=lambda i: day(i["date"]))
        label = "yes"
        evidence = f"{last['id']} {last['date']} ({last['employer']}, {last['city']}, event {last['event'] or 'none'})"
    else:
        label, evidence = ("cannot_tell" if maybe else "no"), ""
    return {"label": label, "evidence": evidence, "event_code": event, "confirmed": confirmed,
            "possible": maybe, "same_employer_other_hazard": other}  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--labels", type=Path, default=PROJECT_ROOT / "data" / "labels" / "category1_check.csv"
    )
    parser.add_argument("--raw", type=Path, default=RAW)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cases = list(csv.DictReader(args.labels.open(encoding="utf-8")))
    raw = list(csv.DictReader(args.raw.open(encoding="utf-8-sig", newline="")))
    events = {r["ID"]: r["Event"] for r in raw}
    by_state: dict[str, list[dict[str, str]]] = {}
    for r in raw:
        by_state.setdefault(r["State"].upper(), []).append(r)
    out = {
        c["case"]: history(c, events.get(c["sir_id"], ""), by_state.get(c["state"].upper(), []))
        for c in cases
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1), encoding="utf-8")
    counts = {k: sum(v["label"] == k for v in out.values()) for k in ("yes", "no", "cannot_tell")}
    print(f"wrote {args.out}: {counts}")


if __name__ == "__main__":
    main()
