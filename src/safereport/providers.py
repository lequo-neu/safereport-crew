"""Live model backends: Anthropic, OpenAI, Google and a local model served by LM Studio.

Each backend sends the same JSON prompt the offline rules receive, with a system prompt that
says what to return, and hands back the parsed JSON. Provider failures become `ModelError`, so
the router moves the call down the fallback chain; a reply that is not the JSON asked for does
too. A backend is built only when its credentials (or the local server) are there, so nothing
is called, or paid for, by accident.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import re
import time
from typing import Any
import urllib.request

from safereport.backends import ModelError, Reply
from safereport.config import ModelSettings, ModelSpec
from safereport.offline import ACTIVITY, HAZARD_TYPES
from safereport.writer import draft


LM_STUDIO_URL = os.environ.get("LM_STUDIO_URL", "http://localhost:1234/v1")
# Seconds before a model call gives up; a hung provider then falls back instead of stalling a run.
REQUEST_TIMEOUT = 60.0
# A local model on a laptop thinks before it answers; give it longer than a cloud API.
LOCAL_TIMEOUT = 180.0

SYSTEM = {
    "planner": (
        "You plan requests for an OSHA area office copilot. Return JSON with keys tasks, params, missing. "
        "tasks is a list of {id, kind, needs, depends_on} where kind is one of single_report (the request is an "
        "injury narrative), trend, repeat_employers, triage, safety_talk (add topic and extra_language: one of es, zh, tl, vi, ar, or empty for English only), "
        "prevention_plan. params may hold state (upper case name), start (YYYY-01-01), naics_prefix, "
        "event_group_v3 with hazard_label, capacity (inspector days, a number) and budget. needs lists the "
        "params a task requires: triage and repeat_employers need state, trend needs start. missing lists the "
        "needed params the request does not give."
    ),
    "intake": (
        "You read one OSHA severe injury narrative. Return JSON with keys report_id, activity, hazard_type, "
        "machine_or_hazard, material, injury, event_code, source_code, confidence, fatality_potential, "
        "missing_facts and evidence. activity is one of: "
        + ", ".join(a for a, _ in ACTIVITY)
        + ", other, unknown. "
        "hazard_type is one of: " + ", ".join(h for h, _ in HAZARD_TYPES) + ", other. Keep event_code and "
        "confidence from the baseline in the input unless the narrative clearly contradicts the code. "
        "missing_facts are questions an investigator must ask because the narrative does not answer them "
        "(was the machine locked out, was a guard in place, the fall height). evidence is a list of "
        "{label, text} where text is copied exactly from the narrative. Words such as [EMPLOYER_1] are "
        "placeholders; keep them as they are."
    ),
    "standards_terms": (
        "Return JSON {terms: [...]}: short phrases in the language of 29 CFR Part 1910 that name the hazard in "
        "this narrative (for example 'powered industrial truck' for a forklift, 'servicing and maintenance' "
        "and 'hazardous energy' for clearing a jam). Do not name section numbers."
    ),
    "writer": (
        "You polish a document for an OSHA office. The input holds base_template. Return JSON {template: ...}: "
        "the same document in clear, plain words in the language its code names (en, es, zh, tl, vi or ar), keeping every {{placeholder}} "
        "exactly as written and keeping every CFR citation. Write no digit anywhere outside a placeholder or a "
        "citation; spell small fixed numbers out in words. When the input has fix, it lists what the critic "
        "found wrong in the last draft; correct exactly those points."
    ),
}
STEP_TASKS = {"code": "intake", "retrieve": "standards_terms", "decide": "planner", "write": "writer"}


def parse_json(text: str) -> dict[str, Any]:
    """The JSON object in a reply, also when a model wraps it in a code fence or prose.

    A model sometimes writes an answer, corrects itself and writes a "final answer"; the last
    complete object in the reply is the one it settled on.
    """
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
    body = fenced.group(1) if fenced else text
    decoder = json.JSONDecoder()
    found: list[dict[str, Any]] = []
    at = body.find("{")
    while at != -1:
        try:
            value, end = decoder.raw_decode(body, at)
        except ValueError:
            at = body.find("{", at + 1)
            continue
        if isinstance(value, dict):
            found.append(value)
        at = body.find("{", end)
    if not found:
        raise ValueError("the reply holds no JSON object")
    return found[-1]


def evidence_to_spans(data: dict[str, Any], narrative: str) -> dict[str, Any]:
    """Turn quoted evidence into character offsets; quotes that are not in the narrative are dropped."""
    spans = []
    for item in data.pop("evidence", []) or []:
        quote = str(item.get("text", ""))
        at = narrative.find(quote) if quote else -1
        if at >= 0:
            spans.append({"label": str(item.get("label", "evidence")), "start": at, "end": at + len(quote)})
    return {**data, "spans": spans}


def prepare(task: str, prompt: str) -> str:
    """What the model sees: the Writer gets the rule based draft to polish, so placeholders survive."""
    if task != "writer":
        return prompt
    payload = json.loads(prompt)
    return json.dumps({**payload, "base_template": draft(payload)["template"]})


def finish(task: str, prompt: str, text: str) -> dict[str, Any]:
    data = parse_json(text)
    if task == "intake":
        data = evidence_to_spans(data, json.loads(prompt).get("narrative", ""))
    if task == "writer" and not isinstance(data.get("template"), str):
        raise ValueError("the Writer reply has no template")
    return data


@dataclass
class AnthropicBackend:
    """Claude through the Anthropic SDK, with the server side refusal fallback switched on."""

    spec: ModelSpec
    client: Any = None
    name: str = field(init=False)

    def __post_init__(self) -> None:
        self.name = self.spec.name

    def complete(self, step: str, prompt: str) -> Reply:
        import anthropic

        # The client is made on the first call, so building the backend reads no credentials.
        self.client = self.client or anthropic.Anthropic(timeout=REQUEST_TIMEOUT)

        task = STEP_TASKS.get(step, step)
        started = time.perf_counter()
        try:
            response = self.client.beta.messages.create(
                model=self.spec.model_id,
                max_tokens=16000,
                system=SYSTEM[task],
                messages=[{"role": "user", "content": prepare(task, prompt)}],
                output_config={"effort": "low" if task in ("intake", "standards_terms") else "medium"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.APITimeoutError as error:
            raise ModelError("timeout", self.name) from error
        except anthropic.RateLimitError as error:
            raise ModelError("rate_limit", self.name) from error
        except anthropic.APIStatusError as error:
            raise ModelError(
                "server_error" if error.status_code >= 500 else "bad_request", self.name
            ) from error
        except anthropic.APIConnectionError as error:
            raise ModelError("server_error", self.name) from error
        if response.stop_reason == "refusal":
            raise ModelError("refusal", self.name)
        text = "".join(block.text for block in response.content if block.type == "text")
        return _reply(
            self.name, task, prompt, text, response.usage.input_tokens, response.usage.output_tokens, started
        )


@dataclass
class OpenAIBackend:
    """GPT models, or a local model through LM Studio's OpenAI compatible server."""

    spec: ModelSpec
    client: Any = None
    base_url: str | None = None
    name: str = field(init=False)

    def __post_init__(self) -> None:
        self.name = self.spec.name

    def complete(self, step: str, prompt: str) -> Reply:
        import openai

        local = self.base_url is not None
        if self.client is None:
            server = {"base_url": self.base_url, "api_key": "lm-studio"} if local else {}
            self.client = openai.OpenAI(timeout=LOCAL_TIMEOUT if local else REQUEST_TIMEOUT, **server)
        # LM Studio rejects {"type": "json_object"} (it takes only "json_schema" or "text"), so a
        # local model gets no response_format: the system prompt asks for JSON and parse_json
        # reads the object from the reply.
        json_mode = {} if local else {"response_format": {"type": "json_object"}}

        task = STEP_TASKS.get(step, step)
        started = time.perf_counter()
        try:
            response = self.client.chat.completions.create(
                model=self.spec.model_id,
                messages=[
                    {"role": "system", "content": SYSTEM[task]},
                    {"role": "user", "content": prepare(task, prompt)},
                ],
                **json_mode,
            )
        except openai.APITimeoutError as error:
            raise ModelError("timeout", self.name) from error
        except openai.RateLimitError as error:
            raise ModelError("rate_limit", self.name) from error
        except openai.APIStatusError as error:
            raise ModelError(
                "server_error" if error.status_code >= 500 else "bad_request", self.name
            ) from error
        except openai.APIConnectionError as error:
            raise ModelError("server_error", self.name) from error
        text = response.choices[0].message.content or ""
        usage = response.usage
        return _reply(self.name, task, prompt, text, usage.prompt_tokens if usage else 0,
                      usage.completion_tokens if usage else 0, started)  # fmt: skip


