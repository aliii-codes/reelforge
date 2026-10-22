"""LLM provider selection: Groq first, Cohere second, optional local Ollama, never paid fallbacks."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from reelforge.config import Settings
from reelforge.providers.base import (
    AuthenticationError,
    LLMError,
    LLMProvider,
    MalformedResponseError,
    ProviderNotConfigured,
    RateLimitError,
)

T = TypeVar("T")

PROVIDER_ORDER = ("groq", "cohere", "ollama")


def build_provider(name: str, settings: Settings) -> LLMProvider:
    if name == "groq":
        from reelforge.providers.groq_provider import GroqProvider

        return GroqProvider(settings.groq_api_key, settings.groq_model, timeout_s=settings.llm_timeout_s)
    if name == "cohere":
        from reelforge.providers.cohere_provider import CohereProvider

        return CohereProvider(settings.cohere_api_key, settings.cohere_model, timeout_s=settings.llm_timeout_s)
    if name == "ollama":
        from reelforge.providers.local_llm_provider import OllamaProvider

        return OllamaProvider(settings.ollama_url, settings.ollama_model)
    raise ValueError(f"unknown LLM provider {name!r} (choose from {', '.join(PROVIDER_ORDER)} or auto)")


def configured_providers(settings: Settings, preferred: str = "auto") -> list[LLMProvider]:
    names = PROVIDER_ORDER if preferred in ("", "auto") else (preferred,)
    out: list[LLMProvider] = []
    for n in names:
        try:
            out.append(build_provider(n, settings))
        except ProviderNotConfigured:
            continue
    return out


class NoProviderAvailable(LLMError):
    pass


class FallbackLLM:
    """Try each configured provider in order. Moves on for auth, rate-limit, timeout,
    server and malformed-output failures, and records what happened."""

    def __init__(self, providers: list[LLMProvider]):
        if not providers:
            raise NoProviderAvailable(
                "No LLM provider is configured. Set GROQ_API_KEY or COHERE_API_KEY in .env "
                "(see docs/providers.md), or create the job from a script file with --script-file."
            )
        self.providers = providers
        self.attempts: list[str] = []
        self.last_used: LLMProvider | None = None

    def run(self, op: Callable[[LLMProvider], T]) -> T:
        errors = []
        for p in self.providers:
            try:
                result = op(p)
                self.attempts.append(f"{p.label}: ok")
                self.last_used = p
                return result
            except (AuthenticationError, RateLimitError, MalformedResponseError, LLMError) as e:
                self.attempts.append(f"{p.label}: {type(e).__name__}: {e}")
                errors.append(f"{p.label}: {e}")
        raise NoProviderAvailable("All LLM providers failed:\n  " + "\n  ".join(errors))
