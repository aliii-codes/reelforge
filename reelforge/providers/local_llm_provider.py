"""Optional offline script generation through a locally running Ollama server.

Only enabled when OLLAMA_MODEL is set. ReelForge does not install Ollama or pull models; a
small model (e.g. 1-3B) will run on this laptop's CPU but writes noticeably weaker scripts.
"""

from __future__ import annotations

import httpx

from reelforge.providers.base import LLMProvider, MalformedResponseError, ProviderNotConfigured, post_json


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, url: str, model: str, timeout_s: float = 300.0, client: httpx.Client | None = None, **kw):
        if not model:
            raise ProviderNotConfigured("OLLAMA_MODEL is not set")
        super().__init__(model=model, timeout_s=timeout_s, **kw)
        self._url = url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout_s)

    def _complete_json(self, system: str, user: str, schema: dict) -> str:
        body = {
            "model": self.model,
            "stream": False,
            "format": schema,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": 0.7},
        }
        data = post_json(self._client, f"{self._url}/api/chat", "ollama", json=body)
        try:
            return data["message"]["content"]
        except (KeyError, TypeError) as e:
            raise MalformedResponseError("ollama: unexpected response shape") from e
