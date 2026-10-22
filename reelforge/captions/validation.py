"""Detect missing, duplicate, overlapping, out-of-order or out-of-bounds caption timings."""

from __future__ import annotations

from dataclasses import dataclass, field

from reelforge.captions.alignment import CaptionTrack


@dataclass
class CaptionReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings}


def validate_captions(
    track: CaptionTrack,
    audio_duration: float,
    expected_words: int | None = None,
    max_group_chars: int = 26,
    max_group_words: int = 4,
    tolerance: float = 0.05,
) -> CaptionReport:
    r = CaptionReport()
    ws = track.words
    if not ws:
        r.errors.append("no caption words")
        return r
    if expected_words is not None and len(ws) != expected_words:
        r.errors.append(f"{len(ws)} caption words but the script has {expected_words}")
    for i, w in enumerate(ws):
        if not w.text.strip():
            r.errors.append(f"word {i} has empty text")
        if w.end <= w.start:
            r.errors.append(f"word {i} '{w.text}' has non-positive duration ({w.start}-{w.end})")
        if w.start < -tolerance or w.end > audio_duration + tolerance:
            r.errors.append(f"word {i} '{w.text}' ({w.start}-{w.end}) is outside the audio (0-{audio_duration:.2f})")
        if i:
            p = ws[i - 1]
            if w.start < p.start:
                r.errors.append(f"word {i} '{w.text}' starts before word {i - 1} (out of order)")
            elif w.start < p.end - 1e-6:
                r.errors.append(f"word {i} '{w.text}' overlaps word {i - 1}")
            if w.text == p.text and abs(w.start - p.start) < 1e-6:
                r.errors.append(f"word {i} duplicates word {i - 1}")
        if w.end - w.start > 2.0:
            r.warnings.append(f"word {i} '{w.text}' lasts {w.end - w.start:.1f}s (check alignment)")

    seen: set[int] = set()
    for gi, g in enumerate(track.groups):
        if g.end <= g.start:
            r.errors.append(f"group {gi} has non-positive duration")
        if gi and g.start < track.groups[gi - 1].end - 1e-6:
            r.errors.append(f"group {gi} overlaps group {gi - 1}")
        if len(g.text) > max_group_chars and len(g.word_indices) > 1:
            r.errors.append(f"group {gi} '{g.text}' has {len(g.text)} chars (max {max_group_chars})")
        if len(g.word_indices) > max_group_words:
            r.errors.append(f"group {gi} has {len(g.word_indices)} words (max {max_group_words})")
        for k in g.word_indices:
            if k in seen:
                r.errors.append(f"word {k} appears in more than one group")
            seen.add(k)
    missing = set(range(len(ws))) - seen
    if missing:
        r.errors.append(f"{len(missing)} words are not in any caption group")
    if track.approximate_words:
        share = track.approximate_words / len(ws)
        (r.errors if share > 0.25 else r.warnings).append(
            f"{track.approximate_words} words ({share:.0%}) have interpolated timing"
        )
    return r
