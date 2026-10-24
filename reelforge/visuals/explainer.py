"""Explainer style: decide what the viewer should SEE for every narration beat.

Runs after the timing planner (`scene_planner.plan_scenes`), which already cut the narration into
beats and filled in headlines, items, stats and word cues. This pass turns each beat into one of
the explainer treatments (see `scene_manifest.VISUALS`) based on what is being *said*:

- a neural network / layers / connections            -> `network` (nodes + edges drawn on cue)
- training, adjusting weights / parameters / knobs   -> `dials` (a grid of knobs that turn)
- data, text, the internet, examples being consumed  -> `datastream` (sources flowing into the model)
- an ordered process (diagram items)                 -> `steps` (long items) or `chain` (short tokens)
- a number                                           -> `stat`; two numbers compared -> `scale`
- two things compared / an analogy                   -> `compare`
- code / a terminal                                  -> `code` / `terminal`
- otherwise a key term                               -> `keyword` or an icon `card`, alternating

It also derives the continuity furniture of the style: a header pill per section, optional
chapter tabs (from `step:` hints) that advance through the video, the presenter's pose, phrase-
level speech-bubble captions with highlighted key terms, and a sparse set of sound cues.
"""

from __future__ import annotations

import re

from reelforge.captions.alignment import CaptionGroup, CaptionTrack, CaptionWord
from reelforge.schemas import Script
from reelforge.visuals.scene_manifest import Scene

FPS = 30

# Ordered: on a tie the earlier treatment wins.
SEMANTIC = [
    ("network", re.compile(r"\b(neural|networks?|neurons?|layers?|nodes?|connections?|connected)\b", re.I)),
    # change verbs only: "a 7-billion-parameter model" is not about training
    ("dials", re.compile(r"\b(train(s|ed|ing)?|adjust\w*|tweak\w*|knobs?|nudg\w*|dials?|tun(e|es|ed|ing)|updat\w*)\b", re.I)),
    ("datastream", re.compile(r"\b(data|dataset\w*|internet|web|texts?|books?|articles?|examples?|websites?|reads?|reading|feed\w*|pages?)\b", re.I)),
]  # fmt: skip
RICH = {"network", "dials", "datastream"}
MAX_RUNS = 2

EMOJI = [
    (r"neural|brain|learn|think|smart", "🧠"), (r"data|statistic|chart|percent", "📊"), (r"internet|web|online", "🌐"),
    (r"book|text|read|article|word", "📚"), (r"\bai\b|model|robot|chatbot|llm", "🤖"), (r"laptop|computer|cpu|pc\b", "💻"),
    (r"phone|mobile", "📱"), (r"gpu|chip|hardware", "🔌"), (r"cost|money|price|\$", "💸"), (r"fast|speed|quick", "⚡"),
    (r"wrong|error|mistake|fail", "❌"), (r"correct|right|accura", "✅"), (r"guess|predict|next", "🎯"),
    (r"number|math|calcul", "🔢"), (r"image|photo|picture|pixel", "🖼️"), (r"human|people|person|feedback", "🧑"),
    (r"warning|catch|danger|risk", "⚠️"), (r"idea|trick|secret", "💡"), (r"repeat|again|loop|practice|times", "🔁"),
    (r"memory|store|gigabyte|\bgb\b", "💾"), (r"compress|squeeze|shrink", "🗜️"), (r"code|program|python|function", "⌨️"),
    (r"weight|parameter|knob|dial|adjust|tweak", "🎛️"), (r"train", "🏋️"), (r"time|second|minute|hour", "⏱️"),
]  # fmt: skip
ICON_EMOJI = {
    "chip": "💻", "brain": "🧠", "phone": "📱", "bolt": "⚡", "book": "📚", "chart": "📊", "bulb": "💡",
    "warning": "⚠️", "share": "📤", "layers": "🧱", "globe": "🌐", "scale": "⚖️",
}  # fmt: skip
SOURCE_EMOJI = [
    (r"book", "📚"), (r"web|internet|site|online", "🌐"), (r"article|news", "📰"), (r"chat|conversation|forum", "💬"),
    (r"image|photo|picture", "🖼️"), (r"code", "⌨️"), (r"video", "🎬"), (r"wiki|encyclop", "📖"),
]  # fmt: skip

