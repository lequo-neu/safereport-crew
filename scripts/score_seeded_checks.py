"""Evaluate seeded citation errors using existing offline checks.

Run:
    python scripts/score_seeded_checks.py

The frozen seeds are evaluated without changing the answer key
or tuning the domain rules. No model API calls are made.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from safereport import offline
from safereport.domain import check_citation
from safereport.ecfr import ECFR_DIR, CitationIndex, parse_part
from safereport.evaluation import wilson
from safereport.schemas import IntakeResult


ROOT = Path(__file__).resolve().parents[1]
KEY = ROOT / "data/labels/answer_key.csv"
SEEDS = ROOT / "data/labels/seeded_errors.csv"
OUT = ROOT / "eval/results/seeded_checks.json"

KEY_HASH = "59e869da67c085b7151d24ca35095ec3a560a947b8d8c1eed390602f59be2be8"

SEED_HASH = "9c603ea327c42ca648c22e14f73f7edbe18834f7594192148cebf3fb09eb68fd"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path: Path) -> list[dict]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def rate(k: int, n: int) -> dict:
    return {
        "hits": k,
        "total": n,
        "rate": k / n if n else None,
        "ci95": wilson(k / n, n) if n else None,
    }


def intake_facts(row: dict) -> IntakeResult:
    return IntakeResult.model_validate(
        offline.intake(
            {
                "report_id": row["sir_id"],
                "narrative": row["narrative"],
                "event_title": row["event"],
            }
        )
    )


def citation_issues(
    facts: IntakeResult,
    primary: str,
    secondary: str,
    citations: CitationIndex,
    naics: str = "31",
) -> list[dict]:
    issues = []

    for issue in check_citation(facts, primary, secondary, naics):
        issues.append(
            {
                "rule": issue.rule,
                "message": issue.message,
                "suggestion": issue.suggestion,
                "fix": issue.fix,
            }
        )

    # Wrong regulatory parts are checked by the domain rule.
    # Do not treat a missing Part 1926 XML file as proof that
    # a construction citation does not exist.
    for citation in (primary, secondary):
        if citation and citation.startswith("1910.") and not citations.exists(citation):
            issues.append(
                {
                    "rule": "unknown_citation",
                    "message": f"{citation} is not in the eCFR index",
                    "suggestion": "",
                    "fix": True,
                }
            )

    return issues


def score_seed(seed: dict, reference: dict, citations) -> dict:
    facts = intake_facts(reference)

    issues = citation_issues(
        facts,
        seed["seeded_primary"],
        seed["seeded_secondary"],
        citations,
    )

    expected = seed["expected_rule"]

    matches = [issue for issue in issues if issue["rule"] == expected]

    caught = any(issue["fix"] for issue in matches)
    flagged = bool(matches) and not caught

    return {
        **seed,
        "expected_rule_detected": bool(matches),
        "caught": caught,
        "flagged_for_person": flagged,
        "any_issue": bool(issues),
        "actual_rules": [issue["rule"] for issue in issues],
        "issues": issues,
        "intake": facts.model_dump(mode="json"),
    }


def score_reference(reference: dict, citations) -> dict:
    facts = intake_facts(reference)

    issues = citation_issues(
        facts,
        reference["primary_standard"],
        "",
        citations,
    )

    return {
        "case": reference["case"],
        "sir_id": reference["sir_id"],
        "primary": reference["primary_standard"],
        "wrongly_rejected": bool(issues),
        "automatic_fix_requested": any(issue["fix"] for issue in issues),
        "issues": issues,
        "intake": facts.model_dump(mode="json"),
    }


def summarize(rows: list[dict]) -> dict:
    n = len(rows)

    return {
        "expected_rule_detection": rate(sum(r["expected_rule_detected"] for r in rows), n),
        "caught": rate(sum(r["caught"] for r in rows), n),
        "flagged_for_person": rate(sum(r["flagged_for_person"] for r in rows), n),
        "missed_expected_rule": rate(sum(not r["expected_rule_detected"] for r in rows), n),
        "any_issue": rate(sum(r["any_issue"] for r in rows), n),
    }


def main() -> None:
    if digest(KEY) != KEY_HASH:
        raise ValueError("Original answer key has changed")

    if digest(SEEDS) != SEED_HASH:
        raise ValueError("Frozen seeded errors have changed")

    references = read_rows(KEY)
    seeds = read_rows(SEEDS)

    key = {row["case"]: row for row in references}

    eligible = [row for row in references if row["primary_standard"].strip()]

    if len(references) != 60 or len(eligible) != 51:
        raise ValueError("Unexpected reference denominator")

    if len(seeds) != 24:
        raise ValueError("Expected 24 frozen seeds")

    if len({row["case"] for row in seeds}) != len(seeds):
        raise ValueError("Duplicate seeded cases")

    for seed in seeds:
        original = key[seed["case"]]

        if seed["sir_id"] != original["sir_id"] or seed["true_primary"] != original["primary_standard"]:
            raise ValueError(f"Reference mismatch: {seed['case']}")

    xml_files = sorted(ECFR_DIR.glob("title-29-part-*.xml"))

    if not (ECFR_DIR / "title-29-part-1910.xml").is_file():
        raise FileNotFoundError("Part 1910 eCFR XML is missing")

    citations = CitationIndex([paragraph for xml in xml_files for paragraph in parse_part(xml)])

    if not citations.exists("1910.147"):
        raise ValueError("Citation index failed integrity check")

    if citations.exists("1910.999(z)"):
        raise ValueError("Invented citation unexpectedly exists")

    seeded = [score_seed(seed, key[seed["case"]], citations) for seed in seeds]

    correct = [score_reference(reference, citations) for reference in eligible]

    by_rule = {
        rule: summarize([row for row in seeded if row["expected_rule"] == rule])
        for rule in sorted({row["expected_rule"] for row in seeded})
    }

    rejected = [row for row in correct if row["wrongly_rejected"]]

    result = {
        "evaluation": "B6 seeded citation errors",
        "mode": "offline",
        "paid_api_calls": 0,
        "facts_source": "safereport.offline.intake",
        "seed_sha256": digest(SEEDS),
        "answer_key_sha256": digest(KEY),
        "reference_reports": len(references),
        "reference_with_standard": len(eligible),
        "seeded_reports": len(seeds),
        "naics_assumption": "Manufacturing (31)",
        "ecfr_files": {xml.name: digest(xml) for xml in xml_files},
        "overall": summarize(seeded),
        "by_rule": by_rule,
        "false_rejection": rate(len(rejected), len(correct)),
        "misses": [row for row in seeded if not row["expected_rule_detected"]],
        "false_rejections": rejected,
        "seeded_per_case": seeded,
        "reference_per_case": correct,
        "limitations": [
            "Purposeful stress-test sample, not population accuracy.",
            "Detection does not establish successful correction.",
            "Accepted alternative sections are not treated as simultaneously required secondary citations.",
            "Citation existence checks are restricted to Part 1910; wrong_part checks regulatory scope.",
        ],
    }

    # Post-evaluation review: explanations, not changes to the rules.
    explanations = {
        "C02": ("Offline Intake interpreted sting as a bite hazard rather than an explosive hazard."),
        "C14": ("Offline Intake classified the press as the hazard instead of the same-level trip and fall."),
        "C27": (
            "Offline Intake classified normal machine operation as setup, triggering the energy-control rule."
        ),
        "C32": (
            "Offline Intake interpreted caught as machine entanglement rather than a trip involving a cart."
        ),
    }

    automatic = sum(row["automatic_fix_requested"] for row in rejected)

    result["false_rejection_breakdown"] = {
        "automatic_fix_requested": rate(automatic, len(correct)),
        "human_review_only": rate(len(rejected) - automatic, len(correct)),
    }

    result["false_rejection_analysis"] = [
        {
            "case": row["case"],
            "rules": [issue["rule"] for issue in row["issues"]],
            "intake_confidence": row["intake"]["confidence"],
            "automatic_fix_requested": row["automatic_fix_requested"],
            "interpretation": explanations.get(row["case"], "Requires separate human review."),
        }
        for row in rejected
    ]

    result["evaluation_scope"] = {
        "seed_selection": "Targeted, AI-assisted stress test",
        "primary_seeds": sum(bool(row["seeded_primary"]) for row in seeds),
        "secondary_seeds": sum(bool(row["seeded_secondary"]) for row in seeds),
        "seeds_without_reference_standard": sum(not row["true_primary"] for row in seeds),
        "independent_holdout": False,
        "confidence_note": (
            "Offline Intake receives no baseline confidence in this evaluation, so 0.5 is its default value."
        ),
        "scope_note": (
            "Measures citation-check detection and correction "
            "eligibility, not end-to-end correction accuracy."
        ),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n")

    print("=== B6 OVERALL RESULTS ===")
    print(json.dumps(result["overall"], indent=2))

    print("\n=== RESULTS BY RULE ===")
    for rule, metrics in by_rule.items():
        print(rule, json.dumps(metrics["expected_rule_detection"]))

    print("\n=== FALSE REJECTION ===")
    print(json.dumps(result["false_rejection"], indent=2))

    print("\n=== MISSED EXPECTED RULES ===")
    for row in result["misses"]:
        print(
            row["case"],
            row["expected_rule"],
            row["actual_rules"],
        )

    print("\n=== FALSE REJECTION CASES ===")
    for row in rejected:
        print(
            row["case"],
            row["primary"],
            [issue["rule"] for issue in row["issues"]],
        )

    print("\nSaved:", OUT)
    print("No paid API calls.")


if __name__ == "__main__":
    main()
