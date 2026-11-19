"""Replace employer names, addresses and personal details before text goes to a cloud model.

OSHA already writes "an employee" instead of the worker's name, but about 150 narratives name
the employer, and a narrative a user pastes in may name anyone. People are found by a title
("Dr. José Núñez"), by a role word ("Employee Maria Lopez"), or as two capitalized words that the
narratives never write in lower case ("Maria Lopez fell" becomes "[NAME_1] fell"). A one word
name with no title ("Lopez fell") is not found. Each distinct value gets its own placeholder
such as [EMPLOYER_1]; the mapping stays on this machine, so `restore` puts the real words back
in the model's answer for the office's own views.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
import re

from safereport.employers import LEGAL_WORDS


LETTER = r"[^\W\d_]"  # any letter, accented ones included
NAME = rf"{LETTER}+(?:['-]{LETTER}+)*"
PATTERNS = {
    # A title and one or two names, in any case: "Dr. José Núñez", "MR. SMITH".
    "PERSON": re.compile(rf"\b(?i:mr|mrs|ms|miss|dr)\.?\s+{NAME}(?:\s+(?=[^\W\d_a-z]){NAME})?"),
    "PHONE": re.compile(r"\(?\b\d{3}\)?[-.\s]+\d{3}[-.\s]\d{4}\b"),
    "EMAIL": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"),
}
# Two capitalized words right after a role word, the usual way a pasted narrative names a
# worker without a title: "Employee Maria Lopez fell". Names written any other way need a
# named entity model, which this module does not have.
# Two capitalized words, as in "Maria Lopez fell" or "Memorial Hermann".
NAME_PAIR = re.compile(rf"\b((?=[^\W\d_a-z]){NAME})\s+((?=[^\W\d_a-z]){NAME})\b")
ROLE_NAME = re.compile(
    rf"\b(?i:employee|worker|operator|supervisor|technician|named),?\s+((?=[^\W\d_a-z]){NAME}\s+(?=[^\W\d_a-z]){NAME})"
)
GENERIC_WORDS = LEGAL_WORDS | {
    "services",
    "service",
    "group",
    "industries",
    "international",
    "american",
    "national",
}


@cache
def common_words(path: str = "") -> frozenset[str]:
    """Lower case words of the OSHA narratives (built by `safereport build-data`), or none."""
    from safereport.data import COMMON_WORDS

    file = Path(path) if path else COMMON_WORDS
    return frozenset(file.read_text().split()) if file.exists() else frozenset()


def _employer_variants(employer: str) -> list[str]:
    """The full name, the name without its legal suffix, and its first distinctive word."""
    full = employer.strip()
    if not full:
        return []
    words = re.split(r"[\s,]+", full)
    legal = {word.replace(" ", "") for word in LEGAL_WORDS}
    core = [w for w in words if re.sub(r"[^a-z]", "", w.lower()) not in legal]
    variants = [full, " ".join(core), " ".join(core[:2])]
    first = core[0].strip(".") if core else ""
    if len(first) >= 4 and first.lower() not in GENERIC_WORDS:
        variants.append(first)
    return [v for v in dict.fromkeys(variants) if v]


@dataclass
class Redacted:
    text: str
    mapping: dict[str, str] = field(default_factory=dict)

    def restore(self, text: str) -> str:
        """Put the original words back into any text that uses this mapping's placeholders."""
        for placeholder, original in self.mapping.items():
            text = text.replace(placeholder, original)
        return text


def redact(
    text: str,
    employer: str = "",
    address: str = "",
    city: str = "",
    zip_code: str = "",
    address2: str = "",
    keep: tuple[str, ...] = (),
) -> Redacted:
    """Replace known and pattern matched details; overlapping matches keep the longer one.

    `keep` lists words that stay visible even when a pattern matches them, such as the state names
    a request needs ("Puerto Rico" looks like a name pair to the pattern).
    """
    if re.search(r"\[(EMPLOYER|ADDRESS|CITY|ZIP|PERSON|PHONE|EMAIL|NAME)_\d+\]", text):
        raise ValueError("the text already contains a redaction placeholder")
    found: list[tuple[int, int, str]] = []
    known = [("EMPLOYER", v) for v in _employer_variants(employer)]
    known += [
        (kind, v.strip())
        for kind, v in (("ADDRESS", address), ("ADDRESS", address2), ("ZIP", zip_code))
        if v.strip()
    ]
    if city.strip():
        known.append(("CITY", city.strip()))
    for kind, value in known:
        pattern = rf"(?<!\w){re.escape(value)}(?!\w)"
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            # A one word value such as a city ("Mobile") or a brand ("Tyson") counts only where
            # the text writes it as a name, with a capital, so the word "mobile" stays.
            if " " not in value and value[0].isalpha() and not match.group(0)[0].isupper():
                continue
            found.append((match.start(), match.end(), kind))
    for kind, pattern in PATTERNS.items():
        found += [(m.start(), m.end(), kind) for m in pattern.finditer(text)]
    found += [(m.start(1), m.end(1), "PERSON") for m in ROLE_NAME.finditer(text)]
    # A pair of capitalized words that the narratives never write in lower case is a name of some
    # kind (a person, a hospital, a brand). On the whole file this marks 135 of 105,996 narratives,
    # and a placeholder is cheap, so these are hidden too. Without the word list it is skipped.
    vocabulary = common_words()
    if vocabulary:
        for match in NAME_PAIR.finditer(text):
            if match.group(1).lower() not in vocabulary and match.group(2).lower() not in vocabulary:
                found.append((match.start(), match.end(), "NAME"))

    visible = {word.lower() for word in keep}
    found = [f for f in found if text[f[0] : f[1]].lower() not in visible]
    kept: list[tuple[int, int, str]] = []
    for start, end, kind in sorted(found, key=lambda f: (f[0], -(f[1] - f[0]))):
        if kept and start < kept[-1][1]:
            continue
        kept.append((start, end, kind))

    mapping: dict[str, str] = {}
    by_original: dict[str, str] = {}
    counters: dict[str, int] = {}
    pieces, cursor = [], 0
    for start, end, kind in kept:
        original = text[start:end]
        if original not in by_original:
            counters[kind] = counters.get(kind, 0) + 1
            by_original[original] = f"[{kind}_{counters[kind]}]"
            mapping[by_original[original]] = original
        pieces += [text[cursor:start], by_original[original]]
        cursor = end
    pieces.append(text[cursor:])
    return Redacted("".join(pieces), mapping)
