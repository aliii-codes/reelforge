"""Research sources: free-first search plus real page fetching.

- WikipediaSearch: MediaWiki API, no key. Follows Wikimedia API etiquette (descriptive
  User-Agent, serial requests).
- TavilySearch: optional, used only when TAVILY_API_KEY is set (free plan: 1,000 credits/month
  at time of checking; see docs/providers.md).
- Manual sources: URLs + notes supplied by the user, optionally fetched to confirm they open.

A Source is marked `fetched=True` only if its page was actually retrieved in this run.
"""

from __future__ import annotations

import html
import re
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

from reelforge import __version__
from reelforge.schemas import Source, utcnow


def user_agent(contact: str = "") -> str:
    contact = contact or "local install; no contact configured"
    return f"ReelForgeAI/{__version__} ({contact}) python-httpx/{httpx.__version__}"


class SearchProvider(ABC):
    name = "base"

    @abstractmethod
    def search(self, query: str, limit: int = 4) -> list[Source]: ...


WIKIMEDIA_HEADERS = {"Accept": "application/json", "Accept-Encoding": "gzip"}


class WikipediaSearch(SearchProvider):
    name = "wikipedia"
    API = "https://en.wikipedia.org/w/api.php"

    def __init__(self, contact: str = "", client: httpx.Client | None = None):
        # Wikimedia rejects httpx's default "Accept: */*" + deflate (HTTP 403 robot policy);
        # its API etiquette asks for gzip and a descriptive User-Agent.
        self._client = client or httpx.Client(
            timeout=15, headers=WIKIMEDIA_HEADERS | {"User-Agent": user_agent(contact)}
        )

    def search(self, query: str, limit: int = 4) -> list[Source]:
        r = self._client.get(
            self.API,
            params={"action": "query", "list": "search", "srsearch": query, "srlimit": limit, "format": "json"},
        )
        r.raise_for_status()
        titles = [h["title"] for h in r.json().get("query", {}).get("search", [])]
        if not titles:
            return []
        r2 = self._client.get(
            self.API,
            params={
                "action": "query",
                "prop": "extracts|info",
                "inprop": "url",
                "explaintext": 1,
                "exintro": 1,
                "titles": "|".join(titles),
                "format": "json",
            },
        )
        r2.raise_for_status()
        pages = r2.json().get("query", {}).get("pages", {})
        by_title = {p.get("title"): p for p in pages.values()}
        now = utcnow()
        out = []
        for i, t in enumerate(titles):
            p = by_title.get(t)
            if not p or "fullurl" not in p:
                continue
            out.append(
                Source(
                    id=f"W{i + 1}",
                    url=p["fullurl"],
                    title=f"{t} - Wikipedia",
                    origin="wikipedia",
                    fetched=bool(p.get("extract")),
                    http_status=r2.status_code,
                    accessed_at=now,
                    excerpt=(p.get("extract") or "")[:6000],
                )
            )
        return out


class TavilySearch(SearchProvider):
    name = "tavily"
    API = "https://api.tavily.com/search"

    def __init__(self, api_key: str, client: httpx.Client | None = None):
        self._key = api_key
        self._client = client or httpx.Client(timeout=20)

    def search(self, query: str, limit: int = 4) -> list[Source]:
        r = self._client.post(
            self.API,
            json={"query": query, "max_results": limit, "search_depth": "basic"},
            headers={"Authorization": f"Bearer {self._key}"},
        )
        r.raise_for_status()
        now = utcnow()
        out = []
        for i, res in enumerate(r.json().get("results", [])):
            out.append(
                Source(
                    id=f"T{i + 1}",
                    url=res["url"],
                    title=res.get("title", ""),
                    origin="tavily",
                    fetched=bool(res.get("content")),
                    http_status=200,
                    accessed_at=now,
                    excerpt=(res.get("content") or "")[:6000],
                    notes="excerpt returned by Tavily search",
                )
            )
        return out


_TAG_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>|<[^>]+>", re.S | re.I)


def html_to_text(raw: str) -> tuple[str, str]:
    title_m = re.search(r"<title[^>]*>(.*?)</title>", raw, re.S | re.I)
    title = html.unescape(title_m.group(1)).strip() if title_m else ""
    text = html.unescape(_TAG_RE.sub(" ", raw))
    return title, " ".join(text.split())


def fetch_source(src: Source, contact: str = "", client: httpx.Client | None = None, max_chars: int = 60000) -> Source:
    """Open the source URL and record what was actually retrieved."""
    c = client or httpx.Client(timeout=15, follow_redirects=True, headers={"User-Agent": user_agent(contact)})
    update: dict[str, object] = {"accessed_at": utcnow()}
    try:
        r = c.get(src.url)
        update["http_status"] = r.status_code
        ctype = r.headers.get("content-type", "")
        if r.status_code == 200 and ("html" in ctype or "text" in ctype):
            title, text = html_to_text(r.text) if "html" in ctype else ("", r.text)
            update.update(fetched=bool(text), excerpt=text[:max_chars], title=src.title or title, fetch_error="")
        else:
            update.update(fetched=False, fetch_error=f"HTTP {r.status_code} ({ctype or 'no content-type'})")
    except httpx.HTTPError as e:
        update.update(fetched=False, fetch_error=f"{type(e).__name__}")
    return src.model_copy(update=update)


def parse_sources_file(path: Path) -> list[Source]:
    """Manual sources: one per line, `URL | optional note`. Blank lines and `#` comments ignored."""
    out: list[Source] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        url, _, note = line.partition("|")
        out.append(Source(id=f"M{len(out) + 1}", url=url.strip(), notes=note.strip(), origin="manual"))
    return out


def run_search(query: str, tavily_key: str = "", contact: str = "", limit: int = 4) -> tuple[list[Source], list[str]]:
    """Search with the best available free provider. Returns (sources, notes)."""
    notes: list[str] = []
    providers: list[SearchProvider] = []
    if tavily_key:
        providers.append(TavilySearch(tavily_key))
    providers.append(WikipediaSearch(contact))
    for p in providers:
        try:
            found = p.search(query, limit)
        except httpx.HTTPError as e:
            hint = ""
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 403 and p.name == "wikipedia":
                hint = " (Wikimedia robot policy: set REELFORGE_CONTACT to an email/URL in .env)"
            notes.append(f"{p.name} search failed: {type(e).__name__}{hint}")
            continue
        notes.append(f"{p.name}: {len(found)} results for {query!r}")
        if found:
            return found, notes
    return [], notes
