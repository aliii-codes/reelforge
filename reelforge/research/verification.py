"""Claim checking against text that was actually retrieved.

The automatic check is lexical: it looks for the claim's key terms and numbers in the fetched
source text. It can tell you "the source talks about this, with these numbers" — it cannot
prove the claim is true. Results are labelled accordingly and a human must review them.
"""

from __future__ import annotations

import re

from reelforge.schemas import Claim, ClaimStatus, Script, Source

STOPWORDS = set(
    [
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "if",
        "of",
        "to",
        "in",
        "on",
        "at",
        "by",
        "for",
        "with",
        "from",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "than",
        "then",
        "so",
        "such",
        "can",
        "could",
        "will",
        "would",
        "should",
        "may",
        "might",
        "must",
        "do",
        "does",
        "did",
        "not",
        "no",
        "yes",
        "you",
        "your",
        "we",
        "our",
        "they",
        "their",
        "he",
        "she",
        "his",
        "her",
        "i",
        "me",
        "my",
        "about",
        "into",
        "over",
        "under",
        "more",
        "most",
        "less",
        "least",
        "very",
        "just",
        "also",
        "only",
        "like",
        "up",
        "down",
        "out",
        "what",
        "which",
        "who",
        "whom",
        "how",
        "why",
        "when",
        "where",
        "there",
        "here",
        "all",
        "any",
        "each",
        "every",
        "some",
        "much",
        "many",
        "one",
        "way",
        "here's",
        "it's",
    ]
)

NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100, "thousand": 1000,
}  # fmt: skip


def _terms(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9][a-z0-9.\-]*", text.lower())
    return [w.strip(".-") for w in words if w.strip(".-") and w not in STOPWORDS and len(w) > 2]


def _numbers(text: str) -> set[str]:
    nums = set(re.findall(r"\d+(?:\.\d+)?", text))
    for w in re.findall(r"[a-z]+", text.lower()):
        if w in NUMBER_WORDS and NUMBER_WORDS[w] > 2:
            nums.add(str(NUMBER_WORDS[w]))
    return nums


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > 5 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def assess_claim(claim: Claim, sources: list[Source]) -> Claim:
    if claim.status in (ClaimStatus.HUMAN_VERIFIED, ClaimStatus.HUMAN_REJECTED):
        return claim  # never overwrite a human decision
    linked = [s for s in sources if s.id in claim.source_ids]
    if not linked:
        return claim.model_copy(
            update={"status": ClaimStatus.UNVERIFIED, "check_details": "No source is linked to this claim."}
        )
    opened = [s for s in linked if s.fetched and s.excerpt]
    if not opened:
        return claim.model_copy(
            update={
                "status": ClaimStatus.UNVERIFIED,
                "check_details": "Linked source(s) could not be opened in this run; nothing was checked.",
            }
        )
    terms = {_stem(t) for t in _terms(claim.text) if not t[0].isdigit()}
    nums = _numbers(claim.text)
    best_cov, best_src, best_missing_nums = 0.0, opened[0], nums
    for s in opened:
        body = s.excerpt.lower()
        body_terms = {_stem(t) for t in _terms(body)}
        cov = len(terms & body_terms) / len(terms) if terms else 0.0
        body_nums = _numbers(body)
        missing_nums = {n for n in nums if n not in body_nums}
        if cov > best_cov or (cov == best_cov and len(missing_nums) < len(best_missing_nums)):
            best_cov, best_src, best_missing_nums = cov, s, missing_nums
    detail = (
        f"Lexical check vs [{best_src.id}] {best_src.domain}: {best_cov:.0%} of key terms found"
        + (f"; numbers not found in source text: {sorted(best_missing_nums)}" if best_missing_nums else "")
        + ". Automatic text match only - not proof; review the source."
    )
    if best_cov >= 0.6 and not best_missing_nums:
        status = ClaimStatus.AUTO_SUPPORTED
    elif best_cov >= 0.35:
        status = ClaimStatus.WEAK_EVIDENCE
    else:
        status = ClaimStatus.NOT_FOUND_IN_SOURCE
    return claim.model_copy(update={"status": status, "check_details": detail})


def assess_all(claims: list[Claim], sources: list[Source]) -> list[Claim]:
    return [assess_claim(c, sources) for c in claims]


_FACTUAL = re.compile(
    r"\d|\b(" + "|".join(k for k in NUMBER_WORDS if NUMBER_WORDS[k] > 2) + r"|percent|billion|million|"
    r"thousand|first|largest|fastest|most|every|always|never|invented|released|founded)\b",
    re.I,
)


def extract_candidate_claims(script: Script, start_index: int = 1) -> list[Claim]:
    """Heuristically list sentences that state facts (numbers, superlatives, dates).

    Used when a manual script arrives without an explicit claim list, so nothing factual
    slips through without at least an 'unverified' label.
    """
    claims: list[Claim] = []
    n = start_index
    for si, sec in enumerate(script.sections):
        if sec.role == "cta":
            continue
        for sent in re.split(r"(?<=[.!?])\s+", sec.text):
            if _FACTUAL.search(sent) and len(sent.split()) >= 4:
                claims.append(
                    Claim(
                        id=f"C{n}",
                        text=sent.strip(),
                        section_index=si,
                        uncertainty="Auto-detected factual sentence; no source supplied.",
                    )
                )
                n += 1
    return claims
