import json

import httpx
import pytest

from reelforge.config import Settings
from reelforge.providers import FallbackLLM, NoProviderAvailable, configured_providers
from reelforge.providers.base import (
    AuthenticationError,
    MalformedResponseError,
    ProviderNotConfigured,
    ProviderTimeoutError,
    RateLimitError,
)
from reelforge.providers.cohere_provider import CohereProvider, inline_refs
from reelforge.providers.groq_provider import GroqProvider
from reelforge.providers.local_llm_provider import OllamaProvider

HOOKS = {"hooks": [{"text": f"Hook number {i}", "score": 5 + i} for i in range(4)]}
DRAFT = {
    "title": "T",
    "sections": [
        {"role": "hook", "text": "A hook.", "on_screen": "Hook"},
        {"role": "explain", "text": "An explanation."},
        {"role": "twist", "text": "But a twist."},
        {"role": "cta", "text": "Share it."},
    ],
    "claims": [{"text": "c", "source_ids": ["W1", "FAKE9"], "section_index": 0}],
    "caption": "cap",
    "hashtags": ["AI", "#LLM"],
}


def groq_reply(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def make_groq(handler, sleeps=None) -> GroqProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return GroqProvider(
        "test-key",
        "openai/gpt-oss-120b",
        client=client,
        sleep=(sleeps.append if sleeps is not None else lambda s: None),
    )


def test_groq_happy_path_and_request_shape():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["auth"] = req.headers["authorization"]
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=groq_reply(json.dumps(HOOKS)))

    out = make_groq(handler).generate_hooks("topic", "ctx")
    assert len(out.hooks) == 4
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["body"]["model"] == "openai/gpt-oss-120b"


def test_malformed_json_is_repaired_once_then_fails():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(200, json=groq_reply("not json at all" if len(calls) == 1 else json.dumps(HOOKS)))

    assert len(make_groq(handler).generate_hooks("t", "c").hooks) == 4
    assert len(calls) == 2

    def always_bad(req):
        return httpx.Response(200, json=groq_reply('{"hooks": "wrong type"}'))

    with pytest.raises(MalformedResponseError):
        make_groq(always_bad).generate_hooks("t", "c")


def test_rate_limit_retries_with_retry_after_then_raises():
    sleeps: list[float] = []

    def handler(req):
        return httpx.Response(429, headers={"retry-after": "3"}, json={"error": "slow down"})

    with pytest.raises(RateLimitError):
        make_groq(handler, sleeps).generate_hooks("t", "c")
    assert sleeps == [3.0, 3.0]  # two retries honouring Retry-After


def test_rate_limit_recovers():
    n = []

    def handler(req):
        n.append(1)
        if len(n) == 1:
            return httpx.Response(429, json={})
        return httpx.Response(200, json=groq_reply(json.dumps(HOOKS)))

    assert make_groq(handler, []).generate_hooks("t", "c")


def test_timeout_and_auth_errors():
    def timeout(req):
        raise httpx.ReadTimeout("slow", request=req)

    with pytest.raises(ProviderTimeoutError):
        make_groq(timeout, []).generate_hooks("t", "c")

    def unauthorized(req):
        return httpx.Response(401, json={"error": "bad key"})

    with pytest.raises(AuthenticationError) as e:
        make_groq(unauthorized).generate_hooks("t", "c")
    assert "test-key" not in str(e.value)


def test_missing_credentials():
    with pytest.raises(ProviderNotConfigured):
        GroqProvider("", "m")
    with pytest.raises(ProviderNotConfigured):
        CohereProvider("", "m")
    with pytest.raises(ProviderNotConfigured):
        OllamaProvider("http://x", "")
    assert configured_providers(Settings()) == []
    with pytest.raises(NoProviderAvailable):
        FallbackLLM([])


def test_provider_order_groq_then_cohere():
    s = Settings(groq_api_key="g", cohere_api_key="c")
    assert [p.name for p in configured_providers(s)] == ["groq", "cohere"]
    assert [p.name for p in configured_providers(s, "cohere")] == ["cohere"]


def test_cohere_schema_mode_and_fallback_on_400():
    bodies = []

    def handler(req):
        body = json.loads(req.content)
        bodies.append(body)
        if "schema" in body["response_format"]:
            return httpx.Response(400, json={"message": "schema unsupported"})
        return httpx.Response(200, json={"message": {"content": [{"type": "text", "text": json.dumps(DRAFT)}]}})

    p = CohereProvider("k", "command-a-03-2025", client=httpx.Client(transport=httpx.MockTransport(handler)))
    draft = p.generate_script("topic", "hook", [])
    assert draft.title == "T"
    assert bodies[0]["response_format"]["type"] == "json_object" and "schema" in bodies[0]["response_format"]
    assert "schema" not in bodies[1]["response_format"]


def test_inline_refs_removes_defs():
    from reelforge.providers.base import ScriptDraftOut

    flat = inline_refs(ScriptDraftOut.model_json_schema())
    assert "$defs" not in json.dumps(flat) and "$ref" not in json.dumps(flat)


def test_fallback_moves_to_next_provider():
    def unauthorized(req):
        return httpx.Response(401, json={})

    def ok(req):
        return httpx.Response(200, json={"message": {"content": [{"type": "text", "text": json.dumps(HOOKS)}]}})

    bad = make_groq(unauthorized)
    good = CohereProvider("k", "m", client=httpx.Client(transport=httpx.MockTransport(ok)))
    llm = FallbackLLM([bad, good])
    res = llm.run(lambda p: p.generate_hooks("t", "c"))
    assert len(res.hooks) == 4 and llm.last_used is good
    assert "AuthenticationError" in llm.attempts[0]


def test_unknown_llm_source_ids_are_dropped():
    from reelforge.providers.base import ScriptDraftOut
    from reelforge.schemas import ResearchBundle, Source
    from reelforge.scripting.generator import draft_to_script

    research = ResearchBundle(sources=[Source(id="W1", url="https://en.wikipedia.org/wiki/X")])
    script, bundle, notes = draft_to_script(ScriptDraftOut.model_validate(DRAFT), "topic", research)
    assert bundle.claims[0].source_ids == ["W1"]
    assert "FAKE9" in bundle.claims[0].uncertainty and notes
    assert script.hashtags == ["#AI", "#LLM"]


def test_ollama_request():
    def handler(req):
        body = json.loads(req.content)
        assert body["stream"] is False and "format" in body
        return httpx.Response(200, json={"message": {"content": json.dumps(HOOKS)}})

    p = OllamaProvider(
        "http://127.0.0.1:11434", "llama3.2:3b", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    assert len(p.generate_hooks("t", "c").hooks) == 4


def test_wikipedia_search_headers_and_parsing():
    from reelforge.research.search import WIKIMEDIA_HEADERS, WikipediaSearch

    seen = []

    def handler(req):
        seen.append(req.headers)
        if req.url.params.get("list") == "search":
            return httpx.Response(200, json={"query": {"search": [{"title": "Quantization"}]}})
        return httpx.Response(
            200,
            json={
                "query": {
                    "pages": {
                        "1": {
                            "title": "Quantization",
                            "fullurl": "https://en.wikipedia.org/wiki/Quantization",
                            "extract": "Quantization maps values.",
                        }
                    }
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), headers=WIKIMEDIA_HEADERS | {"User-Agent": "t"})
    out = WikipediaSearch(client=client).search("q")
    assert out[0].fetched and out[0].origin == "wikipedia" and out[0].url.endswith("/Quantization")
    assert seen[0]["accept-encoding"] == "gzip" and seen[0]["accept"] == "application/json"
