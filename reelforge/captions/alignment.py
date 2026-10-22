"""Align the approved script's words to the narration transcript's word timestamps.

Captions show the *script's* spelling and punctuation, timed by Whisper's word timestamps
from the actual selected narration. Script words Whisper did not hear are interpolated
between neighbours and flagged `approximate`.
"""

from __future__ import annotations

import difflib
import re

from pydantic import BaseModel, Field

from reelforge.schemas import Script, Transcript, Word
from reelforge.voice.quality import normalize_words


class CaptionWord(BaseModel):
    text: str
    start: float
    end: float
    section_index: int
    approximate: bool = False


class CaptionGroup(BaseModel):
    start: float
    end: float
    word_indices: list[int]
    text: str


class CaptionTrack(BaseModel):
    words: list[CaptionWord]
    groups: list[CaptionGroup]
    timing_source: str
    word_level: bool
    approximate_words: int = 0
    notes: list[str] = Field(default_factory=list)
    words_source: str = "script"


def _display_tokens(script: Script) -> list[tuple[str, int]]:
    toks = []
    for si, sec in enumerate(script.sections):
        for t in sec.text.split():
            toks.append((t, si))
    return toks


def _segment_level_words(transcript: Transcript) -> list[Word]:
    """Fallback when no word timestamps exist: spread each segment's words by character
    length. Every resulting word is an approximation."""
    out = []
    for seg in transcript.segments:
        ws = seg.text.split()
        total = sum(len(w) for w in ws) or 1
        t = seg.start
        for w in ws:
            d = (seg.end - seg.start) * len(w) / total
            out.append(Word(text=w, start=round(t, 3), end=round(t + d, 3)))
            t += d
    return out


def _match(script: Script, transcript: Transcript) -> tuple[list[tuple[str, int]], list[Word], dict[int, list[int]]]:
    """Map script display tokens to heard (transcript) word indices."""
    display = _display_tokens(script)
    heard = transcript.words if transcript.word_level else _segment_level_words(transcript)

    s_norm: list[str] = []
    s_owner: list[int] = []
    for di, (tok, _) in enumerate(display):
        for norm in normalize_words(tok) or [tok.lower()]:
            s_norm.append(norm)
            s_owner.append(di)
    h_norm: list[str] = []
    h_owner: list[list[int]] = []
    for hi, w in enumerate(heard):
        for n in normalize_words(w.text):
            # Whisper often emits spelled-out acronyms as separate words ("G", "P", "T."):
            # merge consecutive single letters across words, like normalize_words does within one.
            if (
                len(n) == 1
                and n.isalpha()
                and n not in ("a", "i")
                and h_norm
                and h_owner[-1][-1] == hi - 1
                and len(heard[hi - 1].text.strip(".,!?")) == 1
                and h_norm[-1].isalpha()
                and h_norm[-1] not in ("a", "i")
            ):
                h_norm[-1] += n
                h_owner[-1].append(hi)
                continue
            h_norm.append(n)
            h_owner.append([hi])

    matched: dict[int, list[int]] = {}
    sm = difflib.SequenceMatcher(a=s_norm, b=h_norm, autojunk=False)
    for block in sm.get_matching_blocks():
        for k in range(block.size):
            matched.setdefault(s_owner[block.a + k], []).extend(h_owner[block.b + k])
    # Pair up same-length substitutions too (e.g. "fourteen" heard as "forty"): timing is still right.
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "replace" and (i2 - i1) == (j2 - j1):
            for k in range(i2 - i1):
                matched.setdefault(s_owner[i1 + k], []).extend(h_owner[j1 + k])
    return display, heard, matched


def transcript_caption_words(script: Script, transcript: Transcript) -> list[CaptionWord]:
    """Captions that show what was actually said (Whisper's words and timing). Each word is
    assigned to the script section it lines up with, so scene planning still works."""
    display, heard, matched = _match(script, transcript)
    section_of_heard: dict[int, int] = {}
    display_of_heard: dict[int, int] = {}
    for di, his in matched.items():
        for hi in his:
            section_of_heard.setdefault(hi, display[di][1])
            display_of_heard.setdefault(hi, di)
    n_sections = max(si for _, si in display) + 1
    section_tokens = {si: [di for di, (_, s2) in enumerate(display) if s2 == si] for si in range(n_sections)}
    out: list[CaptionWord] = []
    section, furthest = 0, -1
    for hi, w in enumerate(heard):
        if hi in section_of_heard:
            section = section_of_heard[hi]
            furthest = max(furthest, display_of_heard[hi])
        elif hi and re.search(r"[.!?]$", heard[hi - 1].text) and section + 1 < n_sections:
            # an unmatched (ad-libbed) sentence: move on once most of this section was spoken
            toks = section_tokens[section]
            covered = sum(1 for di in toks if di <= furthest) / max(len(toks), 1)
            if covered >= 0.6:
                section += 1
        out.append(
            CaptionWord(
                text=w.text, start=w.start, end=w.end, section_index=section, approximate=not transcript.word_level
            )
        )
    for k in range(1, len(out)):
        if out[k].start < out[k - 1].end:
            out[k - 1].end = round(max(out[k - 1].start + 0.04, out[k].start), 3)
        if out[k].end <= out[k].start:
            out[k].end = round(out[k].start + 0.06, 3)
    return out


