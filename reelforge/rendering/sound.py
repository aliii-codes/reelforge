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


def write_bed(
    path: Path, duration: float, drops: list[tuple[float, float]] | None = None, fade_out: float = 1.5
) -> None:
    """Music bed with automation: silent during `drops` (start, end in seconds, 80 ms ramps) and a
    fade-out at the end."""
    bed = ambient_bed(duration)
    n = len(bed)
    env = np.ones(n, dtype=np.float32)
    ramp = int(0.08 * SR)
    for t0, t1 in drops or []:
        a, b = max(0, int(t0 * SR)), min(n, int(t1 * SR))
        if b <= a:
            continue
        env[a:b] = 0
        lo = max(0, a - ramp)
        env[lo:a] = np.minimum(env[lo:a], np.linspace(1, 0, a - lo))
        hi = min(n, b + ramp)
        env[b:hi] = np.minimum(env[b:hi], np.linspace(0, 1, hi - b))
    f = min(n, int(fade_out * SR))
    if f:
        env[-f:] *= np.linspace(1, 0, f)
    sf.write(path, bed * env, SR, subtype="PCM_16")


def tick(length: float = 0.12) -> np.ndarray:
    """Soft, short percussive tick for number/stat reveals."""
    n = int(length * SR)
    t = np.arange(n, dtype=np.float32) / SR
    y = np.sin(2 * np.pi * 1400 * t) * np.exp(-t * 45) + 0.5 * np.sin(2 * np.pi * 2100 * t) * np.exp(-t * 60)
    return (y / (np.max(np.abs(y)) + 1e-9) * 0.35).astype(np.float32)


def impact(length: float = 0.55, seed: int = 0) -> np.ndarray:
    """Low thump with a short noisy transient - lands with a number slam or a flash cut."""
    n = int(length * SR)
    t = np.arange(n, dtype=np.float32) / SR
    freq = 40 + 70 * np.exp(-t * 18)
    body = np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t * 7)
    noise = np.random.default_rng(seed).standard_normal(n).astype(np.float32) * np.exp(-t * 60) * 0.35
    y = body + noise
    return (y / (np.max(np.abs(y)) + 1e-9) * 0.9).astype(np.float32)


def riser(length: float, seed: int = 0) -> np.ndarray:
    """Rising filtered noise + pitch, ending exactly at the cut it leads into."""
    n = max(1, int(length * SR))
    t = np.linspace(0, 1, n, dtype=np.float32)
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(n).astype(np.float32)
    out = np.zeros(n, dtype=np.float32)
    acc = 0.0
    cut = 0.02 + 0.3 * t**2
    for i in range(n):
        acc += cut[i] * (noise[i] - acc)
        out[i] = acc
    tone = np.sin(2 * np.pi * np.cumsum(220 + 660 * t**2) / SR) * 0.25
    y = (out + tone) * (t**1.6)
    return (y / (np.max(np.abs(y)) + 1e-9) * 0.5).astype(np.float32)


def pop(length: float = 0.09) -> np.ndarray:
    n = int(length * SR)
    t = np.arange(n, dtype=np.float32) / SR
    y = np.sin(2 * np.pi * np.cumsum(1100 - 500 * t / length) / SR) * np.exp(-t * 55)
    return (y / (np.max(np.abs(y)) + 1e-9) * 0.4).astype(np.float32)


def keys(length: float, seed: int = 0) -> np.ndarray:
    """Soft keyboard clicks (~15/s with jitter) for the time a command is being typed."""
    n = max(1, int(length * SR))
    rng = np.random.default_rng(seed)
    out = np.zeros(n, dtype=np.float32)
    click_n = int(0.012 * SR)
    t = 0.0
    while t < length - 0.02:
        a = int(t * SR)
        c = rng.standard_normal(click_n).astype(np.float32) * np.exp(-np.arange(click_n) / (click_n / 5))
        c = (np.convolve(c, np.ones(4) / 4, mode="same") * rng.uniform(0.5, 1.0)).astype(np.float32)
        b = min(n, a + click_n)
        out[a:b] += c[: b - a]
        t += rng.uniform(0.045, 0.09)
    return (out / (np.max(np.abs(out)) + 1e-9) * 0.3).astype(np.float32)


def shutter() -> np.ndarray:
    """Two quick mechanical clicks, for a screenshot landing on screen."""
    n = int(0.12 * SR)
    out = np.zeros(n, dtype=np.float32)
    rng = np.random.default_rng(3)
    for start in (0.0, 0.045):
        a = int(start * SR)
        k = int(0.018 * SR)
        click = rng.standard_normal(k).astype(np.float32) * np.exp(-np.arange(k) / (k / 6))
        out[a : a + k] += click
    return (out / (np.max(np.abs(out)) + 1e-9) * 0.45).astype(np.float32)


def write_sfx_track(path: Path, duration: float, cues: Sequence) -> None:
    """Place SFX at cue times. A cue is a time (whoosh), (time, kind) or (time, kind, length_s).
    Whooshes start slightly early so they peak on the cut; risers end on their target."""
    n = int(duration * SR)
    out = np.zeros(n, dtype=np.float32)
    for i, cue in enumerate(cues):
        if isinstance(cue, tuple):
            t, kind = float(cue[0]), cue[1]
            length = float(cue[2]) if len(cue) > 2 else 0.0
        else:
            t, kind, length = float(cue), "whoosh", 0.0
        lead = 0.0
        if kind == "tick":
            sample = tick()
        elif kind == "impact":
            sample = impact(seed=i)
        elif kind == "riser":
            sample = riser(max(length, 0.6), seed=i)
        elif kind == "pop":
            sample = pop()
        elif kind == "keys":
            sample = keys(max(length, 0.15), seed=i)
        elif kind == "shutter":
            sample = shutter()
        else:
            sample, lead = whoosh(seed=i), 0.2
        a = max(0, int((t - lead) * SR))
        b = min(n, a + len(sample))
        out[a:b] += sample[: b - a]
    peak = float(np.max(np.abs(out))) if n else 0.0
    if peak > 1:
        out /= peak
    sf.write(path, out, SR, subtype="PCM_16")
