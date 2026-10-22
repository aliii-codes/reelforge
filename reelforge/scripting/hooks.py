"""Rank candidate hooks. Combines the LLM's own score with transparent heuristics, so the
first hook returned is never picked just because it came first."""

from __future__ import annotations

import re

from reelforge.schemas import Hook

CLICKBAIT = re.compile(r"you won'?t believe|shocking|insane|nobody is talking|mind[- ]?blowing|secret they", re.I)


def heuristic_score(text: str) -> tuple[float, list[str]]:
    words = text.split()
    score, why = 5.0, []
    if len(words) <= 14:
        score += 1.5
        why.append("short")
    elif len(words) > 20:
        score -= 2
        why.append("too long to land in ~3s")
    if re.search(r"\d|\b(billion|million|percent|half|twice|times)\b", text, re.I):
        score += 1.5
        why.append("concrete number")
    if re.search(r"\b(you|your)\b", text, re.I):
        score += 0.5
        why.append("speaks to viewer")
    if re.search(r"\b(but|actually|instead|without|not|never|only)\b", text, re.I) or text.endswith("?"):
        score += 1.0
        why.append("tension/contrast")
    if CLICKBAIT.search(text):
        score -= 3
        why.append("clickbait phrasing")
    return max(0.0, min(10.0, score)), why


def rank_hooks(hooks: list[Hook]) -> list[Hook]:
    out = []
    seen: set[str] = set()
    for h in hooks:
        key = re.sub(r"\W+", " ", h.text.lower()).strip()
        if key in seen:
            continue  # drop near-verbatim duplicates
        seen.add(key)
        hs, why = heuristic_score(h.text)
        llm = h.llm_score if h.llm_score is not None else hs
        total = round(0.6 * llm + 0.4 * hs, 2)
        rationale = h.rationale + (f" [heuristics: {', '.join(why)}]" if why else "")
        out.append(h.model_copy(update={"heuristic_score": hs, "score": total, "rationale": rationale.strip()}))
    return sorted(out, key=lambda h: h.score, reverse=True)
