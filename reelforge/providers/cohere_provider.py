"""Cohere Chat API v2. Docs: https://docs.cohere.com/reference/chat

Uses `response_format: {"type": "json_object", "schema": ...}` (Cohere's JSON-schema mode).
If Cohere rejects the schema, retries once in plain JSON mode; output is validated locally.
"""

from __future__ import annotations

import json

import httpx

from reelforge.providers.base import (
    BadRequestError,
    LLMProvider,
    MalformedResponseError,
    ProviderNotConfigured,
    post_json,
)

COHERE_URL = "https://api.cohere.ai/v2/chat"


def inline_refs(schema: dict) -> dict:
    """Inline `$defs` references; simpler schema dialects handle that better."""
    defs = schema.get("$defs", {})

    def walk(node: object) -> object:
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].split("/")[-1]
                return walk(defs[name])
            return {k: walk(v) for k, v in node.items() if k not in ("$defs", "title", "default")}
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(schema)  # type: ignore[return-value]


class CohereProvider(LLMProvider):
    name = "cohere"

    def __init__(self, api_key: str, model: str, timeout_s: float = 60.0, client: httpx.Client | None = None, **kw):
        if not api_key:
            raise ProviderNotConfigured("COHERE_API_KEY is not set")
        super().__init__(model=model, timeout_s=timeout_s, **kw)
        self._key = api_key
        self._client = client or httpx.Client(timeout=timeout_s)
        self._use_schema = True

    def _complete_json(self, system: str, user: str, schema: dict) -> str:
        fmt: dict = {"type": "json_object"}
        if self._use_schema:
            fmt["schema"] = inline_refs(schema)
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user + "\n\nReply in JSON. Schema:\n" + json.dumps(inline_refs(schema))},
            ],
            "response_format": fmt,
            "temperature": 0.7,
        }
        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            data = post_json(self._client, COHERE_URL, "cohere", json=body, headers=headers)
        except BadRequestError:
            if not self._use_schema:
                raise
            self._use_schema = False
            return self._complete_json(system, user, schema)
        try:
            parts = data["message"]["content"]
            return "".join(p.get("text", "") for p in parts if p.get("type") == "text")
        except (KeyError, TypeError) as e:
            raise MalformedResponseError("cohere: unexpected response shape") from e
