"""Narration beats: where a visual change should land, derived from the final voice-over.

Candidate cut points come from the timing of what was actually said:

- section starts (always cuts),
- sentence ends (strong),
- real pauses in the audio (>= 0.3 s between words; strength grows with length),
- clause commas (weak).

Cuts are placed a couple of frames *before* the next word's onset (common editing practice so
the picture changes as the word lands). Within each section a small dynamic programme picks the
cut set whose segment lengths are closest to the target pace while preferring strong beats and
never producing segments shorter than `min_s`.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from reelforge.captions.alignment import CaptionWord

ANTICIPATE_FRAMES = 2


@dataclass
class Beat:
    word_index: int  # first word after the cut
    time: float  # cut time in seconds (slightly before the word)
    strength: float  # 0..1
    reason: str


@dataclass
class Segment:
    section_index: int
    start_word: int
    end_word: int  # exclusive
    start: float
    end: float

    @property
    def length(self) -> float:
        return self.end - self.start


def candidate_beats(words: list[CaptionWord], fps: int = 30) -> list[Beat]:
    out: list[Beat] = []
    lead = ANTICIPATE_FRAMES / fps
    for i in range(1, len(words)):
        prev, w = words[i - 1], words[i]
        gap = w.start - prev.end
        t = max(prev.end, w.start - lead)
        if w.section_index != prev.section_index:
            out.append(Beat(i, t, 1.0, "section"))
        elif re.search(r"[.!?…]$", prev.text):
            out.append(Beat(i, t, 0.8, "sentence"))
        elif gap >= 0.3:
            out.append(Beat(i, t, min(0.75, 0.4 + gap / 2), f"pause {gap:.2f}s"))
        elif re.search(r"[,;:—]$", prev.text):
            out.append(Beat(i, t, 0.3, "clause"))
    return out


def segment_section(
    words: list[CaptionWord],
    beats: list[Beat],
    first: int,
    last: int,
    start: float,
    end: float,
    pace: float,
    min_s: float = 1.8,
) -> list[tuple[int, float]]:
    """Choose cuts inside one section. Returns [(word_index, time)] of the chosen inner cuts."""
    cands = [b for b in beats if first < b.word_index < last and start + min_s <= b.time <= end - min_s]
    points = [(first, start, 1.0)] + [(b.word_index, b.time, b.strength) for b in cands] + [(last, end, 1.0)]
    n = len(points)
    best = [math.inf] * n
    prev = [-1] * n
    best[0] = 0.0
    for j in range(1, n):
        for i in range(j):
            length = points[j][1] - points[i][1]
            if length < min_s and not (i == 0 and j == n - 1):
                continue
            # cost: distance from target pace (long segments cost more than short ones), plus
            # a penalty for cutting on a weak beat
            over = max(0.0, length - pace)
            under = max(0.0, pace - length)
            cost = over**2 * 1.4 + under**2 + (1.0 - points[j][2]) * 1.2 * (j != n - 1)
            if best[i] + cost < best[j]:
                best[j], prev[j] = best[i] + cost, i
    cuts: list[tuple[int, float]] = []
    j = n - 1
    while prev[j] > 0:
        j = prev[j]
        cuts.append((points[j][0], points[j][1]))
    return sorted(cuts)


def plan_segments(words: list[CaptionWord], duration: float, pace: float, fps: int = 30) -> list[Segment]:
    """Split the narration into visual segments aligned to beats."""
    if not words:
        return []
    beats = candidate_beats(words, fps)
    section_starts = [0] + [b.word_index for b in beats if b.reason == "section"]
    bounds = section_starts + [len(words)]
    segs: list[Segment] = []
    for k in range(len(bounds) - 1):
        first, last = bounds[k], bounds[k + 1]
        start = 0.0 if k == 0 else next(b.time for b in beats if b.word_index == first)
        end = duration if last == len(words) else next(b.time for b in beats if b.word_index == last)
        cuts = segment_section(words, beats, first, last, start, end, pace)
        edges = [(first, start)] + cuts + [(last, end)]
        for (a, ta), (b, tb) in zip(edges, edges[1:], strict=False):
            segs.append(Segment(words[first].section_index, a, b, ta, tb))
    return segs


def emphasis_word_indices(words: list[CaptionWord], extra: set[str] | None = None) -> list[int]:
    """Words worth a visual accent: numbers/quantities and explicitly emphasised terms."""
    extra = {e.lower() for e in (extra or set())}
    num = re.compile(
        r"^(\d[\d.,]*%?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
        r"fifteen|sixteen|twenty|thirty|forty|fifty|hundred|thousand|million|billion|half)$"
    )
    out = []
    for i, w in enumerate(words):
        core = re.sub(r"[^a-z0-9.%-]", "", w.text.lower()).strip(".")
        parts = core.split("-")
        if any(num.match(p) for p in parts if p) or core in extra:
            out.append(i)
    # collapse runs ("seven billion") to their first word
    return [i for k, i in enumerate(out) if k == 0 or out[k - 1] != i - 1]
