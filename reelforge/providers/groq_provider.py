"""Groq (OpenAI-compatible chat completions). Docs: https://console.groq.com/docs

Uses JSON-object mode, which Groq documents as supported by all models, and validates the
result locally with Pydantic. The model id comes from GROQ_MODEL and is never switched
automatically.
"""

from __future__ import annotations

import httpx

from reelforge.providers.base import LLMProvider, MalformedResponseError, ProviderNotConfigured, post_json

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(self, api_key: str, model: str, timeout_s: float = 60.0, client: httpx.Client | None = None, **kw):
        if not api_key:
            raise ProviderNotConfigured("GROQ_API_KEY is not set")
        super().__init__(model=model, timeout_s=timeout_s, **kw)
        self._key = api_key
        self._client = client or httpx.Client(timeout=timeout_s)

    def _complete_json(self, system: str, user: str, schema: dict) -> str:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                # every prompt already spells out its JSON shape and replies are validated locally,
                # so the full schema isn't sent: it costs ~1k tokens against an 8K-tokens/min free limit
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.7,
        }
        if self.model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = "low"  # far fewer hidden reasoning tokens, plenty for scripts
        data = post_json(
            self._client,
            GROQ_URL,
            "groq",
            json=body,
            headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"},
        )
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise MalformedResponseError("groq: unexpected response shape") from e
