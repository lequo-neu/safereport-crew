"""Facts read from a narrative by fixed rules, for OSHA's triage factors.

These run on every report in stage 1 without a model, and the proposal's figures come from
them, so each rule is written down here once. The patterns are deliberately narrow: the word
"temporary" alone also appears in "temporary repairs" and "temporary platform".
"""

from __future__ import annotations

import re


# OSHA lists "temporary workers or other vulnerable employees" among the Category 2 factors.
TEMPORARY_WORKER = re.compile(r"\btemporary (?:employee|worker)|\btemp worker|staffing agency", re.IGNORECASE)


def mentions_temporary_worker(narrative: str) -> bool:
    return bool(TEMPORARY_WORKER.search(narrative))


# A safeguard that was off or missing: OSHA's Category 2 factor "safety program failure".
# 946 narratives match, and 79.7% of them were inspected.
FAILED_SAFEGUARD = re.compile(
    r"\bnot (?:been )?(?:locked|tagged)[ /-]*(?:out|and tagged)|\bwithout (?:locking|lockout|lock ?out)|\bno lockout"
    r"|\b(?:guard|guarding) (?:was |had been )?(?:removed|missing|bypassed|not in place)|\bno guard|\bunguarded",
    re.IGNORECASE,
)

# A worker's age under 18 stated next to the worker. OSHA reports rarely give ages: on the whole
# file a looser pattern matched one narrative, and the 14 year old there was a patient, not a
# worker. So the Category 1 "worker under 18" criterion mostly comes from a user rule.
MINOR_WORKER = re.compile(
    r"\b1[4-7][- ]year[- ]old (?:employee|worker|laborer|male employee|female employee)\b", re.IGNORECASE
)


def mentions_failed_safeguard(narrative: str) -> bool:
    return bool(FAILED_SAFEGUARD.search(narrative))


def mentions_minor_worker(narrative: str) -> bool:
    return bool(MINOR_WORKER.search(narrative))
