"""Derive timed scenes from the approved script and the narration's word timings.

Priority for each section's visuals: explicit hints in the script > LLM scene plan (if one
was generated) > deterministic heuristics. Timing always comes from the aligned captions.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from pathlib import Path

from reelforge.captions.alignment import CaptionTrack, CaptionWord
from reelforge.providers.base import ScenePlanOut
from reelforge.schemas import ClaimStatus, ResearchBundle, Script, ScriptSection, VisualHint
from reelforge.visuals import director, explainer
from reelforge.visuals.avatar import blink_schedule, mouth_envelope, visemes
from reelforge.visuals.beats import emphasis_word_indices, plan_segments
from reelforge.visuals.scene_manifest import (
    ICONS,
    AvatarTrack,
    CaptionGroupF,
    CaptionWordF,
    Cue,
    MusicCue,
    Scene,
    SceneManifest,
    SfxCue,
    StatData,
)

FPS = 30
TAIL_S = 0.8
MAX_SCENE_S = 7.5
MIN_SPLIT_S = 2.5

ROLE_TO_SCENE = {
    "hook": "hook", "explain": "explain", "beat": "explain", "number": "stat", "analogy": "analogy",
    "twist": "twist", "payoff": "explain", "cta": "cta",
}  # fmt: skip
ROLE_TO_EXPRESSION = {
    "hook": "surprised", "explain": "neutral", "beat": "thoughtful", "number": "surprised",
    "analogy": "thoughtful", "twist": "skeptical", "payoff": "happy", "cta": "happy",
}  # fmt: skip
ICON_KEYWORDS = [
    ("phone", "phone"), ("mobile", "phone"), ("laptop", "chip"), ("cpu", "chip"), ("gpu", "chip"), ("chip", "chip"),
    ("memory", "layers"), ("ram", "layers"), ("bit", "layers"), ("weight", "layers"), ("brain", "brain"),
    ("neural", "brain"), ("learn", "brain"), ("train", "brain"), ("think", "bulb"), ("idea", "bulb"),
    ("fast", "bolt"), ("speed", "bolt"), ("energy", "bolt"), ("power", "bolt"), ("data", "chart"),
    ("percent", "chart"), ("grow", "chart"), ("internet", "globe"), ("cloud", "globe"), ("world", "globe"),
    ("book", "book"), ("read", "book"), ("risk", "warning"), ("catch", "warning"), ("worse", "warning"),
    ("trade", "scale"), ("balance", "scale"), ("compare", "scale"), ("share", "share"), ("send", "share"),
]  # fmt: skip
FILLER = re.compile(
    r"^(so|and|but|now|well|okay|here'?s (how|the catch|the thing)[^.]*\.?|the trick is|it turns out)\b[,:]?\s*",
    re.I,
)
UNITS = {
    "gigabytes": "GB",
    "gigabyte": "GB",
    "megabytes": "MB",
    "terabytes": "TB",
    "percent": "%",
    "bits": "-bit",
    "bit": "-bit",
    "bytes": " bytes",
    "billion": "B",
    "million": "M",
    "times": "x",
    "x": "x",
}
WORD_NUMS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
}  # fmt: skip


# --------------------------------------------------------------------------- text heuristics


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


UNIT_SHORT = {"gigabytes": "GB", "gigabyte": "GB", "megabytes": "MB", "terabytes": "TB", "percent": "%"}
WEAK_END = {
    "a",
    "an",
    "the",
    "of",
    "to",
    "and",
    "or",
    "in",
    "on",
    "with",
    "for",
    "is",
    "are",
    "that",
    "has",
    "have",
    "need",
    "needs",
    "about",
    "roughly",
    "called",
    "your",
    "my",
    "just",
    "like",
    "than",
    "it",
}


def compact_numbers(text: str) -> str:
    """'roughly three and a half gigabytes' -> 'roughly 3.5 GB' (on-screen text only)."""
    names = "|".join(sorted(WORD_NUMS, key=len, reverse=True))

    def repl(m: re.Match) -> str:
        value = float(WORD_NUMS[m.group(1).lower()])
        if m.group(2):
            value += WORD_NUMS[m.group(2).lower()]
        if m.group(3):
            value += 0.5
        num = f"{value:g}"
        unit = m.group(4) or ""
        unit = UNIT_SHORT.get(unit.lower(), unit)
        return f"{num} {unit}".strip() if unit else num

    pattern = rf"\b({names})(?:[ -]({names}))?( and a half)?(?: (gigabytes?|megabytes|terabytes|percent))?\b"
    return re.sub(pattern, repl, text, flags=re.I)


def short_headline(text: str, max_words: int = 6) -> str:
    """A complete, short phrase for the screen: prefer a whole sentence or clause that fits,
    and only truncate as a last resort (never ending on a dangling function word)."""
    cands: list[str] = []
    for sent in sentences(text):
        sent = compact_numbers(FILLER.sub("", sent).strip()).rstrip(".!?")
        cands.append(sent)
        cands += [c.strip() for c in re.split(r"[,;:—]", sent) if c.strip()]
    cands = [FILLER.sub("", c).strip() for c in cands]

    def content(c: str) -> int:
        return sum(len(w.strip(",")) > 4 or any(ch.isdigit() for ch in w) for w in c.split())

    max_chars = max_words * 6 + 4  # screen space, not word count, is the real limit
    fitting = [c for c in cands if len(c.split()) >= 3 and len(c) <= max_chars and content(c) >= 2]
    if fitting:
        best = max(fitting, key=lambda c: (content(c), len(c.split())))
        words = best.split()
    else:
        pool = [c for c in cands if len(c.split()) >= 2] or [text]
        words = max(pool, key=content).split()[:max_words]
        while len(words) > 2 and words[-1].lower().strip(",") in WEAK_END:
            words.pop()
    out = " ".join(words).strip(",;: ")
    return out[:1].upper() + out[1:]


def find_number(text: str) -> StatData | None:
    """First number in the text with a unit, from digits or simple number words."""
    low = text.lower().replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(%|[a-z]+)?", low)
    if m:
        value = float(m.group(1))
        unit = UNITS.get(m.group(2) or "", "")
        return StatData(value=value, decimals=0 if value.is_integer() else 1, suffix=unit)
    toks = re.findall(r"[a-z]+", low)
    for i, t in enumerate(toks):
        if t in WORD_NUMS and WORD_NUMS[t] > 1:
            value = float(WORD_NUMS[t])
            j = i + 1
            if j < len(toks) and toks[j] in WORD_NUMS and WORD_NUMS[toks[j]] < 10 and value >= 20:
                value += WORD_NUMS[toks[j]]
                j += 1
            if toks[j : j + 3] == ["and", "a", "half"]:
                value += 0.5
                j += 3
            unit = UNITS.get(toks[j], "") if j < len(toks) else ""
            return StatData(value=value, decimals=0 if value.is_integer() else 1, suffix=unit)
    return None


def pick_icon(text: str) -> str:
    low = text.lower()
    for kw, icon in ICON_KEYWORDS:
        if re.search(rf"\b{kw}", low):
            return icon
    return "chip"


def pick_emphasis(headline: str) -> list[str]:
    words = [w.strip(".,!?") for w in headline.split()]
    nums = [w for w in words if re.search(r"\d", w)]
    if nums:
        return nums[:1]
    longest = sorted(words, key=len, reverse=True)
    return longest[:1] if longest and len(longest[0]) > 4 else []


def split_analogy(text: str) -> tuple[str, str] | None:
    m = re.search(r"(?:think of it like|it'?s like|like)\s+([^.,]+?)(?:[.,]|$)", text, re.I)
    if not m:
        return None
    return "This", m.group(1).strip()[:60]


# --------------------------------------------------------------------------- planning


def _merge_hint(section: ScriptSection, llm: VisualHint | None) -> VisualHint:
    base = section.visual
    if llm is None:
        return base
    data = llm.model_dump()
    for k, v in base.model_dump().items():
        if v not in (None, "", [], 0):
            data[k] = v
    return VisualHint(**data)


def llm_hints(plan: ScenePlanOut | None) -> dict[int, VisualHint]:
    if plan is None:
        return {}
    out = {}
    for s in plan.scenes:
        out[s.section_index] = VisualHint(
            scene=s.scene,
            headline=s.headline,
            subtext=s.subtext,
            items=s.items[:4],
            left=s.left,
            right=s.right,
            stat_value=s.stat_value,
            stat_prefix=s.stat_prefix,
            stat_suffix=s.stat_suffix,
            stat_label=s.stat_label,
            icon=s.icon if s.icon in ICONS else "",
            expression=s.expression,
            step=s.step[:16],
            tag=s.tag[:40],
        )
    return out


def _scene_for(section: ScriptSection, hint: VisualHint, text: str, idx: int) -> dict:
    stype = hint.scene or ROLE_TO_SCENE[section.role]
    headline = hint.headline or short_headline(text)
    d: dict = {
        "type": stype,
        "headline": headline,
        "subtext": hint.subtext,
        "items": hint.items,
        "left": hint.left or None,
        "right": hint.right or None,
        "stat": None,
        "expression": hint.expression or ROLE_TO_EXPRESSION[section.role],
        "icon": hint.icon if hint.icon in ICONS else pick_icon(text),
    }
    if stype == "stat":
        stat = None
        if hint.stat_value is not None:
            stat = StatData(
                value=hint.stat_value,
                decimals=0 if float(hint.stat_value).is_integer() else 1,
                prefix=hint.stat_prefix,
                suffix=hint.stat_suffix,
                label=hint.stat_label,
            )
        else:
            stat = find_number(text)
            if stat is not None:
                stat = stat.model_copy(update={"label": hint.stat_label or short_headline(text, 5)})
        if stat is None:
            d["type"] = "explain"
        else:
            d["stat"] = stat
            if not hint.headline:
                d["headline"] = ""
    if d["type"] in ("analogy", "comparison") and not (d["left"] and d["right"]):
        pair = split_analogy(text)
        if pair:
            d["left"], d["right"] = pair
        else:
            d["type"] = "explain"
    if d["type"] == "diagram" and not 2 <= len(d["items"]) <= 4:
        d["type"] = "explain"
    if d["type"] == "twist" and not d["subtext"]:
        d["subtext"] = "BUT…"
    if d["type"] == "cta" and not d["subtext"]:
        d["subtext"] = short_headline(text, 9)
    d["emphasis"] = pick_emphasis(d["headline"])
    if d["type"] == "hook":
        d["transition"] = "pop"
    elif d["type"] == "twist":
        d["transition"] = "wipe"
    elif d["type"] == "cta":
        d["transition"] = "pop"
    else:
        d["transition"] = ("slide", "fade")[idx % 2]
    return d


def _source_label(section_index: int, research: ResearchBundle) -> str | None:
    by_id = {s.id: s for s in research.sources}
    for c in research.claims:
        if c.section_index != section_index or c.status == ClaimStatus.HUMAN_REJECTED:
            continue
        for sid in c.source_ids:
            if sid in by_id:
                return source_label_text(by_id[sid].url, by_id[sid].domain)
    return None


def source_label_text(url: str, domain: str) -> str:
    """Readable on-screen source: raw GitHub files -> github.com/org/repo."""
    m = re.match(r"https?://raw\.githubusercontent\.com/([^/]+)/([^/]+)/", url)
    if m:
        return f"github.com/{m.group(1)}/{m.group(2)}"
    return domain


MIN_STEP_FRAMES = 30  # a diagram step / demo line must stay on screen at least this long
HOLDING_TYPES = {"diagram", "demo"}  # one scene per section; steps appear on narration beats
FOCUS_TYPES = {"stat", "diagram", "demo", "comparison", "analogy", "reveal", "bars", "photo"}
_STOP = {"the", "a", "an", "of", "to", "and", "or", "in", "on", "is", "are", "it", "that", "this", "for", "with"}


def _norm(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", w.lower())


def _match_frames(phrases: list[str], words: list[CaptionWord], lo: int, hi: int) -> list[int | None]:
    """For each phrase, the frame where its first content word is spoken (in order), else None."""
    out: list[int | None] = []
    k = lo
    for ph in phrases:
        keys = [_norm(t) for t in compact_numbers(ph).split() if len(_norm(t)) > 2 and _norm(t) not in _STOP]
        found = None
        for idx in range(k, hi):
            wn = _norm(compact_numbers(words[idx].text))
            if any(wn and (wn.startswith(key[:5]) or key.startswith(wn[:5])) for key in keys if len(wn) > 2):
                found = idx
                break
        if found is not None:
            out.append(int(round(words[found].start * FPS)))
            k = found + 1
        else:
            out.append(None)
    return out


def _fill_cues(frames: list[int | None], start: int, end: int, beat_frames: list[int]) -> list[int]:
    """Matched steps keep their spoken frame. Unmatched steps go on the next free narration beat
    inside the scene, else a short, even step after the previous one. The first step shows
    within 4 frames of the scene start if nothing places it earlier."""
    pool = [b for b in beat_frames if start < b < end and b not in frames]
    step = max(6, int((end - start) * 0.7 / max(len(frames), 1)))
    out: list[int] = []
    for f in frames:
        prev = out[-1] if out else start
        if f is None:
            later = [b for b in pool if b > prev]
            if later and out:
                f = later[0]
                pool.remove(f)
            else:
                f = start + 4 if not out else prev + step
        out.append(max(f, prev))
    # Keep every step readable: the last one needs ~1 s on screen, earlier ones at least 8 frames
    # apart. Late cues are pulled earlier (still in order) rather than flashing at the very end.
    latest = end - MIN_STEP_FRAMES
    for k in range(len(out) - 1, -1, -1):
        out[k] = max(start, min(out[k], latest))
        latest = out[k] - 8
    for k in range(1, len(out)):
        out[k] = max(out[k], out[k - 1])
    return out


def _says_value(text: str, value: float) -> bool:
    """Does the spoken text contain this number (digits or words, e.g. "fourteen" == 14)?"""
    target = f"{value:g}"
    return target in re.findall(r"\d+(?:\.\d+)?", compact_numbers(text).replace(",", ""))


def _secondary(text: str, role: str, n: int, allow_stat: bool = True) -> dict:
    """Visual for a later beat inside a section: a number becomes a stat, a twist a reveal,
    otherwise alternate between a word-synced reveal and an icon explainer."""
    stat = find_number(text) if allow_stat else None
    if stat is not None and role in ("number", "beat", "explain"):
        label = short_headline(text, 6)
        return {"type": "stat", "stat": stat.model_copy(update={"label": label[:48]}), "headline": ""}
    kind = "reveal" if (role in ("twist", "payoff", "number") or n % 2 == 1) else "explain"
    return {"type": kind, "headline": short_headline(text, 8)}


EvidenceFn = Callable[[str, str], dict | None]


def _anchor_index(phrase: str, words: list[CaptionWord], lo: int, hi: int) -> int | None:
    """Index of the word where `phrase` starts being spoken (first 3 content tokens must match)."""
    want = [_norm(compact_numbers(t)) for t in phrase.split()][:3]
    want = [w for w in want if w]
    for i in range(lo, hi):
        got = [_norm(compact_numbers(words[j].text)) for j in range(i, min(i + len(want), hi))]
        if got == want:
            return i
    return None


def _phrases(words: list[CaptionWord], lo: int, hi: int, emph: set[int], max_words: int = 4) -> list[dict]:
    """Kinetic typography: the spoken words split into short phrases, each word with its frame."""
    out: list[dict] = []
    cur: list[dict] = []
    for i in range(lo, hi):
        w = words[i]
        cur.append({"text": w.text, "frame": int(round(w.start * FPS)), "emph": i in emph})
        if len(cur) >= max_words or re.search(r"[.,!?;:]$", w.text):
            out.append({"words": cur})
            cur = []
    if cur:
        out.append({"words": cur})
    return out


def _bars(items: list[str]) -> list[dict]:
    bars = []
    for it in items:
        label, _, value = it.partition("=")
        try:
            bars.append({"label": label.strip(), "value": float(value.strip())})
        except ValueError:
            continue
    return bars


def plan_scenes(
    script: Script,
    track: CaptionTrack,
    research: ResearchBundle,
    duration_frames: int,
    plan: ScenePlanOut | None = None,
    pace: float = 3.2,
    evidence: EvidenceFn | None = None,
) -> list[Scene]:
    words = track.words
    hints = llm_hints(plan)
    emph_idx = emphasis_word_indices(words)
    emph_set = set(emph_idx)

    # Anchored beats: the author says which phrase each extra visual starts on.
    section_words: dict[int, tuple[int, int]] = {}
    for i, w in enumerate(words):
        lo, hi = section_words.get(w.section_index, (i, i))
        section_words[w.section_index] = (lo, i + 1)
    forced: dict[int, list[int]] = {}
    beat_hints: dict[int, dict[int, VisualHint]] = {}
    for si, sec in enumerate(script.sections):
        if si not in section_words or not sec.beats:
            continue
        lo, hi = section_words[si]
        for bh in sec.beats:
            idx = _anchor_index(bh.at, words, lo + 1, hi) if bh.at else None
            if idx is not None:
                forced.setdefault(si, []).append(idx)
                beat_hints.setdefault(si, {})[idx] = bh
    section_pace = {si: director.pace_for(sec.role) for si, sec in enumerate(script.sections)}
    segs = plan_segments(words, duration_frames / FPS, pace, FPS, section_pace, forced)
    beat_frames = sorted({int(round(sg.start * FPS)) for sg in segs})

    raw: list[dict] = []
    by_section: dict[int, list] = {}
    for sg in segs:
        by_section.setdefault(sg.section_index, []).append(sg)
    for si, sec_segs in sorted(by_section.items()):
        sec = script.sections[si] if si < len(script.sections) else script.sections[-1]
        hint = _merge_hint(sec, hints.get(si))
        anchored = beat_hints.get(si, {})
        primary = _scene_for(sec, hint, sec.text, len(raw))
        holding = primary["type"] in HOLDING_TYPES and not anchored
        groups = [sec_segs] if holding else [[sg] for sg in sec_segs]
        texts = [" ".join(w.text for w in words[g[0].start_word : g[-1].end_word]) for g in groups]
        primary_at = 0
        if not anchored and primary["type"] == "stat" and primary.get("stat") is not None:
            primary_at = next((k for k, t in enumerate(texts) if _says_value(t, primary["stat"].value)), 0)
        for gi, grp in enumerate(groups):
            first, last = grp[0], grp[-1]
            text = texts[gi]
            seg_hint = anchored.get(first.start_word)
            if seg_hint is not None:
                d = _scene_for(sec, seg_hint, text, len(raw))
                d["source_label"] = None
                h = seg_hint
            elif gi == primary_at:
                d = dict(primary)
                d["source_label"] = None if d["type"] == "twist" else _source_label(si, research)
                h = hint
            else:
                d = _scene_for(sec.model_copy(update={"role": "beat"}), VisualHint(), text, len(raw))
                d.update(_secondary(text, sec.role, len(raw), allow_stat=primary["type"] != "stat"))
                if d["type"] == "reveal" and len(text.split()) <= 9:
                    d["type"] = "kinetic"
                d["expression"] = "surprised" if d["type"] == "stat" else ("thoughtful", "neutral")[len(raw) % 2]
                d["source_label"] = None
                d["subtext"] = ""
                d["emphasis"] = pick_emphasis(d["headline"]) if d["headline"] else []
                h = VisualHint()
            d.update(
                start_frame=int(round(first.start * FPS)),
                end_frame=int(round(last.end * FPS)),
                section_index=si,
                _words=(first.start_word, last.end_word),
                _hint=h,
            )
            if h.lines:
                d["lines"] = [ln[:34] for ln in h.lines[:6]]
            raw.append(d)

    merged: list[dict] = []
    for d in raw:
        if merged and d["end_frame"] - d["start_frame"] < 12:
            merged[-1]["end_frame"] = d["end_frame"]
            merged[-1]["_words"] = (merged[-1]["_words"][0], d["_words"][1])
            continue
        merged.append(d)
    merged[0]["start_frame"] = 0
    merged[-1]["end_frame"] = duration_frames
    for a, b in zip(merged, merged[1:], strict=False):
        a["end_frame"] = b["start_frame"]

    for d in merged:
        lo, hi = d["_words"]
        h = d["_hint"]
        start, end = d["start_frame"], d["end_frame"]
        cues: list[Cue] = []
        meta: dict = {}
        t = d["type"]
        if t == "diagram":
            fr = _fill_cues(_match_frames(d["items"], words, lo, hi), start, end, beat_frames)
            cues += [Cue(frame=f, kind="item", index=i) for i, f in enumerate(fr)]
        elif t == "demo":
            fr = _fill_cues(_match_frames(d["lines"], words, lo, hi), start, end, beat_frames)
            cues += [Cue(frame=f, kind="line", index=i) for i, f in enumerate(fr)]
        elif t == "stat":
            num_words = [i for i in emph_idx if lo <= i < hi]
            value_words = [
                i
                for i in num_words  # must start on a number word ("fourteen", "three and a half")
                if d["stat"] and _says_value(" ".join(w.text for w in words[i : i + 4]), d["stat"].value)
            ]
            pick = value_words[0] if value_words else (num_words[0] if num_words else None)
            f = int(round(words[pick].start * FPS)) if pick is not None else start + 4
            cues.append(Cue(frame=min(max(f, start), end - 6), kind="count"))
        elif t in ("comparison", "analogy", "photo") and d.get("right"):
            m = _match_frames([d["right"], "jpeg", "smaller"], words, lo, hi)
            f = next((x for x in m if x is not None), start + (end - start) // 3)
            cues.append(Cue(frame=min(max(f, start + 8), end - 6), kind="item", index=1))
        elif t == "reveal":
            spoken = _match_frames(d["headline"].split(), words, lo, hi)
            last_f = start
            for i, maybe in enumerate(spoken):
                f = maybe if maybe is not None else last_f + 4
                last_f = min(max(f, last_f), end - 6)
                cues.append(Cue(frame=last_f, kind="word", index=i))
        elif t == "kinetic":
            meta["phrases"] = _phrases(words, lo, hi, emph_set)
            d["headline"] = ""
        elif t == "terminal":
            if h.cast:
                meta["cast"] = h.cast
                meta["timing"] = director.terminal_timing(h.cast, start, end)
                meta["highlight"] = h.quote
                for k, step in enumerate(meta["timing"]):
                    cues.append(Cue(frame=min(step["out_at"], end - 1), kind="output", index=k))
                    if h.quote and any(h.quote.lower() in ln.lower() for ln in h.cast["steps"][k]["output"]):
                        cues.append(Cue(frame=min(step["out_at"] + 8, end - 1), kind="highlight", index=k))
            else:
                d["type"] = "explain"  # never fake terminal footage
        elif t == "evidence":
            shot = evidence(h.source, h.quote) if (evidence and h.source and h.quote) else None
            if shot and shot.get("ok"):
                d["asset"] = shot["asset"]
                meta.update({k: shot[k] for k in ("rects", "width", "height", "captured_at", "title") if k in shot})
            else:
                meta["fallback"] = True
            meta["quote"] = h.quote
            meta["domain"] = source_label_text(h.source, re.sub(r"^https?://(www\.)?([^/]+).*$", r"\2", h.source))
            cues.append(Cue(frame=min(start + 14, end - 1), kind="highlight"))
        elif t == "bars":
            meta["bars"] = _bars(d["items"])
            meta["suffix"] = h.stat_suffix
            vals = [b["value"] for b in meta["bars"]]
            spoken = [
                next(
                    (
                        int(round(words[i].start * FPS))
                        for i in range(lo, hi)
                        if _says_value(" ".join(w.text for w in words[i : i + 4]), v)
                    ),
                    None,
                )
                for v in vals
            ]
            fr = _fill_cues(spoken, start, end, beat_frames)
            cues += [Cue(frame=f, kind="item", index=i) for i, f in enumerate(fr)]
            d["items"] = []
        elif t == "meme":
            d["headline"], d["subtext"] = (h.top or d["headline"])[:60], (h.bottom or d["subtext"])[:70]
        for i in emph_idx:
            if lo <= i < hi:
                f = int(round(words[i].start * FPS))
                if start <= f < end:
                    cues.append(Cue(frame=f, kind="emphasis"))
        cues.sort(key=lambda c: c.frame)
        d["cues"] = cues
        d["meta"] = meta
        d["layout"] = "focus" if t in FOCUS_TYPES else "center"

    director.direct(merged, {si: sec.role for si, sec in enumerate(script.sections)})
    scenes = []
    for k, d in enumerate(merged):
        d.pop("_words")
        d.pop("_hint")
        scenes.append(Scene(id=f"s{k + 1:02d}", **d))
    return scenes


def avatar_beats(words: list[CaptionWord], emph: list[int], duration_frames: int) -> tuple[list[int], list[int]]:
    """Brow-raise frames on emphasised words (>= 1.2 s apart) and nod frames at sentence ends."""
    em: list[int] = []
    for i in emph:
        f = int(round(words[i].start * FPS))
        if f < duration_frames and (not em or f - em[-1] >= 36):
            em.append(f)
    nods = [
        int(round(w.end * FPS))
        for w in words
        if re.search(r"[.!?]$", w.text) and int(round(w.end * FPS)) < duration_frames - 8
    ]
    return em, nods


def caption_groups_to_frames(
    track: CaptionTrack, duration_frames: int, emphasis: set[int] | None = None
) -> list[CaptionGroupF]:
    out: list[CaptionGroupF] = []
    prev_end = 0
    for gi, g in enumerate(track.groups):
        gs = max(prev_end, int(round(g.start * FPS)))
        ge = min(duration_frames, max(gs + 1, int(round(g.end * FPS))))
        if gi + 1 < len(track.groups):
            ge = min(ge, max(gs + 1, int(round(track.groups[gi + 1].start * FPS))))
        ws: list[CaptionWordF] = []
        for k in g.word_indices:
            w = track.words[k]
            s = min(max(gs, int(round(w.start * FPS))), ge - 1)
            e = min(ge, max(s + 1, int(round(w.end * FPS))))
            if ws and s < ws[-1].end_frame:
                s = min(ws[-1].end_frame, ge - 1)
                e = max(e, s + 1)
            ws.append(CaptionWordF(text=w.text, start_frame=s, end_frame=min(e, ge), emphasis=k in (emphasis or set())))
        out.append(CaptionGroupF(start_frame=gs, end_frame=ge, words=ws))
        prev_end = ge
    return out


def cover_title(script: Script, scenes: list[Scene]) -> str:
    """Short, legible cover text: the hook's on-screen headline, else a trimmed title."""
    if scenes and scenes[0].type == "hook" and 2 <= len(scenes[0].headline.split()) <= 7:
        return scenes[0].headline[:48]
    return short_headline(script.title, 6)[:48]


