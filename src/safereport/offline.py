"""Deterministic stand ins for the model steps, so the whole crew runs offline.

Each handler takes the JSON prompt a step sends and returns what a model would: the Planner's
sub tasks, the Intake facts, terms for the Standards search, the Writer's draft. They are fixed
rules, written from our labelling guide, so their scores on the answer key are not a fair test
of anything and are never reported as model results. When the API keys are added, the same
prompts go to the configured models instead.
"""

from __future__ import annotations

from datetime import date
import json
import re
from typing import Any

from safereport.signals import mentions_failed_safeguard


STATES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", "Delaware", "Florida",
    "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine",
    "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska",
    "Nevada", "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio",
    "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota", "Tennessee", "Texas",
    "Utah", "Vermont", "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming", "Puerto Rico",
    "District of Columbia",
]  # fmt: skip
INDUSTRIES = {
    "food manufacturing": "311",
    "plastics": "326",
    "fabricated metal": "332",
    "primary metal": "331",
    "warehous": "493",
    "construction": "23",
    "manufacturing": "3",
}
# Hazard words to an OIICS 3 event group prefix, so trends can cross January 2024.
HAZARDS = {
    "caught in machinery": "653",
    "caught in": "653",
    "struck by": "64",
    "falls to a lower level": "41",
    "falls": "41",
    "slips and trips": "43",
}

ACTIVITY = [
    ("unjamming", r"\bunjam|\bjam(med|s)?\b|clear(ing)? (a |the )?(jam|blockage)|became stuck|got stuck|\bstuck\b"),
    ("cleaning", r"\bclean(ing|ed)?\b|blow(ing)? down|wash(ing)? down"),
    ("servicing", r"maintenance|\brepair|servic(e|ing)|replac(e|ing)|adjust(ing)?|tighten(ing)?|lubricat|greas(e|ing)|remov(e|ing) (a|the) (tool|bolt|nut|part|guard|cover|panel|die)|changing|die change"),
    ("setup", r"setting up|set(ting)? up|\bsetup\b|changeover|threading|installing"),
    ("normal operation", r"operat(ing|ed|e)|running|feeding|\busing\b|cutting|working on|monitoring|loading|unloading"),
]  # fmt: skip
MACHINE_WORDS = (
    r"roller|conveyor|\bsaw\b|\bpress\b|blade|machine|auger|\bgear|\bbelt\b|chain|shear|cutter|mixer|lathe|"
    r"grinder|slitter|airlock|spindle|hydraulic|cylinder|\bmill\b|\bdie\b|winder|extruder|sprocket|pulley"
)
# A moving part hurting someone; with a machine word it settles the hazard as a machine, even when
# the narrative also says that something "slipped" or "dropped".
MACHINE_INJURY = r"caught|crush|amputat|pinch|pulled into|smash|entangl|struck|severed|laceration"
HAZARD_TYPES = [
    ("violence", r"\bshot\b|stabbed|assault|punched|attacked"),
    ("bite", r"\bbit(ten|e)\b|\bsting"),
    ("heat", r"heat (stress|stroke|exhaustion|illness|related)|dehydrat"),
    ("electrical", r"electric|\bshock|arc flash|electrocut|energized"),
    ("fire", r"\bfire\b|explosion|exploded|flash fire|ignit"),
    ("powered_truck", r"forklift|fork lift|pallet jack|powered industrial truck|order picker|reach truck|narrow aisle"),
    ("crane_load", r"\bcrane\b|\bhoist|\bsling\b"),
    ("ladder", r"\bladder\b"),
    ("machine", rf"(?=.*(?:{MACHINE_INJURY}))(?=.*(?:{MACHINE_WORDS}))"),
    ("fall_height", r"(employee|worker|he|she|they) fell (\w+ ){0,4}(from|off)|fall(ing)? (from|off)|\b\d+ (feet|foot|ft)\b.{0,30}\bfell|fell.{0,30}\b\d+ (feet|foot|ft)\b|roof"),
    ("same_level", r"(employee|worker|he|she|they) (slipped|tripped)|\bslipped on\b|\btripped (on|over)\b|lost (his|her|their) (balance|footing)"),
    ("machine", MACHINE_WORDS + r"|caught|pinch"),
    ("other_vehicle", r"front end loader|\btruck\b|vehicle|tractor|trailer|\bcar\b"),
    ("struck_by_object", r"struck by|fell on|falling object|dropped"),
    ("chemical", r"chemical|\bacid\b|caustic|ammonia|chlorine|exposed to|exposure to"),
    ("hot_substance", r"\bhot\b|molten|\bburn(ed|s)?\b|steam|scald"),
    ("overexertion", r"lifting|overexert|strain(ed)?|\blifted\b"),
]  # fmt: skip
MATERIALS = [
    ("wood", r"\bwood|lumber|timber|plywood|board"),
    ("metal", r"\bmetal|steel|rebar|aluminum|iron|pipe"),
    ("food", r"\bfish|meat|poultry|chicken|dough|food"),
    ("plastic", r"plastic|film|resin"),
    ("paper", r"paper|cardboard|corrugated"),
]
TERMS = [
    (r"forklift|fork lift|pallet jack|order picker|reach truck", "powered industrial truck operator"),
    (r"\bjam|clean|servic|maintenance|repair|unjam|setting up|set up|adjust", "servicing maintenance unexpected energization lockout tagout energy control"),
    (r"roller|\bnip\b|rolls", "in-running nip points rotating parts machine guarding"),
    (r"caught|pinch|point of operation|blade|cutter", "point of operation guarding"),
    (r"\bladder\b", "ladder rungs steps side rails"),
    (r"fell (\w+ ){0,4}(from|off)|roof|platform|edge|feet", "fall protection unprotected sides and edges walking-working surfaces"),
    (r"slip|trip", "walking-working surfaces slippery housekeeping"),
    (r"\bpress\b", "mechanical power press point of operation"),
    (r"crane|hoist", "overhead and gantry cranes hoist load"),
    (r"belt|pulley|gear|chain|sprocket|shaft", "mechanical power-transmission apparatus"),
    (r"electric|arc flash|shock", "electrical safety-related work practices energized parts"),
    (r"chemical|acid|caustic|exposure", "hazard communication chemical"),
    (r"\bhot\b|molten|burn|steam", "personal protective equipment"),
    (r"grinder|abrasive", "abrasive wheel machinery"),
]  # fmt: skip