@dataclass
class GoogleBackend:
    """Gemini through the google-genai SDK."""

    spec: ModelSpec
    client: Any = None
    name: str = field(init=False)

    def __post_init__(self) -> None:
        self.name = self.spec.name

    def complete(self, step: str, prompt: str) -> Reply:
        from google import genai
        from google.genai import errors, types

        self.client = self.client or genai.Client(
            http_options=types.HttpOptions(timeout=int(REQUEST_TIMEOUT * 1000))
        )

        task = STEP_TASKS.get(step, step)
        started = time.perf_counter()
        try:
            response = self.client.models.generate_content(
                model=self.spec.model_id,
                contents=prepare(task, prompt),
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM[task], response_mime_type="application/json"
                ),
            )
        except errors.APIError as error:
            kind = (
                "rate_limit" if error.code == 429 else "server_error" if error.code >= 500 else "bad_request"
            )
            raise ModelError(kind, self.name) from error
        usage = response.usage_metadata
        return _reply(self.name, task, prompt, response.text or "", (usage.prompt_token_count or 0) if usage else 0,
                      (usage.candidates_token_count or 0) if usage else 0, started)  # fmt: skip


def _reply(
    name: str, task: str, prompt: str, text: str, tokens_in: int, tokens_out: int, started: float
) -> Reply:
    try:
        data = finish(task, prompt, text)
    except (ValueError, TypeError) as error:
        unusable = Reply(name, text, None, tokens_in, tokens_out, time.perf_counter() - started)
        raise ModelError("bad_output", name, unusable) from error
    return Reply(name, text, data, tokens_in, tokens_out, time.perf_counter() - started)