def align_script_to_transcript(script: Script, transcript: Transcript) -> list[CaptionWord]:
    display, heard, matched = _match(script, transcript)
    words: list[CaptionWord | None] = []
    for di, (tok, si) in enumerate(display):
        idxs = matched.get(di)
        if idxs:
            ws = [heard[i] for i in idxs]
            words.append(
                CaptionWord(
                    text=tok,
                    start=min(w.start for w in ws),
                    end=max(w.end for w in ws),
                    section_index=si,
                    approximate=not transcript.word_level,
                )
            )
        else:
            words.append(None)

    # Interpolate unmatched runs between known neighbours.
    duration = transcript.duration
    i = 0
    while i < len(words):
        if words[i] is not None:
            i += 1
            continue
        j = i
        while j < len(words) and words[j] is None:
            j += 1
        prev_end = words[i - 1].end if i > 0 and words[i - 1] else 0.0  # type: ignore[union-attr]
        next_start = words[j].start if j < len(words) and words[j] else duration  # type: ignore[union-attr]
        span = max(next_start - prev_end, 0.12 * (j - i))
        lens = [len(display[k][0]) for k in range(i, j)]
        total = sum(lens) or 1
        t = prev_end
        for k in range(i, j):
            d = span * lens[k - i] / total
            words[k] = CaptionWord(
                text=display[k][0],
                start=round(t, 3),
                end=round(t + d, 3),
                section_index=display[k][1],
                approximate=True,
            )
            t += d
        i = j

    final = [w for w in words if w is not None]
    # Enforce monotonic, non-overlapping timing.
    for k in range(1, len(final)):
        if final[k].start < final[k - 1].end:
            mid = max(final[k - 1].start + 0.04, min(final[k].start, final[k - 1].end))
            final[k - 1].end = round(mid, 3)
            final[k].start = round(max(final[k].start, mid), 3)
        if final[k].end <= final[k].start:
            final[k].end = round(final[k].start + 0.06, 3)
    return final


_BREAK_AFTER = re.compile(r"[.!?;:,…—]$")


def group_words(
    words: list[CaptionWord], max_words: int = 3, max_chars: int = 20, max_gap: float = 0.45, hold: float = 0.5
) -> list[CaptionGroup]:
    groups: list[list[int]] = []
    cur: list[int] = []
    for i, w in enumerate(words):
        if cur:
            prev = words[cur[-1]]
            chars = sum(len(words[k].text) + 1 for k in cur) + len(w.text)
            if (
                len(cur) >= max_words
                or chars > max_chars
                or _BREAK_AFTER.search(prev.text)
                or w.start - prev.end > max_gap
                or w.section_index != prev.section_index
            ):
                groups.append(cur)
                cur = []
        cur.append(i)
    if cur:
        groups.append(cur)

    out = []
    for gi, g in enumerate(groups):
        start = words[g[0]].start
        end = words[g[-1]].end + hold
        if gi + 1 < len(groups):
            end = min(end, words[groups[gi + 1][0]].start)
        end = max(end, words[g[-1]].end)
        out.append(
            CaptionGroup(
                start=round(start, 3), end=round(end, 3), word_indices=g, text=" ".join(words[k].text for k in g)
            )
        )
    return out


def build_caption_track(script: Script, transcript: Transcript, source: str = "script") -> CaptionTrack:
    """`source`: "script" (script spelling, Whisper timing), "transcript" (what was said), or
    "auto" (script unless the narration departs from it by more than 8% of words)."""
    from reelforge.voice.quality import compare_transcript

    notes: list[str] = []
    if source == "auto":
        wer = compare_transcript(script.full_text, transcript.text).wer
        source = "transcript" if wer > 0.08 else "script"
        notes.append(f"caption source auto-selected: {source} (narration vs script word difference {wer:.1%})")
    if source == "transcript":
        words = transcript_caption_words(script, transcript)
        timing = f"{transcript.model} words and timestamps on the final narration (captions show what was said)"
    else:
        words = align_script_to_transcript(script, transcript)
        timing = f"{transcript.model} word timestamps on the final narration, aligned to the approved script"
    groups = group_words(words)
    approx = sum(1 for w in words if w.approximate)
    if not transcript.word_level:
        notes.append("Word timestamps unavailable: timings spread across segments (approximate).")
    if approx and source == "script":
        notes.append(
            f"{approx} of {len(words)} words were not matched in the transcript; their timing is interpolated."
        )
    return CaptionTrack(
        words=words,
        groups=groups,
        timing_source=timing,
        word_level=transcript.word_level,
        approximate_words=approx,
        notes=notes,
        words_source=source,
    )