def _find(patterns: list[tuple[str, str]], text: str, default: str) -> tuple[str, re.Match[str] | None]:
    for label, pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return label, match
    return default, None


def plan_request(request: str, today: date | None = None) -> dict[str, Any]:
    """Split a request into sub tasks and list the parameters that are missing."""
    text = request.strip()
    lower = text.lower()
    params: dict[str, Any] = {}
    state = next((s for s in STATES if re.search(rf"\b{s}\b", text, flags=re.IGNORECASE)), "")
    if state:
        params["state"] = state.upper()
    year = re.search(r"\b(since|from|after)\s+(20\d{2})\b", lower)
    if year:
        params["start"] = f"{year.group(2)}-01-01"
    industry = next((code for words, code in INDUSTRIES.items() if words in lower), "")
    if industry:
        params["naics_prefix"] = industry
    hazard = next(((words, code) for words, code in HAZARDS.items() if words in lower), None)
    if hazard:
        params["hazard_label"], params["event_group_v3"] = hazard
    days = re.search(r"(\d+(?:\.\d+)?)\s+inspector days", lower)
    if days:
        params["capacity"] = float(days.group(1))
    budget = re.search(r"\$\s?([\d,]+)", text)

    is_narrative = bool(
        re.match(r"^(an?|the|two|three)\s+(employee|worker|temporary|machinist|operator)", lower)
    ) or (len(text.split()) > 18 and re.search(r"\b(was|were)\b", lower) and "?" not in text)
    tasks: list[dict[str, Any]] = []
    if is_narrative:
        tasks.append({"id": "report", "kind": "single_report", "needs": [], "depends_on": []})
    else:
        if re.search(r"trend|what injures|how many|getting (better|worse)|injuries in|find .*injur", lower):
            tasks.append({"id": "trend", "kind": "trend", "needs": [], "depends_on": []})
        if re.search(r"repeat|more than once|reported before", lower):
            tasks.append(
                {
                    "id": "repeats",
                    "kind": "repeat_employers",
                    "needs": ["state"],
                    "depends_on": [t["id"] for t in tasks],
                }
            )
        if re.search(r"inspection|inspector|plan this week|this week'?s", lower):
            tasks.append(
                {
                    "id": "triage",
                    "kind": "triage",
                    "needs": ["state"],
                    "depends_on": [t["id"] for t in tasks if t["kind"] == "repeat_employers"],
                }
            )
        if re.search(r"safety talk|toolbox|training talk", lower):
            topic = next(
                (
                    t
                    for t in ("lockout", "forklift", "ladder", "fall", "machine guarding", "slip")
                    if t in lower
                ),
                "lockout",
            )
            tasks.append({"id": "talk", "kind": "safety_talk", "needs": [], "depends_on": [],
                          "topic": topic, "spanish": "spanish" in lower or "español" in lower})  # fmt: skip
        if budget or "prevention" in lower:
            tasks.append({"id": "prevention", "kind": "prevention_plan", "needs": [], "depends_on": []})
            if budget:
                params["budget"] = int(budget.group(1).replace(",", ""))
    if any(t["kind"] == "trend" for t in tasks) and "start" not in params:
        tasks[[t["kind"] for t in tasks].index("trend")]["needs"].append("start")
    missing = sorted({n for t in tasks for n in t["needs"] if n not in params})
    if not tasks:
        missing = ["request"]
    return {"tasks": tasks, "params": params, "missing": missing}


