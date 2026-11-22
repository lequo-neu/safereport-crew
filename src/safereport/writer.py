"""The Writer's templates: briefs, RRI letters, safety talks, memos and answers.

Every number comes in through a FactLedger placeholder such as {{reports_2025}}; the templates
themselves spell small fixed quantities out in words ("five working days"), so the critic can
treat any digit outside a placeholder or a citation as untraced. A model writing these drafts
must follow the same rule, and the critic holds it to it.
"""

from __future__ import annotations

from typing import Any

from safereport.talk_languages import LEADS, TRANSLATIONS


TALKS: dict[str, dict[str, dict[str, Any]]] = {
    "lockout": {
        "en": {
            "title": "Lockout before you reach in",
            "why": "Machines start without warning. A jam, a cleaning job or a quick adjustment is when hands go where the guard used to be.",
            "points": [
                "Stop the machine and turn off every energy source: electric, air, hydraulic, gravity and stored springs.",
                "Put your own lock and tag on each isolation point. Your lock, your key.",
                "With every lock on, stand clear and try the normal start controls to make sure the machine does not start, then return them to off.",
                "If a jam keeps coming back, tell your supervisor. Do not clear it with the machine running.",
            ],
            "close": "Ask: what energy could still move this machine? If you are not sure, it is not locked out.",
        },
        "es": {
            "title": "Bloquee antes de meter las manos",
            "why": "Las máquinas arrancan sin aviso. Un atasco, una limpieza o un ajuste rápido es cuando las manos entran donde estaba la guarda.",
            "points": [
                "Pare la máquina y corte todas las fuentes de energía: eléctrica, aire, hidráulica, gravedad y resortes cargados.",
                "Ponga su propio candado y su etiqueta en cada punto de aislamiento. Su candado, su llave.",
                "Intente arrancar la máquina antes de meter las manos y luego deje el control en apagado.",
                "Si un atasco se repite, avise a su supervisor. No lo despeje con la máquina en marcha.",
            ],
            "close": "Pregunte: ¿qué energía todavía puede mover esta máquina? Si no está seguro, no está bloqueada.",
        },
    },
    "machine guarding": {
        "en": {
            "title": "Guards stay on",
            "why": "Rollers, blades and belts pull a glove or a sleeve in faster than anyone can react.",
            "points": [
                "Never run a machine with a guard removed, bent or bypassed.",
                "Keep hands out of the point of operation; use push sticks and feeding tools.",
                "Report a missing or damaged guard before the shift starts.",
            ],
            "close": "If a guard slows the job down, say so. Removing it is not the fix.",
        },
        "es": {
            "title": "Las guardas se quedan puestas",
            "why": "Rodillos, cuchillas y correas jalan un guante o una manga más rápido de lo que nadie reacciona.",
            "points": [
                "Nunca opere una máquina con una guarda quitada, doblada o anulada.",
                "Mantenga las manos fuera del punto de operación; use empujadores y herramientas de alimentación.",
                "Reporte una guarda que falte o esté dañada antes de empezar el turno.",
            ],
            "close": "Si una guarda hace más lento el trabajo, dígalo. Quitarla no es la solución.",
        },
    },
    "fall": {
        "en": {
            "title": "Every edge is a fall",
            "why": "Most falls happen on short, routine jobs: one step onto a trailer, a quick look over a mezzanine edge.",
            "points": [
                "Use the guardrail, the harness or the lift; never step past an unprotected edge.",
                "Cover and mark holes and skylights.",
                "Keep three points of contact when climbing on and off equipment.",
            ],
            "close": "Before you go up, ask how you are protected if you slip.",
        },
        "es": {
            "title": "Cada borde es una caída",
            "why": "La mayoría de las caídas ocurren en trabajos cortos y rutinarios: subir a un remolque o asomarse al borde de un entrepiso.",
            "points": [
                "Use la baranda, el arnés o la plataforma; nunca pase un borde sin protección.",
                "Cubra y marque los huecos y tragaluces.",
                "Mantenga tres puntos de contacto al subir y bajar de los equipos.",
            ],
            "close": "Antes de subir, pregunte cómo está protegido si se resbala.",
        },
    },
    "forklift": {
        "en": {
            "title": "Forklifts and people",
            "why": "A forklift operator often cannot see a person walking behind a load.",
            "points": [
                "Only trained and evaluated operators drive a forklift.",
                "Walk in marked aisles and make eye contact before crossing.",
                "Keep loads low and stable; never ride on the forks.",
            ],
            "close": "If you cannot see the operator's eyes, the operator cannot see you.",
        },
        "es": {
            "title": "Montacargas y personas",
            "why": "El operador de un montacargas muchas veces no ve a una persona que camina detrás de la carga.",
            "points": [
                "Solo los operadores capacitados y evaluados manejan un montacargas.",
                "Camine por los pasillos marcados y haga contacto visual antes de cruzar.",
                "Mantenga las cargas bajas y estables; nunca se suba a las horquillas.",
            ],
            "close": "Si no ve los ojos del operador, el operador no lo ve a usted.",
        },
    },
}
for _topic, _languages in TRANSLATIONS.items():
    TALKS[_topic].update(_languages)
