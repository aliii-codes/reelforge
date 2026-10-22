"""Provider-independent LLM interface.

Concrete providers implement only `_complete_json` (one HTTP round-trip returning a JSON
object). The four pipeline operations below are shared: they build prompts, validate the
returned JSON with Pydantic, and ask the model once to repair malformed output.
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TypeVar

import httpx
from pydantic import BaseModel, Field, ValidationError

from reelforge.providers import prompts
from reelforge.schemas import Expression, SceneType, Script, SectionRole, Source

T = TypeVar("T", bound=BaseModel)


# --------------------------------------------------------------------------- errors


class LLMError(Exception):
    retryable = False


class ProviderNotConfigured(LLMError):
    pass


class AuthenticationError(LLMError):
    pass


class RateLimitError(LLMError):
    retryable = True

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class ProviderTimeoutError(LLMError):
    retryable = True


class ProviderServerError(LLMError):
    retryable = True


class BadRequestError(LLMError):
    pass


class MalformedResponseError(LLMError):
    pass


# --------------------------------------------------------------------------- LLM I/O models


class HookOut(BaseModel):
    text: str
    angle: str = ""
    rationale: str = ""
    score: float = Field(default=5, ge=0, le=10)


class HookSetOut(BaseModel):
    hooks: list[HookOut] = Field(min_length=3, max_length=8)


class SectionOut(BaseModel):
    role: SectionRole
    text: str
    on_screen: str = ""


class ClaimOut(BaseModel):
    text: str
    source_ids: list[str] = Field(default_factory=list)
    support_explanation: str = ""
    uncertainty: str = ""
    section_index: int | None = None


class ScriptDraftOut(BaseModel):
    title: str
    sections: list[SectionOut] = Field(min_length=4)
    claims: list[ClaimOut] = Field(default_factory=list)
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)


class SceneHintOut(BaseModel):
    section_index: int
    scene: SceneType
    headline: str
    subtext: str = ""
    items: list[str] = Field(default_factory=list, max_length=4)
    left: str = ""
    right: str = ""
    stat_value: float | None = None
    stat_prefix: str = ""
    stat_suffix: str = ""
    stat_label: str = ""
    icon: str = ""
    expression: Expression = "neutral"


class ScenePlanOut(BaseModel):
    scenes: list[SceneHintOut] = Field(min_length=1)


# --------------------------------------------------------------------------- provider


class LLMProvider(ABC):
    name: str = "base"

    def __init__(
        self, model: str, timeout_s: float = 60.0, max_retries: int = 2, sleep: Callable[[float], None] = time.sleep
    ):
        self.model = model
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self._sleep = sleep

    @property
    def label(self) -> str:
        return f"{self.name}:{self.model}"

    @abstractmethod
    def _complete_json(self, system: str, user: str, schema: dict) -> str:
        """Return the raw text of a single JSON-object completion."""

    # -- shared plumbing ------------------------------------------------------

    def _call_with_retries(self, system: str, user: str, schema: dict) -> str:
        attempt = 0
        while True:
            try:
                return self._complete_json(system, user, schema)
            except LLMError as e:
                if not e.retryable or attempt >= self.max_retries:
                    raise
                wait = 2.0 * (2**attempt)
                if isinstance(e, RateLimitError) and e.retry_after:
                    wait = e.retry_after
                if wait > 30:
                    raise  # don't block the CLI for minutes; surface the limit instead
                self._sleep(wait)
                attempt += 1

    def structured(self, system: str, user: str, model_cls: type[T]) -> T:
        schema = model_cls.model_json_schema()
        raw = self._call_with_retries(system, user, schema)
        try:
            return _parse(raw, model_cls)
        except MalformedResponseError as first:
            repair = prompts.repair_prompt(user, raw, str(first))
            raw2 = self._call_with_retries(system, repair, schema)
            return _parse(raw2, model_cls)

    # -- pipeline operations -------------------------------------------------

    def generate_hooks(self, topic: str, context: str) -> HookSetOut:
        return self.structured(prompts.SYSTEM_WRITER, prompts.hooks_prompt(topic, context), HookSetOut)

    def generate_script(self, topic: str, selected_hook: str, sources: list[Source]) -> ScriptDraftOut:
        return self.structured(
            prompts.SYSTEM_WRITER, prompts.script_prompt(topic, selected_hook, sources), ScriptDraftOut
        )

    def revise_script(self, script: Script, feedback: str, sources: list[Source]) -> ScriptDraftOut:
        return self.structured(prompts.SYSTEM_WRITER, prompts.revise_prompt(script, feedback, sources), ScriptDraftOut)

    def generate_scene_plan(self, approved_script: Script) -> ScenePlanOut:
        return self.structured(prompts.SYSTEM_DESIGNER, prompts.scene_plan_prompt(approved_script), ScenePlanOut)


def _parse[T: BaseModel](raw: str, model_cls: type[T]) -> T:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{") :]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise MalformedResponseError("response contained no JSON object")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as e:
        raise MalformedResponseError(f"invalid JSON: {e}") from e
    try:
        return model_cls.model_validate(data)
    except ValidationError as e:
        raise MalformedResponseError(f"JSON did not match schema: {e.error_count()} errors: {e.errors()[:3]}") from e


def raise_for_http(resp: httpx.Response, provider: str) -> None:
    """Map HTTP failures to typed errors. Never includes request headers (API keys)."""
    if resp.status_code < 400:
        return
    snippet = resp.text[:300].replace("\n", " ")
    if resp.status_code in (401, 403):
        raise AuthenticationError(
            f"{provider}: authentication failed (HTTP {resp.status_code}). Check the API key in .env."
        )
    if resp.status_code == 429:
        retry_after = resp.headers.get("retry-after")
        try:
            ra = float(retry_after) if retry_after else None
        except ValueError:
            ra = None
        raise RateLimitError(f"{provider}: rate limit reached (HTTP 429): {snippet}", retry_after=ra)
    if resp.status_code in (408, 504):
        raise ProviderTimeoutError(f"{provider}: upstream timeout (HTTP {resp.status_code})")
    if resp.status_code >= 500:
        raise ProviderServerError(f"{provider}: server error (HTTP {resp.status_code}): {snippet}")
    raise BadRequestError(f"{provider}: request rejected (HTTP {resp.status_code}): {snippet}")


def post_json(client: httpx.Client, url: str, provider: str, **kwargs: object) -> dict:
    try:
        resp = client.post(url, **kwargs)  # type: ignore[arg-type]
    except httpx.TimeoutException as e:
        raise ProviderTimeoutError(f"{provider}: request timed out") from e
    except httpx.TransportError as e:
        raise ProviderServerError(f"{provider}: network error: {type(e).__name__}") from e
    raise_for_http(resp, provider)
    try:
        return resp.json()
    except ValueError as e:
        raise MalformedResponseError(f"{provider}: response body was not JSON") from e