def build_manifest(
    *,
    job_id: str,
    script: Script,
    track: CaptionTrack,
    research: ResearchBundle,
    narration: Path,
    audio_duration: float,
    handle: str = "",
    plan: ScenePlanOut | None = None,
    pace: float = 3.2,
    evidence: EvidenceFn | None = None,
    style: str = "creator",
) -> SceneManifest:
    """Everything is timed from the final narration: captions and cuts from its word timestamps,
    the avatar's mouth from its loudness, SFX from the resulting cuts."""
    duration_frames = int(math.ceil((audio_duration + TAIL_S) * FPS))
    scenes = plan_scenes(script, track, research, duration_frames, plan, pace, evidence)
    mouth = mouth_envelope(narration, FPS, duration_frames)
    emph = emphasis_word_indices(track.words)
    em_frames, nod_frames = avatar_beats(track.words, emph, duration_frames)
    chapters: list[str] = []
    caption_track, caption_emph = track, set(emph)
    if style == "explainer":
        scenes, chapters = explainer.stylize(script, track, scenes)
        sfx, music = explainer.sound_cues(scenes)
        caption_track = explainer.bubble_track(track)
        caption_emph = explainer.keyword_indices(caption_track, scenes, chapters, set(emph))
    else:
        sfx, music = director.sound_cues([s.model_dump() | {"cues": s.cues} for s in scenes])
    return SceneManifest(
        style=style,  # type: ignore[arg-type]  # validated by pydantic
        chapters=chapters,
        job_id=job_id,
        title=script.title,
        cover_title=cover_title(script, scenes),
        duration_frames=duration_frames,
        handle=handle or script.handle,
        audio_src="narration.wav",
        scenes=scenes,
        caption_groups=caption_groups_to_frames(caption_track, duration_frames, caption_emph),
        avatar=AvatarTrack(
            mouth_open=mouth,
            visemes=visemes(track.words, mouth, FPS),  # type: ignore[arg-type]
            blink_frames=blink_schedule(job_id, duration_frames, FPS),
            emphasis_frames=em_frames,
            nod_frames=nod_frames,
        ),
        sfx_cues=[SfxCue(**c) for c in sfx if c["frame"] < duration_frames],
        music_cues=[MusicCue(**c) for c in music],
    )