TALKS["ladder"] = TALKS["fall"]
TALKS["slip"] = TALKS["fall"]


def _bullets(items: list[str]) -> str:
    return "\n".join(f"* {item}" for item in items)


def draft(payload: dict[str, Any]) -> dict[str, Any]:
    """Draft one document. `payload` names the kind and the fact keys the tools recorded."""
    kind = payload["kind"]
    if kind == "inspection_brief":
        template = (
            "# Inspection brief: report {{report_id}}\n\n"
            "**Employer:** {{employer}}, {{city}}, {{state}}. **Date of injury:** {{event_date}}.\n\n"
            "**What happened:** {{narrative}}\n\n"
            f"**Hazard:** {payload['hazard']} during {payload['activity']}. "
            f"**Standard:** {payload['citation']}{payload.get('secondary_note', '')}.\n\n"
            "> {{quote}}\n\n"
            "**Employer history in this state:** {{history_same}} earlier reports confirmed, "
            "{{history_possible}} possible matches to confirm.\n\n"
            + (
                "**Similar past injuries:**\n"
                + _bullets([f"{{{{similar_{n}}}}}" for n in range(1, payload["similar"] + 1)])
                + "\n\n"
                if payload.get("similar")
                else ""
            )
            + "**Questions for the visit:**\n"
            + _bullets(payload.get("questions", []) or ["None beyond the standard."])
        )
    elif kind == "rri_letter":
        template = (
            "Dear {{employer}},\n\n"
            "OSHA received your report of a severe injury on {{event_date}} at your {{city}} site. "
            "Instead of an on site inspection, we ask you to investigate the incident yourself and reply "
            "in writing within five working days of this letter.\n\n"
            "Please answer these questions in your reply:\n"
            + _bullets(payload.get("questions", []))
            + "\n\nPlease also send:\n"
            + _bullets(
                [
                    "the results of your internal investigation, including the root cause;",
                    (
                        "a signed abatement verification describing the corrections you made, with supporting "
                        "documents such as procedures, photographs and training records;"
                    ),
                    "a signed certificate that you posted this letter where employees can see it.",
                ]
            )
            + f"\n\nThe hazard appears to fall under {payload['citation']}. "
            "If your reply is incomplete, or if we learn of other hazards, OSHA may conduct an on site inspection.\n\n"
            "Area Director"
        )
    elif kind == "safety_talk":
        language = payload.get("language", "en")
        talk = TALKS.get(payload.get("topic", "lockout"), TALKS["lockout"])[language]
        lead = LEADS[language]
        template = (
            f"# {talk['title']}\n\n{lead} {talk['why']}\n\n{_bullets(talk['points'])}\n\n{talk['close']}"
        )
    elif kind == "trend_answer":
        compare = (
            ". The range holds this one year only, so there is no earlier year to compare with."
            if payload.get("single_year")
            else ", against {{previous_reports}} in the same months of {{previous_year}}: a change of {{change}}."
        )
        template = (
            f"**{payload['subject']}**\n\n"
            "{{latest_reports}} reports in {{latest_year}} ({{latest_note}})" + compare
            + ("\n\nYears before {{oiics_change_year}} use event codes estimated from the narrative "
               "(OSHA moved to OIICS 3 in January {{oiics_change_year}})."
               if payload.get("estimated") else "")
        )  # fmt: skip
    elif kind == "repeat_answer":
        template = (
            "{{repeat_employers}} employers in {{state}} filed more than one of these reports, "
            "counting only names that match exactly; {{possible_pairs}} more name pairs need a person to confirm them."
        )
    elif kind == "triage_summary":
        template = (
            "# Proposed list for {{state}}, {{week}}\n\n"
            "{{reports}} reports. {{category_one}} meet a Category 1 criterion and must be inspected. "
            "The plan sends {{inspections}} to an inspection and {{letters}} to an RRI letter, using "
            "{{days_used}} of {{capacity}} inspector days."
            + ("\n\n**Not enough inspector days:** the reports that must be inspected (Category 1, and the rows "
               "the Area Director set to inspection) need {{shortfall}} more days."
               if payload.get("infeasible") else "")
        )  # fmt: skip
    elif kind == "plant_memo":
        template = (
            "To the plant manager:\n\nIn plants of your industry, {{top_hazard}} caused {{top_hazard_reports}} "
            f"severe injuries since {{{{since}}}}. The standard to check first is {payload['citation']}."
        )
    else:
        raise ValueError(f"the Writer has no template for {kind!r}")
    return {"kind": kind, "language": payload.get("language", "en"), "template": template}
