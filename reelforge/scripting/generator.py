"""Topic -> research -> hooks -> script draft, and LLM-assisted revision."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from reelforge.providers import FallbackLLM
from reelforge.providers.base import ScriptDraftOut
from reelforge.research.search import fetch_source, run_search
from reelforge.research.verification import assess_all
from reelforge.schemas import Claim, Hook, ResearchBundle, Script, ScriptSection, Source, VisualHint
from reelforge.scripting.hooks import rank_hooks


@dataclass
class GenerationResult:
    script: Script
    research: ResearchBundle
    origin: str
    notes: list[str] = field(default_factory=list)


def gather_research(
    topic: str,
    *,
    tavily_key: str = "",
    contact: str = "",
    extra_sources: list[Source] | None = None,
    fetch: bool = True,
    queries: list[str] | None = None,
    max_sources: int = 5,
) -> ResearchBundle:
    """Search each query, merge, and keep only sources that actually talk about the topic."""
    sources: list[Source] = []
    notes: list[str] = []
    seen: set[str] = set()
    for q in queries or [topic]:
        found, n = run_search(q, tavily_key=tavily_key, contact=contact, limit=3)
        notes += n
        for s in found:
            if s.url not in seen:
                seen.add(s.url)
                sources.append(s)
    terms = {w for w in re.findall(r"[a-z0-9]+", " ".join([topic, *(queries or [])]).lower()) if len(w) > 3}
    relevant = [s for s in sources if len(terms & set(re.findall(r"[a-z0-9]+", s.excerpt.lower()))) >= 2]
    if len(relevant) < len(sources):
        notes.append(f"dropped {len(sources) - len(relevant)} off-topic search result(s)")
    sources = [s.model_copy(update={"id": f"W{i + 1}"}) for i, s in enumerate(relevant[:max_sources])]
    manual = []
    for s in extra_sources or []:
        manual.append(fetch_source(s, contact) if fetch else s)
    taken = {s.id for s in sources}
    for s in manual:
        if s.id in taken:
            s = s.model_copy(update={"id": f"M{len(taken) + 1}"})
        taken.add(s.id)
        sources.append(s)
    mode: Literal["online", "manual", "none"] = (
        "online" if any(s.fetched for s in sources) else ("manual" if manual else "none")
    )
    if not sources:
        notes.append("No sources retrieved (offline or no results). The script will be unverified.")
    return ResearchBundle(sources=sources, research_mode=mode, notes=notes)


def draft_to_script(
    draft: ScriptDraftOut, topic: str, research: ResearchBundle
) -> tuple[Script, ResearchBundle, list[str]]:
    notes: list[str] = []
    known = {s.id for s in research.sources}
    claims = []
    for i, c in enumerate(draft.claims, 1):
        good = [sid for sid in c.source_ids if sid in known]
        dropped = [sid for sid in c.source_ids if sid not in known]
        unc = c.uncertainty
        if dropped:
            notes.append(f"claim C{i}: removed unknown source ids {dropped} cited by the model")
            unc = (unc + " " if unc else "") + f"Model cited non-existent sources {dropped}."
        sec = c.section_index if c.section_index is not None and 0 <= c.section_index < len(draft.sections) else None
        claims.append(
            Claim(
                id=f"C{i}",
                text=c.text,
                source_ids=good,
                support_explanation=c.support_explanation,
                uncertainty=unc,
                section_index=sec,
            )
        )
    sections = [
        ScriptSection(role=s.role, text=s.text, visual=VisualHint(headline=s.on_screen.strip())) for s in draft.sections
    ]
    tags = [t if t.startswith("#") else f"#{t}" for t in (h.strip().replace(" ", "") for h in draft.hashtags) if t]
    script = Script(title=draft.title, topic=topic, sections=sections, caption=draft.caption, hashtags=tags[:5])
    bundle = research.model_copy(update={"claims": assess_all(claims, research.sources)})
    return script, bundle, notes


def research_context(research: ResearchBundle) -> str:
    if not research.sources:
        return "No research sources are available."
    return "\n".join(f"[{s.id}] {s.title}: {s.excerpt[:900]}" for s in research.sources if s.fetched)


def generate_from_topic(topic: str, llm: FallbackLLM, research: ResearchBundle) -> GenerationResult:
    hookset = llm.run(lambda p: p.generate_hooks(topic, research_context(research)))
    hooks = rank_hooks(
        [Hook(text=h.text, angle=h.angle, rationale=h.rationale, llm_score=h.score) for h in hookset.hooks]
    )
    best = hooks[0]
    draft = llm.run(lambda p: p.generate_script(topic, best.text, research.sources))
    script, bundle, notes = draft_to_script(draft, topic, research)
    script = script.model_copy(update={"hooks": hooks, "selected_hook": 0})
    origin = f"llm:{llm.last_used.label}" if llm.last_used else "llm"
    return GenerationResult(script=script, research=bundle, origin=origin, notes=notes + llm.attempts)


DRAFT_STYLES = [
    ("Numbers first", "Lead with the single most striking, sourced number and build the explanation around it."),
    ("Story & analogy", "Explain through one vivid everyday analogy; keep any numbers few and accurate."),
    ("Myth-busting", "Open by naming a common misconception about the topic, then correct it step by step."),
]


def generate_drafts(topic: str, llm: FallbackLLM, research: ResearchBundle, n: int = 3) -> list[GenerationResult]:
    """2-3 genuinely different script drafts for the user to choose from: one shared research
    pass and hook brainstorm, then each draft gets its own hook and angle."""
    hookset = llm.run(lambda p: p.generate_hooks(topic, research_context(research)))
    hooks = rank_hooks(
        [Hook(text=h.text, angle=h.angle, rationale=h.rationale, llm_score=h.score) for h in hookset.hooks]
    )
    results: list[GenerationResult] = []
    errors: list[str] = []
    for k in range(max(1, min(n, len(DRAFT_STYLES)))):
        name, style = DRAFT_STYLES[k]
        hook_i = k % len(hooks)
        try:
            hook_text = hooks[hook_i].text

            def write(p, hook_text: str = hook_text, style: str = style) -> ScriptDraftOut:
                return p.generate_script(topic, hook_text, research.sources, style)

            draft = llm.run(write, start=k)  # alternate providers between drafts when several are set
        except Exception as e:  # one failed draft shouldn't lose the others
            errors.append(f"draft {k + 1} ({name}) failed: {type(e).__name__}")
            continue
        script, bundle, notes = draft_to_script(draft, topic, research)
        script = script.model_copy(update={"hooks": hooks, "selected_hook": hook_i})
        origin = f"llm:{llm.last_used.label}" if llm.last_used else "llm"
        results.append(
            GenerationResult(script=script, research=bundle, origin=origin, notes=[f"draft:{name}"] + notes + errors)
        )
    if not results:
        raise RuntimeError("no script draft could be generated: " + "; ".join(errors))
    return results


def revise_with_llm(script: Script, research: ResearchBundle, feedback: str, llm: FallbackLLM) -> GenerationResult:
    draft = llm.run(lambda p: p.revise_script(script, feedback, research.sources))
    new_script, bundle, notes = draft_to_script(draft, script.topic, research.model_copy(update={"claims": []}))
    new_script = new_script.model_copy(
        update={"hooks": script.hooks, "selected_hook": script.selected_hook, "handle": script.handle}
    )
    origin = f"revision:llm:{llm.last_used.label}" if llm.last_used else "revision:llm"
    return GenerationResult(script=new_script, research=bundle, origin=origin, notes=notes + llm.attempts)
