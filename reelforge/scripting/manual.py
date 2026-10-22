"""Parse a hand-written script file.

Plain text works: paragraphs become sections and roles are inferred. Optional markup gives
full control:

    # title: How a laptop runs a 7B model
    # caption: Post caption text...
    # hashtags: #AI #LLM #Quantization #TechExplained #MachineLearning
    # handle: @yourhandle
    # say: GPT = G P T            (pronunciation used for TTS only)

    [hook]
    A seven-billion-parameter AI model can run on a normal laptop.
    > headline: A 7B model on a laptop | kicker: No data center
    > expression: surprised

    [number]
    ...
    > scene: stat | value: 14 | suffix: GB | label: for 7B weights at 16-bit

    [analogy]
    ...
    > left: A RAW photo | right: A JPEG that still looks right

    [source] https://example.org/page | what this page supports
    [claim] Each 16-bit weight takes two bytes. | https://example.org/page
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

from reelforge.schemas import Claim, ResearchBundle, Script, ScriptSection, SectionRole, Source, VisualHint

ROLES = set(get_args(SectionRole))
_ROLE_ALIASES = {"number": "number", "stat": "number", "payoff": "payoff", "call-to-action": "cta", "intro": "hook"}

_HINT_KEYS = {
    "scene": "scene",
    "headline": "headline",
    "on-screen": "headline",
    "kicker": "subtext",
    "subtext": "subtext",
    "items": "items",
    "lines": "lines",
    "left": "left",
    "right": "right",
    "value": "stat_value",
    "prefix": "stat_prefix",
    "suffix": "stat_suffix",
    "label": "stat_label",
    "icon": "icon",
    "expression": "expression",
}


class ScriptParseError(ValueError):
    pass


def _parse_hint(line: str, hint: dict) -> None:
    for part in line.split("|"):
        if ":" not in part:
            continue
        k, _, v = part.partition(":")
        key = _HINT_KEYS.get(k.strip().lower())
        if key is None:
            raise ScriptParseError(f"unknown visual hint key {k.strip()!r}")
        v = v.strip()
        if key in ("items", "lines"):
            hint[key] = [x.strip() for x in v.split(";") if x.strip()]
        elif key == "stat_value":
            hint[key] = float(v.replace(",", ""))
        else:
            hint[key] = v


def infer_role(index: int, total: int, text: str) -> str:
    low = text.lower()
    if index == 0:
        return "hook"
    if index == total - 1 and re.search(r"\b(send|share|follow|save|comment|tag)\b", low):
        return "cta"
    if re.match(r"^(but|however|here'?s the catch|the catch)", low):
        return "twist"
    if re.search(r"\b(think of it|it'?s like|imagine|like a|similar to)\b", low):
        return "analogy"
    if re.search(r"\d|\b(billion|million|percent|thousand)\b", low):
        return "number"
    if index == 1:
        return "explain"
    if index == total - 2:
        return "payoff"
    return "beat"


def parse_script_text(raw: str, fallback_title: str = "Untitled reel") -> tuple[Script, ResearchBundle, dict[str, str]]:
    """Returns (script, research bundle with manual sources/claims, pronunciation map)."""
    meta: dict[str, str] = {}
    say: dict[str, str] = {}
    blocks: list[dict] = []
    current: dict | None = None
    sources: list[Source] = []
    raw_claims: list[tuple[str, list[str]]] = []
    plain_paragraphs: list[list[str]] = [[]]
    used_markup = False

    for lineno, line in enumerate(raw.splitlines(), 1):
        s = line.strip()
        if s.startswith("#"):
            k, sep, v = s.lstrip("#").partition(":")
            if sep:
                key = k.strip().lower()
                if key == "say":
                    word, _, spoken = v.partition("=")
                    say[word.strip()] = spoken.strip()
                else:
                    meta[key] = v.strip()
            continue
        m = re.match(r"^\[([a-z\- ]+)\]\s*(.*)$", s, re.I)
        if m:
            tag, rest = m.group(1).strip().lower(), m.group(2).strip()
            if tag == "source":
                url, _, note = rest.partition("|")
                sources.append(Source(id=f"M{len(sources) + 1}", url=url.strip(), notes=note.strip(), origin="manual"))
                continue
            if tag == "claim":
                text, _, urls = rest.partition("|")
                raw_claims.append((text.strip(), [u.strip() for u in urls.split(",") if u.strip()]))
                continue
            role = _ROLE_ALIASES.get(tag, tag)
            if role not in ROLES:
                raise ScriptParseError(f"line {lineno}: unknown section tag [{tag}]")
            used_markup = True
            current = {"role": role, "lines": [rest] if rest else [], "hint": {}}
            blocks.append(current)
            continue
        if s.startswith(">"):
            if current is None:
                raise ScriptParseError(f"line {lineno}: visual hint outside a section")
            _parse_hint(s[1:].strip(), current["hint"])
            continue
        if current is not None:
            if s:
                current["lines"].append(s)
        else:
            if s:
                plain_paragraphs[-1].append(s)
            elif plain_paragraphs[-1]:
                plain_paragraphs.append([])

    if not used_markup:
        paras = [" ".join(p) for p in plain_paragraphs if p]
        blocks = [{"role": infer_role(i, len(paras), p), "lines": [p], "hint": {}} for i, p in enumerate(paras)]
    if not blocks:
        raise ScriptParseError("script file contains no narration text")

    sections = [
        ScriptSection(role=b["role"], text=" ".join(b["lines"]), visual=VisualHint(**b["hint"])) for b in blocks
    ]
    hashtags = [h if h.startswith("#") else f"#{h}" for h in meta.get("hashtags", "").split()]
    script = Script(
        title=meta.get("title") or fallback_title,
        topic=meta.get("topic", meta.get("title", "")),
        sections=sections,
        caption=meta.get("caption", ""),
        hashtags=hashtags,
        handle=meta.get("handle", ""),
    )

    url_to_id = {s.url: s.id for s in sources}
    claims: list[Claim] = []
    for text, urls in raw_claims:
        ids: list[str] = []
        for u in urls:
            if u not in url_to_id:
                src = Source(id=f"M{len(sources) + 1}", url=u, origin="manual")
                sources.append(src)
                url_to_id[u] = src.id
            ids.append(url_to_id[u])
        claims.append(Claim(id=f"C{len(claims) + 1}", text=text, source_ids=ids, section_index=_locate(text, sections)))
    research = ResearchBundle(sources=sources, claims=claims, research_mode="manual" if sources else "none")
    return script, research, say


def _locate(claim_text: str, sections: list[ScriptSection]) -> int | None:
    """Best-matching section for a claim, by shared words."""
    cw = set(re.findall(r"[a-z0-9]+", claim_text.lower()))
    best, best_i = 0, None
    for i, s in enumerate(sections):
        overlap = len(cw & set(re.findall(r"[a-z0-9]+", s.text.lower())))
        if overlap > best:
            best, best_i = overlap, i
    return best_i


def parse_script_file(path: Path) -> tuple[Script, ResearchBundle, dict[str, str]]:
    return parse_script_text(path.read_text(encoding="utf-8"), fallback_title=path.stem.replace("_", " ").title())


__all__ = ["Claim", "ScriptParseError", "parse_script_file", "parse_script_text"]
