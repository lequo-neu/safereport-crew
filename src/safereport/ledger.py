"""Numbers in an answer come from tools, never from a model.

Tools record each value they compute as a fact. A draft refers to facts by placeholder, for
example "{{reports_2025}} reports", and `render` fills in the value. The critic then checks
the draft template for digits that came from nowhere: any number outside a placeholder, other
than a CFR citation or a directive number, is untraced and sends the draft back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re


PLACEHOLDER = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")
# Numbers that are names, not quantities: CFR citations, directive and code identifiers.
NAMED_NUMBERS = re.compile(
    r"\b(?:19(?:10|26)\.\d+(?:\([A-Za-z0-9]+\))*|CPL \d{2}-\d{2}-\d{3}|OSH Act 5\(a\)\(1\)|5\(a\)\(1\)"
    r"|Category [123]|OIICS [23])"
)
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


@dataclass
class Fact:
    value: object
    source: str
    # The period a count covers; the critic refuses a comparison of unequal periods.
    period: str = ""
    same_months: bool = True

    def text(self) -> str:
        if isinstance(self.value, float):
            return f"{self.value:.1%}" if abs(self.value) <= 1 else f"{self.value:,.1f}"
        if isinstance(self.value, int):
            return f"{self.value:,}"
        return str(self.value)


@dataclass
class FactLedger:
    facts: dict[str, Fact] = field(default_factory=dict)

    def add(self, key: str, value: object, source: str, period: str = "", same_months: bool = True) -> str:
        if not re.fullmatch(r"[a-z0-9_]+", key):
            raise ValueError(f"fact keys are lower case words with underscores: {key!r}")
        self.facts[key] = Fact(value, source, period, same_months)
        return "{{" + key + "}}"

    def render(self, template: str) -> str:
        def fill(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in self.facts:
                raise KeyError(f"the draft uses an unknown fact {key!r}")
            return self.facts[key].text()

        return PLACEHOLDER.sub(fill, template)

    def untraced(self, template: str) -> list[str]:
        """Numbers written into the template by hand rather than taken from a fact."""
        bare = NAMED_NUMBERS.sub(" ", PLACEHOLDER.sub(" ", template))
        return NUMBER.findall(bare)

    def unknown(self, template: str) -> list[str]:
        return [key for key in PLACEHOLDER.findall(template) if key not in self.facts]

    def unequal_periods(self, template: str) -> list[str]:
        """Facts in the template that compare a partial year with a full one."""
        return [
            key
            for key in PLACEHOLDER.findall(template)
            if key in self.facts and not self.facts[key].same_months
        ]
