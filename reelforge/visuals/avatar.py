"""Per-frame avatar animation data derived from the narration.

- mouth_open: loudness envelope (RMS per video frame, normalised, attack/release smoothed).
- visemes: a coarse mouth *shape* guessed from the letters of the word being spoken at that
  moment. This is a heuristic, not phoneme recognition — it adds variety, not accurate lip-sync.
- blink_frames: deterministic natural blink schedule (seeded by job id).
"""

from __future__ import annotations

import hashlib
import random
from pathlib import Path

import numpy as np

from reelforge.captions.alignment import CaptionWord
from reelforge.voice.quality import load_audio

SR = 16000


def mouth_envelope(audio_path: Path, fps: int, n_frames: int) -> list[float]:
    audio = load_audio(audio_path, SR)
    hop = SR / fps
    vals = np.zeros(n_frames, dtype=np.float32)
    for f in range(n_frames):
        a, b = int(f * hop), int((f + 1) * hop)
        seg = audio[a:b]
        if len(seg):
            vals[f] = float(np.sqrt(np.mean(seg**2)))
    db = 20 * np.log10(np.maximum(vals, 1e-6))
    voiced = db[db > -60]
    if not len(voiced):
        return [0.0] * n_frames
    lo, hi = float(np.percentile(voiced, 20)), float(np.percentile(voiced, 95))
    norm = np.clip((db - lo) / max(hi - lo, 1e-3), 0, 1)
    norm[norm < 0.08] = 0
    # attack fast, release slower -> lively but not jittery
    out = np.zeros_like(norm)
    for i, v in enumerate(norm):
        prev = out[i - 1] if i else 0.0
        k = 0.75 if v > prev else 0.35
        out[i] = prev + (v - prev) * k
    return [round(float(x), 3) for x in out]


def _viseme_for(word: str, frac: float) -> str:
    letters = [c for c in word.lower() if c.isalpha()]
    if not letters:
        return "aa"
    c = letters[min(int(frac * len(letters)), len(letters) - 1)]
    if c in "mbp":
        return "mbp"
    if c in "fv":
        return "fv"
    if c in "ouw":
        return "oo"
    if c in "eiy":
        return "ee"
    if c == "a":
        return "aa"
    # consonant: look at the nearest vowel to the right
    for nxt in letters[letters.index(c) :]:
        if nxt in "ouw":
            return "oo"
        if nxt in "eiy":
            return "ee"
        if nxt == "a":
            return "aa"
    return "aa"


def visemes(words: list[CaptionWord], mouth: list[float], fps: int) -> list[str]:
    n = len(mouth)
    out = ["rest"] * n
    for w in words:
        a, b = int(w.start * fps), max(int(w.start * fps) + 1, int(w.end * fps))
        for f in range(a, min(b, n)):
            frac = (f - a) / max(b - a, 1)
            out[f] = _viseme_for(w.text, frac)
    for f in range(n):
        if mouth[f] < 0.06:
            out[f] = "rest"
    return out


def blink_schedule(job_id: str, n_frames: int, fps: int) -> list[int]:
    rng = random.Random(int(hashlib.sha256(job_id.encode()).hexdigest()[:8], 16))
    frames, t = [], rng.uniform(1.0, 2.5)
    while t * fps < n_frames - 6:
        frames.append(int(t * fps))
        t += rng.uniform(2.6, 4.8)
    return frames
