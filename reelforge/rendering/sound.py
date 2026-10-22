"""Original, procedurally generated background bed and transition whooshes.

Everything here is synthesized from sine waves and filtered noise by this code, so there is no
third-party licence to track. Levels are kept low; narration always wins.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 48000


def _adsr(n: int, attack: float, release: float) -> np.ndarray:
    env = np.ones(n, dtype=np.float32)
    a, r = min(int(attack * SR), n // 2), min(int(release * SR), n // 2)
    if a:
        env[:a] = np.linspace(0, 1, a)
    if r:
        env[-r:] = np.minimum(env[-r:], np.linspace(1, 0, r))
    return env


def ambient_bed(duration: float, seed: int = 7) -> np.ndarray:
    """Slow-moving pad: two alternating chords of soft detuned sines, with a gentle pulse."""
    n = int(duration * SR)
    t = np.arange(n, dtype=np.float32) / SR
    chords = [[220.0, 261.63, 329.63, 392.0], [196.0, 246.94, 293.66, 369.99]]  # Am7, Gmaj7
    out = np.zeros(n, dtype=np.float32)
    seg = 4.0
    for k in range(int(np.ceil(duration / seg))):
        a, b = int(k * seg * SR), min(n, int((k + 1) * seg * SR) + int(0.8 * SR))
        if a >= n:
            break
        tt = t[a:b]
        env = _adsr(b - a, 1.2, 1.2)
        for f in chords[k % 2]:
            for det in (-0.6, 0.6):
                out[a:b] += env * np.sin(2 * np.pi * (f + det) * tt) * 0.06
    pulse = 0.85 + 0.15 * np.sin(2 * np.pi * (100 / 60) * t)  # ~100 BPM breathing
    rng = np.random.default_rng(seed)
    air = np.convolve(rng.standard_normal(n).astype(np.float32), np.ones(64) / 64, mode="same") * 0.01
    out = (out * pulse + air) * _adsr(n, 1.5, 2.0)
    return out / (np.max(np.abs(out)) + 1e-9) * 0.5


def whoosh(length: float = 0.45, seed: int = 0) -> np.ndarray:
    n = int(length * SR)
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(n).astype(np.float32)
    # sweep a one-pole low-pass cutoff up then down
    cut = np.concatenate([np.linspace(0.02, 0.35, n // 2), np.linspace(0.35, 0.02, n - n // 2)])
    y = np.zeros(n, dtype=np.float32)
    acc = 0.0
    for i in range(n):
        acc += cut[i] * (noise[i] - acc)
        y[i] = acc
    y *= np.hanning(n).astype(np.float32)
    return y / (np.max(np.abs(y)) + 1e-9) * 0.5


def write_bed(path: Path, duration: float) -> None:
    sf.write(path, ambient_bed(duration), SR, subtype="PCM_16")


def tick(length: float = 0.12) -> np.ndarray:
    """Soft, short percussive tick for number/stat reveals."""
    n = int(length * SR)
    t = np.arange(n, dtype=np.float32) / SR
    y = np.sin(2 * np.pi * 1400 * t) * np.exp(-t * 45) + 0.5 * np.sin(2 * np.pi * 2100 * t) * np.exp(-t * 60)
    return (y / (np.max(np.abs(y)) + 1e-9) * 0.35).astype(np.float32)


def write_sfx_track(path: Path, duration: float, cues: Sequence[float | tuple[float, str]]) -> None:
    """Place SFX at cue times. Cues are times (whoosh) or (time, kind) with kind in
    {"whoosh", "tick"}. Whooshes start slightly before the cue so they peak on the cut."""
    n = int(duration * SR)
    out = np.zeros(n, dtype=np.float32)
    for i, cue in enumerate(cues):
        if isinstance(cue, tuple):
            t, kind = float(cue[0]), cue[1]
        else:
            t, kind = float(cue), "whoosh"
        sample = tick() if kind == "tick" else whoosh(seed=i)
        lead = 0.0 if kind == "tick" else 0.2
        a = max(0, int((t - lead) * SR))
        b = min(n, a + len(sample))
        out[a:b] += sample[: b - a]
    sf.write(path, np.clip(out, -1, 1), SR, subtype="PCM_16")
