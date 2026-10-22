"""Original, procedurally generated music bed (a lo-fi groove) and sound effects.

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


# --------------------------------------------------------------------------- original groove

_CHORDS = [  # vi - IV - I - V in C major / A minor, voiced around middle C
    (110.0, [220.0, 261.63, 329.63, 392.0]),  # Am7
    (87.31, [174.61, 220.0, 261.63, 329.63]),  # Fmaj7
    (65.41, [196.0, 261.63, 329.63, 493.88]),  # Cmaj7 (no low C in the voicing)
    (98.0, [196.0, 246.94, 293.66, 392.0]),  # G
]


def _smooth(x: np.ndarray, k: int) -> np.ndarray:
    return np.convolve(x, np.ones(k, dtype=np.float32) / k, mode="same").astype(np.float32)


def _kick(rng: np.random.Generator) -> np.ndarray:
    n = int(0.38 * SR)
    t = np.arange(n, dtype=np.float32) / SR
    freq = 46 + 110 * np.exp(-t * 28)
    y = np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t * 9)
    click = rng.standard_normal(n).astype(np.float32) * np.exp(-t * 400) * 0.15
    return (y + click).astype(np.float32)


def _snare(rng: np.random.Generator) -> np.ndarray:
    n = int(0.25 * SR)
    t = np.arange(n, dtype=np.float32) / SR
    noise = rng.standard_normal(n).astype(np.float32)
    band = (_smooth(noise, 6) - _smooth(noise, 40)) * np.exp(-t * 16)
    tone = np.sin(2 * np.pi * 185 * t) * np.exp(-t * 30) * 0.35
    return (band * 1.6 + tone).astype(np.float32)


def _hat(rng: np.random.Generator, open_: bool = False) -> np.ndarray:
    n = int((0.22 if open_ else 0.06) * SR)
    t = np.arange(n, dtype=np.float32) / SR
    noise = rng.standard_normal(n).astype(np.float32)
    hp = noise - _smooth(noise, 4)
    return (hp * np.exp(-t * (14 if open_ else 70))).astype(np.float32)


def _bass(freq: float, length: float) -> np.ndarray:
    n = int(length * SR)
    t = np.arange(n, dtype=np.float32) / SR
    env = np.minimum(1, t / 0.006) * (0.55 + 0.45 * np.exp(-t * 6)) * np.minimum(1, (length - t) / 0.05)
    y = np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(4 * np.pi * freq * t)
    return (y * env).astype(np.float32)


def _chord(freqs: list[float], length: float, bright: float) -> np.ndarray:
    """Soft electric-piano-ish stab: detuned sines plus a little 3rd/5th harmonic (triangle-like)."""
    n = int(length * SR)
    t = np.arange(n, dtype=np.float32) / SR
    env = np.minimum(1, t / 0.012) * np.exp(-t * 1.6) * np.minimum(1, (length - t) / 0.08)
    y = np.zeros(n, dtype=np.float32)
    for f in freqs:
        for det in (-0.9, 0.9):
            ff = f + det
            y += np.sin(2 * np.pi * ff * t) + bright * (
                np.sin(6 * np.pi * ff * t) / 9 + np.sin(10 * np.pi * ff * t) / 25
            )
    wobble = 0.85 + 0.15 * np.sin(2 * np.pi * 0.7 * t)
    return (y * env * wobble / len(freqs)).astype(np.float32)


def _place(out: np.ndarray, sample: np.ndarray, t: float, gain: float) -> None:
    a = int(t * SR)
    if a >= len(out) or a + len(sample) <= 0:
        return
    s0 = max(0, -a)
    a = max(0, a)
    b = min(len(out), a + len(sample) - s0)
    out[a:b] += sample[s0 : s0 + (b - a)] * gain


def compose_bed(
    duration: float,
    *,
    bpm: float = 92,
    seed: int = 0,
    full_from: float | None = None,
    anchor: float | None = None,
) -> np.ndarray:
    """An original lo-fi tech groove: swung hats, kick/snare, bass and a vi-IV-I-V chord loop.

    `full_from`: before this time only hats + soft chords play (the hook stays light).
    `anchor`: a time that must fall on a bar's downbeat (e.g. where the music returns after the
    twist), so the groove comes back "on the one". Returns peak-normalised audio.
    """
    rng = np.random.default_rng(seed)
    n = int(duration * SR)
    out = np.zeros(n, dtype=np.float32)
    beat = 60.0 / bpm
    bar = 4 * beat
    phase = (anchor % bar) if anchor is not None else 0.0
    start = phase - bar * np.ceil(phase / bar) if phase else 0.0
    full_from = 0.0 if full_from is None else full_from
    outro = duration - 2 * bar
    kick, snare = _kick(rng), _snare(rng)
    hats = [_hat(rng) for _ in range(4)]
    open_hat = _hat(rng, open_=True)
    swing = 0.16 * beat  # off-beat 8ths land late (lo-fi swing)
    k = 0
    t_bar = start
    while t_bar < duration:
        root, voicing = _CHORDS[k % len(_CHORDS)]
        full = t_bar >= full_from - 1e-6 and t_bar < outro
        # chords: long stab on 1, short push on the "and" of 2
        tone = 0.6 if full else 0.3
        _place(out, _chord(voicing, 1.7 * beat, tone), t_bar, 0.34 if full else 0.42)
        _place(out, _chord(voicing, 0.6 * beat, tone), t_bar + 1.5 * beat + swing, 0.2 if full else 0.26)
        # hats on every 8th, swung, with velocity variation
        for e in range(8):
            t = t_bar + e * beat / 2 + (swing if e % 2 else 0)
            vel = (0.5 if e % 2 == 0 else 0.3) * rng.uniform(0.8, 1.1)
            if e == 7 and k % 2 == 1 and full:
                _place(out, open_hat, t, 0.22)
            else:
                _place(out, hats[(k + e) % 4], t, vel * (1.0 if full else 0.85))
        if not full and t_bar < outro:  # hook: a lighter build - downbeat kick + soft bass, no snare
            _place(out, kick, t_bar, 0.6)
            _place(out, _bass(root, 1.4 * beat), t_bar, 0.5)
        if full:
            _place(out, kick, t_bar, 0.95)
            _place(out, kick, t_bar + 2 * beat + (beat / 2 if k % 2 else 0), 0.8)
            _place(out, snare, t_bar + beat, 0.55)
            _place(out, snare, t_bar + 3 * beat, 0.6)
            _place(out, _bass(root, 1.4 * beat), t_bar, 0.7)
            _place(out, _bass(root, 0.45 * beat), t_bar + 1.5 * beat + swing, 0.5)
            _place(out, _bass(root * 1.5, 0.9 * beat), t_bar + 2.5 * beat + swing, 0.55)
        t_bar += bar
        k += 1
    # vinyl/air texture
    air = _smooth(rng.standard_normal(n).astype(np.float32), 24) * 0.012
    crackle = (rng.random(n) > 0.99985).astype(np.float32) * rng.uniform(-0.25, 0.25, n).astype(np.float32)
    out += air + _smooth(crackle, 3)
    return out / (float(np.max(np.abs(out))) + 1e-9) * 0.9


REFERENCE_LUFS = -16.0  # the bed is normalised to this before music_volume_db is applied


def write_bed(
    path: Path,
    duration: float,
    drops: list[tuple[float, float]] | None = None,
    fade_out: float = 1.5,
    *,
    style: str = "groove",
    seed: int = 0,
    full_from: float | None = None,
    anchor: float | None = None,
) -> None:
    """Music bed with automation: silent during `drops` (start, end in seconds, 80 ms ramps), a
    fade-out at the end, normalised to REFERENCE_LUFS so `music_volume_db` means the same thing
    for every video."""
    if style == "ambient":
        bed = ambient_bed(duration, seed=seed or 7)
    else:
        bed = compose_bed(duration, seed=seed, full_from=full_from, anchor=anchor)
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
    audio = (bed * env).astype(np.float32)
    sf.write(path, audio, SR, subtype="FLOAT")
    from reelforge.voice.voiceover import measure_lufs

    # 1) gain towards the reference and soft-limit transients (tanh) instead of clipping;
    # 2) measure again and correct with pure gain, so the result lands on the reference.
    lufs = measure_lufs(path)
    if lufs is not None and np.isfinite(lufs):
        audio = audio * 10 ** ((REFERENCE_LUFS - lufs) / 20)
        audio = (np.tanh(audio * 1.2) / np.tanh(1.2)).astype(np.float32)
        sf.write(path, audio, SR, subtype="FLOAT")
        lufs = measure_lufs(path)
        if lufs is not None and np.isfinite(lufs):
            audio = audio * 10 ** ((REFERENCE_LUFS - lufs) / 20)
    sf.write(path, np.clip(audio, -0.98, 0.98), SR, subtype="PCM_16")


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