def lm_studio_running(url: str = LM_STUDIO_URL) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/models", timeout=1) as response:  # noqa: S310 (a local server URL)
            return response.status == 200
    except OSError:
        return False


def live_backends(
    settings: ModelSettings, environ: dict[str, str] | None = None, local_only: bool = False
) -> dict[str, Any]:
    """A backend for every configured model whose key (or local server) is available.

    `local_only` (private mode) leaves every cloud model out, even when its key is set, so nothing
    leaves the machine and nothing is paid for, whatever the routing page is set to later.
    """
    if environ is None:
        from safereport.config import load_env_file

        load_env_file()
        environ = dict(os.environ)
    backends: dict[str, Any] = {}
    for spec in settings.models:
        if local_only and spec.provider != "local":
            continue
        if spec.provider == "anthropic" and (
            environ.get("ANTHROPIC_API_KEY") or environ.get("ANTHROPIC_AUTH_TOKEN")
        ):
            backends[spec.name] = AnthropicBackend(spec)
        elif spec.provider == "openai" and environ.get("OPENAI_API_KEY"):
            backends[spec.name] = OpenAIBackend(spec)
        elif spec.provider == "google" and (environ.get("GOOGLE_API_KEY") or environ.get("GEMINI_API_KEY")):
            backends[spec.name] = GoogleBackend(spec)
        elif spec.provider == "local" and lm_studio_running():
            backends[spec.name] = OpenAIBackend(spec, base_url=LM_STUDIO_URL)
    return backends