ROLE_LABEL = {
    "hook": ("", "purple"), "explain": ("how it works ⚙️", "orange"), "beat": ("", "orange"),
    "number": ("the numbers 🔢", "green"), "analogy": ("think of it like 💡", "purple"),
    "twist": ("but wait 😮", "pink"), "payoff": ("so remember 📝", "purple"), "cta": ("", "purple"),
}  # fmt: skip
POSE = {
    "hook": "wave", "network": "point", "steps": "point", "chain": "point", "datastream": "point",
    "dials": "point", "stat": "idle", "scale": "think", "compare": "think", "twist": "shrug",
    "cta": "wave", "code": "point", "terminal": "point", "evidence": "point", "checklist": "point",
    "keyword": "idle", "card": "idle", "bars": "point", "reaction": "shrug",
}  # fmt: skip
_STOP = set(
    "a an the of to and or in on is are it that this for with as at by be was were its it's your you we they them "
    "from into than then so but not can just like about more most very also how what why when which who".split()
)


_GENERIC = {
    "here's",
    "heres",
    "there's",
    "theres",
    "actually",
    "really",
    "required",
    "something",
    "things",
    "thing",
    "because",
    "without",
}


def _terms(text: str) -> list[str]:
    """Content words of a phrase, longest first (numbers first): candidate key terms."""
    ws = [re.sub(r"[^\w%.-]", "", w).strip(".").lower() for w in text.split()]
    ws = [w for w in ws if len(w) > 3 and w not in _STOP and w not in _GENERIC and "'" not in w]
    return sorted(ws, key=lambda w: (not any(c.isdigit() for c in w), -len(w)))


def _norm(w: str) -> str:
    return re.sub(r"[^a-z0-9.%]", "", w.lower()).strip(".")


def scene_words(words: list[CaptionWord], s: Scene) -> list[int]:
    return [i for i, w in enumerate(words) if s.start_frame <= int(round(w.start * FPS)) < s.end_frame]


def pick_emoji(text: str, fallback_icon: str = "") -> str:
    low = text.lower()
    for pat, e in EMOJI:
        if re.search(pat, low):
            return e
    return ICON_EMOJI.get(fallback_icon, "💡")


def _semantic(text: str) -> str | None:
    scores = [(len(rx.findall(text)), -k, name) for k, (name, rx) in enumerate(SEMANTIC)]
    best = max(scores)
    return best[2] if best[0] > 0 else None


