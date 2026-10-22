"""Prompt templates. Adapted from the reference pipeline's script prompt (English, not Hinglish)."""

from __future__ import annotations

import json

from reelforge.schemas import Script, Source

SYSTEM_WRITER = """You write scripts for 45-60 second vertical videos (Instagram Reels, YouTube Shorts)
about AI and technology, narrated by a faceless creator with an animated avatar.
Rules:
- Plain, conversational English. Short sentences. Spoken rhythm, not essay prose.
- 120-160 words total.
- Never invent statistics, quotations, studies or sources. Only state numbers you can tie to a
  provided source, or simple arithmetic you show (e.g. 7 billion x 2 bytes = 14 GB).
- If a claim cannot be supported by the provided sources, leave it out or mark it uncertain.
- No clickbait you can't pay off, no fake urgency, no "you won't believe".
- Write numbers the way they should be SPOKEN (e.g. "fourteen gigabytes").
Always reply with a single JSON object and nothing else."""

SYSTEM_DESIGNER = """You plan on-screen motion graphics for a vertical explainer video.
Each scene shows a SHORT headline (max 6 words) plus one simple graphic. Readability first.
Always reply with a single JSON object and nothing else."""

STRUCTURE = """Structure (each item is one section with a role):
1. hook: a surprising, TRUE fact or tension, under 3 seconds when spoken.
2. explain: "Here's how it actually works" style explanation.
3. 2-4 beats (roles: beat, number, analogy): include one concrete number and one analogy.
4. twist: a real complication, limitation or misconception ("But here's the catch").
5. payoff: one-line takeaway.
6. cta: natural call to action, e.g. "Send this to a friend who ..."."""


def _sources_block(sources: list[Source]) -> str:
    if not sources:
        return "No sources were retrieved. Do not cite any; mark every factual claim as uncertain."
    parts = []
    for s in sources:
        excerpt = s.excerpt[:1500] if s.fetched else "(page could not be opened; do not rely on it)"
        parts.append(f"[{s.id}] {s.title} <{s.url}>\n{excerpt}")
    return "Sources (cite by id only; never invent URLs):\n\n" + "\n\n".join(parts)


def hooks_prompt(topic: str, context: str) -> str:
    return f"""Topic: {topic}

{context}

Write 5 DIFFERENT candidate opening hooks (max 16 words each) for this video. Use different
angles: surprising number, myth-busting, everyday analogy, question, consequence. Each must be
true according to the sources. Score each 0-10 for scroll-stopping strength AND accuracy.

Return JSON: {{"hooks": [{{"text": str, "angle": str, "rationale": str, "score": number}}]}}"""


def script_prompt(topic: str, hook: str, sources: list[Source]) -> str:
    return f"""Topic: {topic}
Opening hook to use (you may tighten wording): {hook}

{STRUCTURE}

{_sources_block(sources)}

Also: list EVERY factual claim in the script with the source ids that support it, a one-sentence
explanation of how the source supports it, and any uncertainty. A claim with no supporting
source must have an empty source_ids list and a note in "uncertainty".
For each section add "on_screen": a 2-6 word headline for the graphic.
Give a 1-3 sentence post caption and exactly 5 relevant hashtags (no unrelated trending tags).

Return JSON:
{{"title": str,
  "sections": [{{"role": "hook|explain|beat|number|analogy|twist|payoff|cta", "text": str, "on_screen": str}}],
  "claims": [{{"text": str, "source_ids": [str], "support_explanation": str, "uncertainty": str, "section_index": int}}],
  "caption": str,
  "hashtags": [str]}}"""


def revise_prompt(script: Script, feedback: str, sources: list[Source]) -> str:
    current = json.dumps([{"role": s.role, "text": s.text} for s in script.sections], indent=1)
    return f"""Revise this video script according to the feedback. Keep what works, keep the structure
rules, keep it 120-160 words, and keep claims tied to sources.

Feedback: {feedback}

Current title: {script.title}
Current sections:
{current}

{STRUCTURE}

{_sources_block(sources)}

Return the full revised script in the same JSON shape:
{{"title": str, "sections": [{{"role": str, "text": str, "on_screen": str}}],
  "claims": [{{"text": str, "source_ids": [str], "support_explanation": str, "uncertainty": str, "section_index": int}}],
  "caption": str, "hashtags": [str]}}"""


def scene_plan_prompt(script: Script) -> str:
    sections = "\n".join(f"{i}. [{s.role}] {s.text}" for i, s in enumerate(script.sections))
    return f"""Plan one scene per section of this approved script. Do not change the script text.

{sections}

Scene types: hook (big headline + small kicker in subtext), explain (icon + headline + subtext),
stat (stat_value number, stat_prefix/suffix like "$" or "GB", stat_label), analogy (left vs right card),
diagram (2-4 short steps in items), comparison (left vs right), twist (subtext like "BUT..." + headline),
cta (headline + subtext as the share prompt).
Icons: chip, brain, phone, bolt, book, chart, bulb, warning, share, layers, globe, scale.
Expressions: neutral, surprised, thoughtful, happy, skeptical (match the line's emotion).
Only use numbers that literally appear in the section text.

Return JSON: {{"scenes": [{{"section_index": int, "scene": str, "headline": str, "subtext": str,
 "items": [str], "left": str, "right": str, "stat_value": number|null, "stat_prefix": str,
 "stat_suffix": str, "stat_label": str, "icon": str, "expression": str}}]}}"""


def repair_prompt(original_user: str, bad_output: str, error: str) -> str:
    return f"""{original_user}

Your previous reply could not be used: {error}
Previous reply (truncated): {bad_output[:1200]}

Reply again with ONLY a valid JSON object matching the requested shape."""