def intake(payload: dict[str, Any]) -> dict[str, Any]:
    """Read the facts of one narrative; the codes and confidence come from the baseline."""
    narrative: str = payload["narrative"]
    hint = f"{narrative} {payload.get('event_title', '')}"
    activity, activity_match = _find(ACTIVITY, narrative, "unknown")
    hazard, hazard_match = _find(HAZARD_TYPES, hint, "other")
    if hazard == "machine" and hazard_match is not None and not hazard_match.group(0):
        hazard_match = re.search(MACHINE_WORDS, narrative, flags=re.IGNORECASE)
    material, material_match = _find(MATERIALS, narrative, "")
    spans = []
    for label, match in (
        ("activity", activity_match),
        ("hazard", hazard_match),
        ("material", material_match),
    ):
        if (
            match
            and match.end() <= len(narrative)
            and narrative[match.start() : match.end()] == match.group(0)
        ):
            spans.append({"label": label, "start": match.start(), "end": match.end()})
    machine = hazard_match.group(0) if hazard_match else ""
    feet = re.search(r"\b(\d+)\s*(feet|foot|ft)\b", narrative, flags=re.IGNORECASE)
    fatality = (
        (hazard == "machine" and re.search(r"pulled into|entangled|head|neck|chest|torso|crushed", narrative, re.IGNORECASE))
        or (hazard in ("fall_height", "ladder") and ((feet and int(feet.group(1)) >= 10) or "roof" in narrative.lower()))
        or hazard in ("electrical", "fire", "crane_load")
        or (hazard in ("powered_truck", "other_vehicle", "struck_by_object") and re.search(r"crushed|pinned|ran over|head|chest", narrative, re.IGNORECASE))
    )  # fmt: skip
    missing = []
    lockout_known = re.search(
        r"lock(ed)?[ /-]*(out|tag)|de-?energiz|shut (down|off)", narrative, re.IGNORECASE
    )
    if hazard == "machine":
        if activity == "unknown":
            missing.append("Was the employee operating, cleaning or servicing the machine?")
        if activity in ("cleaning", "unjamming", "servicing", "setup") and not lockout_known:
            missing.append("Was the machine shut down and locked out before the work began?")
        if not re.search(r"guard", narrative, re.IGNORECASE):
            missing.append("Was a guard in place at the point of operation?")
    if hazard in ("fall_height", "ladder") and not feet:
        missing.append("From what height did the employee fall?")
    if hazard == "fall_height":
        missing.append("Was fall protection provided and in use?")
    if hazard == "ladder":
        missing.append("What type of ladder was used, and was it in good condition?")
    if hazard == "powered_truck":
        missing.append("Was the operator trained and evaluated on this truck?")
    if hazard == "same_level":
        missing.append("What caused the slip or trip: the surface, an object, or the lighting?")
    if hazard == "chemical":
        missing.append("Which substance was involved, and was its safety data sheet available?")
    if not missing and activity == "unknown":
        missing.append("What was the employee doing when the injury happened?")
    return {
        "report_id": payload["report_id"],
        "activity": activity,
        "hazard_type": hazard,
        "machine_or_hazard": machine,
        "material": material,
        "injury": payload.get("nature_title") or "injury",
        "event_code": payload.get("baseline_code", ""),
        "source_code": payload.get("source_code", ""),
        "confidence": float(payload.get("baseline_confidence", 0.5)),
        "fatality_potential": bool(fatality),
        "missing_facts": missing,
        "spans": spans,
        "failed_safeguard": mentions_failed_safeguard(narrative),
    }


def standards_terms(payload: dict[str, Any]) -> dict[str, Any]:
    """Words in the language of the rules for the narrative's hazard."""
    text = payload["narrative"]
    terms = [words for pattern, words in TERMS if re.search(pattern, text, flags=re.IGNORECASE)]
    if payload.get("material") == "wood" and re.search(r"\bsaw\b", text, re.IGNORECASE):
        terms.append("woodworking machinery saws")
    return {"terms": terms}


def handlers() -> dict[str, Any]:
    """The handler for each task name, reading and returning JSON as a model would."""

    def wrap(function):
        return lambda prompt: function(json.loads(prompt))

    from safereport.writer import draft  # the Writer's templates live with the Writer

    return {
        "planner": lambda prompt: plan_request(json.loads(prompt)["request"]),
        "intake": wrap(intake),
        "standards_terms": wrap(standards_terms),
        "writer": wrap(draft),
    }
