# External providers (LLM and research)

**All findings below were checked on 2026-10-22** from the providers' own documentation. Free
access can change or end at any time; nothing here is a guarantee. ReelForge never requires a
paid plan, never switches model ids on its own, and the `--script-file` workflow needs no
provider at all.

## How ReelForge uses them

- `REELFORGE_LLM_PROVIDER=auto` tries, in order: **Groq** → **Cohere** → **Ollama** (local,
  only if `OLLAMA_MODEL` is set). Only providers with credentials configured are tried.
- One HTTP request per operation (`generate_hooks`, `generate_script`, `revise_script`,
  `generate_scene_plan`). Output is JSON, validated locally with Pydantic; one "repair" retry
  is sent if the JSON is malformed.
- Retries: up to 2 for HTTP 429/5xx/timeouts, honouring `Retry-After` (never waits > 30 s).
  Authentication errors are not retried; the next provider is tried instead.
- Keys are read from `.env` / the environment only and are never logged or written to job
  files (`project_config.json` records only `set`/`missing`).

## Groq (primary)

| Item | Finding (2026-10-22) | Source |
|---|---|---|
| Free access | Groq offers a free plan; a paid Developer tier exists. No payment details are mentioned for the free plan in the pages checked (card requirement **unverified**). | https://console.groq.com/docs/rate-limits |
| Limits | The rate-limits page shows per-model tables (RPM/RPD/TPM/TPD) and says limits apply per organisation, that "there may be exceptions", and that your exact limits are on the account's Limits page. The table captured lists `openai/gpt-oss-120b` / `gpt-oss-20b` at 30 RPM, 1K RPD, 8K TPM, 200K TPD; it is labelled as the **Developer** plan base limits. The free-plan tab values could not be read directly; third-party summaries quote the same numbers for the free plan (**unverified**). | https://console.groq.com/docs/rate-limits |
| Retirements | `llama-3.3-70b-versatile` and `llama-3.1-8b-instant` were shut down on 2026-08-16 for free/developer tiers (replacement: `openai/gpt-oss-120b` / `gpt-oss-20b`). `qwen/qwen3.6-27b` retired 2026-09-14 (→ `qwen/qwen3.8-27b`). `groq/compound*` retired 2026-09-21. | https://console.groq.com/docs/deprecations |
| Default model | `openai/gpt-oss-120b` (set `GROQ_MODEL` to change; `openai/gpt-oss-20b` is the lighter option). | — |
| Structured output | `json_schema` (strict and best-effort) on gpt-oss-20b/120b, qwen3.8-27b and others; **JSON-object mode on all models**. ReelForge uses JSON-object mode + local validation for portability. Streaming/tool use are not supported with structured outputs. | https://console.groq.com/docs/structured-outputs |
| Terms | The site terms say they do not cover the cloud services; the "Groq Services Agreement" governs API use. That agreement was not reviewed here, so **commercial-use conditions for free-tier output are unverified**. Read it before monetised use. | https://groq.com/terms-of-use |

Get a key: https://console.groq.com/keys → put it in `.env` as `GROQ_API_KEY=...`.

## Cohere (alternative)

| Item | Finding (2026-10-22) | Source |
|---|---|---|
| Free access | Registration gives "a free, rate-limited trial key". No card requirement is stated. | https://docs.cohere.com/docs/going-live |
| Limits | Trial keys: 20 chat requests/min and **1,000 API calls per month**. Production keys are paid. | https://docs.cohere.com/docs/rate-limits |
| Intended use | The go-live page implies trial keys are for evaluation; production use means upgrading and accepting Cohere's SaaS agreement. The general terms say the service "has been designed for business use" and prohibit personal/household use and benchmarking. **Treat trial keys as for evaluation/prototyping only**; check with Cohere before publishing monetised content made with a trial key. | https://docs.cohere.com/docs/going-live, https://cohere.com/terms-of-use |
| Models | `command-a-03-2025` (default here), `command-a-plus-05-2026`, `command-r-08-2024`, `command-r7b-12-2024`, … Older `command`, `command-r`, `command-r-plus` aliases were deprecated 2025-09-15. | https://docs.cohere.com/docs/models |
| Structured output | Chat v2 `response_format: {"type": "json_object", "schema": {...}}`; the prompt must also ask for JSON. ReelForge sends the schema and falls back to schema-less JSON mode if rejected. | https://docs.cohere.com/docs/structured-outputs |

Get a key: https://dashboard.cohere.com/api-keys → `.env` `COHERE_API_KEY=...`.

## Local LLM (optional)

`OllamaProvider` talks to a locally running Ollama server (`OLLAMA_URL`, `OLLAMA_MODEL`).
ReelForge does not install Ollama or download models. On this laptop (2 cores, 16 GB RAM, no
usable GPU) only small models (≈1–4B, quantized) are practical; expect noticeably weaker
scripts than Groq/Cohere. Status: **implemented and unit-tested with a mocked server; not
tested against a real Ollama install.**

## Research / search

| Provider | Key | Finding (2026-10-22) | Source |
|---|---|---|---|
| Wikipedia (MediaWiki API) | none | No API key. Wikimedia etiquette requires a descriptive User-Agent with contact info (set `REELFORGE_CONTACT`), serial requests and backoff on `ratelimited`. Used by default. | https://www.mediawiki.org/wiki/API:Etiquette |
| Tavily | optional `TAVILY_API_KEY` | Free plan: 1,000 credits/month, no credit card required; basic search = 1 credit. Used first when configured. | https://docs.tavily.com/documentation/api-credits |
| Manual | none | `--sources-file` (`URL | note` per line) or `[source]`/`[claim]` lines in a script file. URLs are opened to confirm they load (disable with `--offline`). | — |

A source is marked `fetched: true` only if its page was actually retrieved in that run; the
claim checker only uses text that was really downloaded.

## Status of live testing

No Groq, Cohere or Tavily key was configured on this machine when the MVP was built, so **no
live LLM or Tavily call has been made**. Those integrations are covered by mocked tests
(`reelforge/tests/test_providers.py`). Direct URL fetching (including Wikipedia article pages) was
exercised live. **Live Wikipedia API search returned HTTP 403 "Please respect our robot policy"**
with the default User-Agent (no contact info) after one initial success; httpx's default
`Accept: */*`/`deflate` headers were also blocked and are now replaced with `Accept:
application/json` + `gzip`. Set `REELFORGE_CONTACT` (your email or a project URL) before relying on
Wikipedia search; when search is blocked the job continues and the failure is recorded in
`claims.json` notes.