def _numbers(text: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?\s?(?:%|[a-zA-Z]{1,3}\b)?", text)


def _value(token: str) -> float | None:
    m = re.match(r"(\d+(?:\.\d+)?)\s?([a-zA-Z%]*)", token)
    if not m:
        return None
    mult = {"k": 1e3, "m": 1e6, "b": 1e9, "t": 1e12}.get(m.group(2).lower()[:1], 1.0) if m.group(2) else 1.0
    return float(m.group(1)) * mult


def _dial_label(text: str) -> str:
    m = re.search(
        r"\b((?:billions?|millions?|thousands?|\d[\d.,]*\s?[bmk]?)\s+(?:of\s+)?)?(weights|parameters|knobs|dials|numbers)\b",
        text,
        re.I,
    )
    if not m:
        return "the model's knobs"
    return ("billions of " + m.group(2).lower()) if not m.group(1) else (m.group(1) + m.group(2)).lower().strip()


def _sources(text: str) -> list[str]:
    low = text.lower()
    found = [e for pat, e in SOURCE_EMOJI if re.search(pat, low)]
    base = found + [e for e in ("📚", "🌐", "📰", "💬", "📖") if e not in found]
    if re.search(r"\b(bias\w*|wrong|bad|errors?|mistakes?|junk|fake)\b", low):
        # bad inputs flowing in: mix warning items into the stream
        return ["❌", base[0], "⚠️", base[1], "❌"]
    return base[:5]


def choose_visual(s: Scene, text: str, prev_visual: str, same_section: bool, n: int) -> str:
    """The treatment for one beat. `n` alternates generic fallbacks so they never stack up."""
    t = s.type
    fixed = {
        "hook": "hook", "cta": "cta", "stat": "stat", "twist": "twist", "terminal": "terminal",
        "evidence": "evidence", "bars": "bars", "meme": "reaction", "demo": "code",
    }  # fmt: skip
    if t == "stat" and s.stat is None:
        t = "explain"
    if t in fixed:
        return fixed[t]
    if t == "diagram" and s.items:
        if _semantic(" ".join(s.items) + " " + s.headline) == "network":
            return "network"
        return "chain" if all(len(it) <= 14 for it in s.items) and len(s.items) <= 3 else "steps"
    if t in ("comparison", "analogy", "photo") and s.left and s.right:
        lv, rv = _numbers(s.left), _numbers(s.right)
        return "scale" if lv and rv else "compare"
    sem = _semantic(text + " " + s.headline)
    if sem and (sem != prev_visual or same_section):
        return sem
    generic = "keyword" if t in ("reveal", "kinetic") else ("card", "keyword")[n % 2]
    if generic == prev_visual:
        generic = "card" if generic == "keyword" else "keyword"
    return generic


def _keyword_headline(s: Scene, text: str) -> str:
    from reelforge.visuals.scene_planner import short_headline

    return s.headline or short_headline(text, 6)


def stylize(script: Script, track: CaptionTrack, scenes: list[Scene]) -> tuple[list[Scene], list[str]]:
    """Assign explainer treatments, labels, chapters and poses. Returns (scenes, chapters)."""
    from reelforge.visuals.scene_planner import _match_frames, pick_emphasis

    words = track.words
    roles = {i: sec.role for i, sec in enumerate(script.sections)}
    # Chapters: sections with a `step:` hint, in order of first appearance.
    chapters: list[str] = []
    sec_chapter: dict[int, int] = {}
    for si, sec in enumerate(script.sections):
        name = sec.visual.step.strip()
        if name:
            if name not in chapters and len(chapters) < 4:
                chapters.append(name[:16])
            if name[:16] in chapters:
                sec_chapter[si] = chapters.index(name[:16])
    first_ch = min(sec_chapter) if sec_chapter else None

    out: list[Scene] = []
    section_label: dict[int, tuple[str, str]] = {}
    prev_visual = ""
    prev_section: int | None = None
    n_generic = 0
    runs: dict[str, int] = {}  # separate appearances of each rich diagram
    current = -1
    for k, s in enumerate(scenes):
        idx = scene_words(words, s)
        text = " ".join(words[i].text for i in idx)
        si = s.section_index if s.section_index is not None else (words[idx[0]].section_index if idx else 0)
        sec = script.sections[min(si, len(script.sections) - 1)]
        role = roles.get(si, "explain")
        same_section = si == prev_section
        hint = sec.visual
        visual = (
            hint.visual
            if (hint.visual and not same_section)
            else choose_visual(s, text, prev_visual, same_section, n_generic)
        )
        if k == 0 and not hint.visual:
            visual = "hook"
        if visual in RICH and visual != prev_visual and not hint.visual:
            if runs.get(visual, 0) >= MAX_RUNS:  # a callback is fine once; more is repetition
                visual = "keyword" if prev_visual == "card" or n_generic % 2 else "card"
            else:
                runs[visual] = runs.get(visual, 0) + 1
        upd: dict = {"visual": visual, "section_index": si}
        meta = dict(s.meta)
        cues = list(s.cues)
        if visual in ("card", "keyword"):
            n_generic += 1
        if visual in ("keyword", "card", "hook") and not s.headline:
            upd["headline"] = _keyword_headline(s, text)[:60]
        headline = upd.get("headline", s.headline)
        if visual == "keyword" and not any(c.kind == "word" for c in cues):
            spoken = _match_frames(headline.split(), words, idx[0] if idx else 0, (idx[-1] + 1) if idx else 0)
            last = s.start_frame
            from reelforge.visuals.scene_manifest import Cue

            for wi, f in enumerate(spoken):
                f = min(max(f if f is not None else last + 4, last), s.end_frame - 6)
                cues.append(Cue(frame=max(f, s.start_frame), kind="word", index=wi))
                last = f
            cues.sort(key=lambda c: c.frame)
        if headline:
            upd["emphasis"] = [
                w for w in (s.emphasis or pick_emphasis(headline)) if _norm(w) not in _GENERIC
            ] or _terms(headline)[:1]
        if visual == "dials":
            meta["label"] = _dial_label(text)
        elif visual == "datastream":
            meta["sources"] = _sources(text)
        elif visual == "network":
            n_items = len(s.items)
            meta["layers"] = [3, 4, 4, 2] if n_items != 3 else [3, 4, 2]
        elif visual == "scale":
            lv = _value(_numbers(s.left or "")[0]) or 1.0
            rv = _value(_numbers(s.right or "")[0]) or 1.0
            meta["ratio"] = round(min(lv, rv) / max(lv, rv), 6)
            meta["bigger"] = "right" if rv >= lv else "left"
        elif visual == "stat" and s.stat is not None:
            meta["dots"] = s.stat.suffix.strip() in ("B", "M", "K", "x")
        # Header pill: the section's tag, else its chapter, else a role default. Kept for every
        # beat of the section so the frame has a stable anchor.
        ch = sec_chapter.get(si)
        if hint.tag:
            label, color = hint.tag, "purple" if role in ("hook", "payoff") else "orange"
        elif ch is not None:
            label, color = f"step {ch + 1}: {chapters[ch]}", "orange"
        elif si in section_label:
            label, color = section_label[si]
        else:
            label, color = ROLE_LABEL.get(role, ("", "orange"))
            if not label and role not in ("hook", "cta"):  # e.g. a "beat" section: name its key term
                key = next((w for w in _terms(sec.visual.headline or headline)), "")
                label = f"{key} {pick_emoji(key, s.icon)}" if key else ""
        section_label.setdefault(si, (label, color))
        if role == "twist":
            color = "pink"
        if visual in ("hook", "cta"):
            label = hint.tag or ""
        upd["label"] = label[:40]
        upd["label_color"] = color
        # Chapter tabs: visible from the first chaptered section until the CTA.
        if first_ch is not None and si >= first_ch and role != "cta" and visual not in ("hook", "cta"):
            if ch is not None:
                current = ch
            after_last = si > max(sec_chapter)
            upd["chapter"] = len(chapters) if after_last else max(current, 0)
        else:
            upd["chapter"] = None
        upd["emoji"] = pick_emoji(headline + " " + text, s.icon)
        upd["pose"] = POSE.get(visual, "idle")
        upd["avatar"] = "center" if visual in ("hook", "cta") else ("reaction" if visual == "reaction" else "corner")
        upd["hide_captions"] = False
        upd["background"] = "grid"
        upd["camera"] = "none"
        if k == 0 or same_section:
            upd["transition"] = "cut"
        else:
            upd["transition"] = "wipe" if role == "twist" else "slide"
        upd["meta"] = meta
        upd["cues"] = cues
        if visual == "keyword" and s.type == "kinetic":
            upd["meta"] = {k2: v for k2, v in meta.items() if k2 != "phrases"}
        out.append(s.model_copy(update=upd))
        prev_visual = visual
        prev_section = si
    return out, chapters


def bubble_groups(words: list[CaptionWord], max_words: int = 5, max_chars: int = 30) -> list[list[int]]:
    """Phrase-level word groups for the speech bubble: sentence ends and pauses always break;
    a comma breaks only once the phrase has 3+ words; a lone trailing word ("bytes.") joins the
    phrase before it when it fits."""
    groups: list[list[int]] = []
    cur: list[int] = []
    for i, w in enumerate(words):
        if cur:
            prev = words[cur[-1]]
            chars = sum(len(words[k].text) + 1 for k in cur) + len(w.text)
            if (
                len(cur) >= max_words
                or chars > max_chars
                or re.search(r"[.!?…]$", prev.text)
                or (re.search(r"[,;:—]$", prev.text) and len(cur) >= 3)
                or w.start - prev.end > 0.4
                or w.section_index != prev.section_index
            ):
                groups.append(cur)
                cur = []
        cur.append(i)
    if cur:
        groups.append(cur)
    merged: list[list[int]] = []
    for g in groups:
        if merged and len(g) == 1:
            last = merged[-1]
            fits = sum(len(words[k].text) + 1 for k in last) + len(words[g[0]].text) <= max_chars + 6
            close = words[g[0]].start - words[last[-1]].end <= 0.4
            same = words[g[0]].section_index == words[last[-1]].section_index
            if fits and close and same and not re.search(r"[.!?…]$", words[last[-1]].text):
                last.extend(g)
                continue
        merged.append(g)
    return merged


def bubble_track(track: CaptionTrack, hold: float = 0.4) -> CaptionTrack:
    words = track.words
    groups = bubble_groups(words)
    out = []
    for gi, g in enumerate(groups):
        end = words[g[-1]].end + hold
        if gi + 1 < len(groups):
            end = min(end, words[groups[gi + 1][0]].start)
        end = max(end, words[g[-1]].end)
        out.append(
            CaptionGroup(
                start=round(words[g[0]].start, 3),
                end=round(end, 3),
                word_indices=g,
                text=" ".join(words[k].text for k in g),
            )
        )
    return track.model_copy(update={"groups": out})


def keyword_indices(track: CaptionTrack, scenes: list[Scene], chapters: list[str], base: set[int]) -> set[int]:
    """Caption words to highlight: numbers (base), each beat's key terms, chapter names. At most
    one highlighted word per caption group so emphasis keeps its meaning."""
    words = track.words
    out: set[int] = set()
    terms_by_scene = []
    for s in scenes:
        terms = {_norm(w) for w in s.emphasis} | {_norm(w) for c in chapters for w in c.split()}
        for it in s.items:
            terms |= {_norm(w) for w in it.split() if len(_norm(w)) > 4}
        terms_by_scene.append({t for t in terms if t and t not in _STOP and len(t) > 2})
    for g in track.groups:
        f = int(round(words[g.word_indices[0]].start * FPS))
        si = next((k for k, s in enumerate(scenes) if s.start_frame <= f < s.end_frame), len(scenes) - 1)
        terms = terms_by_scene[si]
        cands = [i for i in g.word_indices if i in base] or [
            i for i in g.word_indices if _norm(words[i].text) in terms or _norm(words[i].text).rstrip("s") in terms
        ]
        if cands:
            out.add(cands[0])
    return out


def sound_cues(scenes: list[Scene]) -> tuple[list[dict], list[dict]]:
    """Sparse, purposeful sounds: a soft whoosh when the section (header) changes, a tick when a
    diagram element lands, a pop for a number, a riser + music drop into the twist. Never two
    sounds within 0.6 s, and at most two ticks per beat."""
    sfx: list[dict] = []
    music: list[dict] = []

    def add(frame: int, kind: str, dur: int = 0) -> None:
        if all(abs(frame - c["frame"]) >= 18 for c in sfx):
            sfx.append({"frame": frame, "kind": kind, "duration_frames": dur})

    for i, s in enumerate(scenes):
        if i and s.transition != "cut":
            add(s.start_frame, "whoosh")
        if s.visual == "twist" and i:
            add(max(0, s.start_frame - 30), "riser", 30)
            music.append({"frame": max(0, s.start_frame - 2), "kind": "drop"})
            music.append({"frame": min(s.end_frame, s.start_frame + 40), "kind": "return"})
        ticks = 0
        for c in s.cues:
            if c.kind == "count":
                add(c.frame, "pop")
            elif c.kind in ("item", "line") and ticks < 2 and c.frame > s.start_frame + 6:
                add(c.frame, "tick")
                ticks += 1
            elif c.kind == "highlight":
                add(c.frame, "pop")
        if s.visual == "evidence" and s.asset:
            add(s.start_frame + 3, "shutter")
        for step in s.meta.get("timing", []):
            sfx.append(
                {"frame": step["type_start"], "kind": "keys", "duration_frames": step["type_end"] - step["type_start"]}
            )
    sfx.sort(key=lambda c: c["frame"])
    return sfx, music
