"""The records that move between agents.

Every agent returns one of these models, so a malformed model reply is caught at the step
that produced it, and the critic can trust field types when it checks a draft.
"""

from __future__ import annotations

from datetime import date, datetime
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# A CFR citation in our format, for example 1910.212(a)(3)(ii) or 1926.501(b)(1).
CITATION = re.compile(r"^(1910|1926)\.\d+(\([A-Za-z0-9]+\))*$")
# An OSHA directive, which is how an emphasis program is cited: CPL 03-00-027.
DIRECTIVE = re.compile(r"^CPL \d{2}-\d{2}-\d{3}$")
GENERAL_DUTY = "OSH Act 5(a)(1)"

Activity = Literal["normal operation", "cleaning", "unjamming", "servicing", "setup", "other", "unknown"]
# The kind of hazard, which decides the family of standards (see docs/LABELING_GUIDE.md).
HazardType = Literal[
    "machine", "fall_height", "ladder", "same_level", "powered_truck", "other_vehicle", "struck_by_object",
    "crane_load", "electrical", "chemical", "hot_substance", "heat", "overexertion", "violence", "bite", "fire", "other",
]  # fmt: skip
Confidence = Literal["high", "medium", "low"]


def cfr_section(citation: str) -> str:
    """The section a citation belongs to: 1910.212(a)(1) is 1910.212."""
    match = re.match(r"^(\d{4}\.\d+)", citation.strip())
    return match.group(1) if match else ""


def _whole_number(value: str) -> int:
    return int(float(value)) if value and value.strip() else 0


class Report(BaseModel):
    """One OSHA severe injury report, with the columns the agents use."""

    id: str
    event_date: date
    employer: str
    address: str = ""
    city: str = ""
    state: str
    zip: str = ""
    naics: str
    hospitalized: int = Field(ge=0)
    amputation: int = Field(ge=0)
    loss_of_eye: int = Field(ge=0)
    inspection: str = ""
    narrative: str
    event_code: str
    event_title: str
    source_code: str
    source_title: str
    nature_title: str = ""
    body_part_title: str = ""

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> Report:
        """Map a row of OSHA's CSV, whose headers have spaces and capitals, to a Report."""
        return cls(
            id=row["ID"].strip(),
            event_date=datetime.strptime(row["EventDate"].split()[0], "%m/%d/%Y").date(),
            employer=row["Employer"].strip(),
            address=" ".join(
                p.strip() for p in (row.get("Address1", ""), row.get("Address2", "")) if p.strip()
            ),
            city=row.get("City", "").strip(),
            state=row["State"].strip(),
            zip=row.get("Zip", "").strip(),
            naics=row["Primary NAICS"].strip(),
            hospitalized=_whole_number(row["Hospitalized"]),
            amputation=_whole_number(row["Amputation"]),
            loss_of_eye=_whole_number(row["Loss of Eye"]),
            inspection=row.get("Inspection", "").strip(),
            narrative=" ".join(row["Final Narrative"].split()),
            event_code=row["Event"].strip(),
            event_title=row["EventTitle"].strip(),
            source_code=row["Source"].strip(),
            source_title=row["SourceTitle"].strip(),
            nature_title=row.get("NatureTitle", "").strip(),
            body_part_title=row.get("Part of Body Title", "").strip(),
        )

    @property
    def inspected(self) -> bool:
        return bool(self.inspection)

    @property
    def is_manufacturing(self) -> bool:
        return self.naics.startswith(("31", "32", "33"))


class Span(BaseModel):
    """Words of the narrative that support one extracted fact, as character offsets."""

    label: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def _ordered(self) -> Span:
        if self.end <= self.start:
            raise ValueError("a span must end after it starts")
        return self

    def text_in(self, narrative: str) -> str:
        return narrative[self.start : self.end]


class IntakeResult(BaseModel):
    """What the Intake agent reads out of one narrative."""

    report_id: str
    activity: Activity
    hazard_type: HazardType = "other"
    machine_or_hazard: str
    material: str = ""
    injury: str
    event_code: str
    source_code: str = ""
    confidence: float = Field(ge=0, le=1)
    fatality_potential: bool
    missing_facts: list[str] = Field(default_factory=list)
    spans: list[Span] = Field(default_factory=list)

    def spans_outside(self, narrative: str) -> list[Span]:
        """Spans that point past the end of the narrative; a model that invents offsets fails here."""
        return [s for s in self.spans if s.end > len(narrative)]


class Citation(BaseModel):
    """A standard the Standards agent proposes, with the official words it rests on."""

    citation: str
    quote: str = ""
    source: Literal["1910", "1926", "general_duty", "emphasis_program"]
    score: float = 0.0

    @model_validator(mode="after")
    def _format(self) -> Citation:
        self.citation = self.citation.strip()
        if self.source == "general_duty":
            ok = self.citation == GENERAL_DUTY
        elif self.source == "emphasis_program":
            ok = bool(DIRECTIVE.match(self.citation))
        else:
            ok = bool(CITATION.match(self.citation)) and self.citation.startswith(self.source)
        if not ok:
            raise ValueError(f"not a {self.source} citation in our format: {self.citation!r}")
        return self

    @property
    def section(self) -> str:
        if self.source in ("general_duty", "emphasis_program"):
            return self.citation
        return cfr_section(self.citation)


class AnswerKeyCase(BaseModel):
    """One row of data/labels/answer_key.csv."""

    case: str = Field(pattern=r"^C\d{2}$")
    sir_id: str
    narrative: str
    event: str
    source: str
    primary_standard: str
    primary_section: str
    accepted_sections: list[str]
    no_standard_reason: str
    confidence: Confidence
    labelers: list[str]
    status: Literal[
        "both agreed", "settled by the team", "single labeler", "corrected, pending team confirmation"
    ]

    @field_validator("accepted_sections", "labelers", mode="before")
    @classmethod
    def _split(cls, value: object) -> object:
        if isinstance(value, str):
            return [part for part in value.split(";") if part]
        return value

    @model_validator(mode="after")
    def _consistent(self) -> AnswerKeyCase:
        if self.primary_standard:
            if not CITATION.match(self.primary_standard):
                raise ValueError(f"{self.case}: bad citation {self.primary_standard!r}")
            if cfr_section(self.primary_standard) != self.primary_section:
                raise ValueError(f"{self.case}: primary_section does not match the citation")
            if self.primary_section not in self.accepted_sections:
                raise ValueError(f"{self.case}: the primary section must count as a hit")
        elif not self.no_standard_reason:
            raise ValueError(f"{self.case}: a case without a standard needs a reason")
        return self

    @property
    def has_standard(self) -> bool:
        return bool(self.primary_standard)
