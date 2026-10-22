"""Audio quality checks and transcript-vs-script comparison for narration takes.

These checks catch missing/extra words, clipping, long silences and noisy recordings. They do
not prove pronunciation or naturalness is good; a human still listens to the chosen take.
"""

from __future__ import annotations

import difflib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from reelforge.schemas import AudioQuality

# --------------------------------------------------------------------------- audio I/O


def load_audio(path: Path, sample_rate: int = 16000) -> np.ndarray:
    """Decode any FFmpeg-readable file to mono float32 at `sample_rate`."""
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "-"],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg could not decode {path}: {proc.stderr.decode(errors='replace')[:300]}")
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


def probe_audio(path: Path) -> tuple[int, int]:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=sample_rate,channels",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if not out:
        raise RuntimeError(f"{path} has no audio stream")
    sr, ch = out.split(",")[:2]
    return int(sr), int(ch)


def _db(x: float) -> float:
    return float(20 * np.log10(max(x, 1e-9)))


def frame_rms(audio: np.ndarray, sr: int, hop_s: float = 0.02) -> np.ndarray:
    hop = max(1, int(sr * hop_s))
    n = len(audio) // hop
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    frames = audio[: n * hop].reshape(n, hop)
    return np.sqrt(np.mean(frames**2, axis=1))


def analyze_audio(path: Path, *, max_pause_s: float = 1.2, min_seconds: float = 0.0) -> AudioQuality:
    sr_native, channels = probe_audio(path)
    sr = 16000
    audio = load_audio(path, sr)
    duration = len(audio) / sr
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    rms = float(np.sqrt(np.mean(audio**2))) if len(audio) else 0.0
    clipping = float(np.mean(np.abs(audio) >= 0.999)) if len(audio) else 0.0

    hop_s = 0.02
    env = frame_rms(audio, sr, hop_s)
    env_db = 20 * np.log10(np.maximum(env, 1e-9))
    noise_floor = float(np.percentile(env_db, 10)) if len(env_db) else -120.0
    speech_level = float(np.percentile(env_db, 90)) if len(env_db) else -120.0
    silent = env_db < max(noise_floor + 6, speech_level - 35)
    silence_ratio = float(np.mean(silent)) if len(silent) else 1.0

    # Longest internal pause (ignore leading/trailing silence).
    longest = 0.0
    voiced = np.where(~silent)[0]
    if len(voiced):
        inner = silent[voiced[0] : voiced[-1] + 1]
        run = 0
        for s in inner:
            run = run + 1 if s else 0
            longest = max(longest, run * hop_s)

    issues = []
    if duration < min_seconds:
        issues.append(f"only {duration:.1f}s long (need at least {min_seconds:.0f}s)")
    if clipping > 0.001:
        issues.append(f"clipping on {clipping:.2%} of samples")
    if _db(peak) < -20:
        issues.append(f"very quiet (peak {_db(peak):.1f} dBFS)")
    snr = speech_level - noise_floor
    if snr < 20:
        issues.append(f"noisy: speech only {snr:.0f} dB above the noise floor (aim for 30+)")
    if longest > max_pause_s:
        issues.append(f"long pause of {longest:.1f}s")
    if silence_ratio > 0.5:
        issues.append(f"{silence_ratio:.0%} silence")
    return AudioQuality(
        duration=round(duration, 3),
        sample_rate=sr_native,
        channels=channels,
        peak_dbfs=round(_db(peak), 2),
        rms_dbfs=round(_db(rms), 2),
        clipping_ratio=round(clipping, 5),
        silence_ratio=round(silence_ratio, 3),
        longest_pause=round(longest, 2),
        noise_floor_dbfs=round(noise_floor, 1),
        snr_estimate_db=round(snr, 1),
        issues=issues,
    )


# --------------------------------------------------------------------------- text comparison

_ONES = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
_TENS = ["_", "_", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def number_to_words(n: int) -> str:
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + ("" if n % 10 == 0 else " " + _ONES[n % 10])
    if n < 1000:
        return _ONES[n // 100] + " hundred" + ("" if n % 100 == 0 else " " + number_to_words(n % 100))
    for div, name in ((10**9, "billion"), (10**6, "million"), (1000, "thousand")):
        if n >= div:
            rest = n % div
            return number_to_words(n // div) + " " + name + ("" if rest == 0 else " " + number_to_words(rest))
    return str(n)


def _expand_token(tok: str) -> list[str]:
    m = re.fullmatch(r"(\d+)(?:\.(\d+))?(%?)", tok)
    if m:
        words = number_to_words(int(m.group(1))).split()
        if m.group(2):
            words += ["point"] + [_ONES[int(d)] for d in m.group(2)]
        if m.group(3):
            words.append("percent")
        return words
    return [tok]


def normalize_words(text: str) -> list[str]:
    """Lowercase, drop punctuation, spell digits, and merge spelled-out letters ("g p t" -> "gpt")."""
    text = text.lower().replace("’", "'").replace("-", " ").replace("—", " ")
    text = re.sub(r"(\d),(\d{3})", r"\1\2", text)
    raw = re.findall(r"[a-z0-9]+(?:\.[0-9]+)?%?|[a-z]+'[a-z]+", text)
    toks: list[str] = []
    for r in raw:
        toks.extend(_expand_token(r.replace("'", "")))
    return _fold_equivalents(_merge_letter_runs(toks))


_NUMBER_WORDS = set(_ONES) | set(_TENS[2:]) | {"hundred", "thousand", "million", "billion"}
# Spellings Whisper picks interchangeably; folding them avoids blaming the voice for them.
_HOMOPHONES = {"too": "to", "two": "to"}


def _fold_equivalents(toks: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(toks):
        # "three and a half" == "3.5" (Whisper writes the digits)
        if toks[i : i + 3] == ["and", "a", "half"] and out and out[-1] in _NUMBER_WORDS:
            out += ["point", "five"]
            i += 3
            continue
        out.append(_HOMOPHONES.get(toks[i], toks[i]))
        i += 1
    return out


def _merge_letter_runs(toks: list[str]) -> list[str]:
    out: list[str] = []
    run: list[str] = []
    for t in toks + [""]:
        if len(t) == 1 and t.isalpha() and t not in ("a", "i"):
            run.append(t)
            continue
        if run:
            out.append("".join(run))
            run = []
        if t:
            out.append(t)
    return out


@dataclass
class TextDiff:
    wer: float
    missing: list[str]
    extra: list[str]
    substitutions: list[tuple[str, str]]


def compare_transcript(expected: str, heard: str) -> TextDiff:
    exp, got = normalize_words(expected), normalize_words(heard)
    sm = difflib.SequenceMatcher(a=exp, b=got, autojunk=False)
    missing: list[str] = []
    extra: list[str] = []
    subs: list[tuple[str, str]] = []
    errors = 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        a, b = exp[i1:i2], got[j1:j2]
        if op == "delete":
            missing += a
            errors += len(a)
        elif op == "insert":
            extra += b
            errors += len(b)
        else:
            for k in range(max(len(a), len(b))):
                if k < len(a) and k < len(b):
                    subs.append((a[k], b[k]))
                elif k < len(a):
                    missing.append(a[k])
                else:
                    extra.append(b[k])
            errors += max(len(a), len(b))
    wer = errors / max(len(exp), 1)
    return TextDiff(wer=round(wer, 4), missing=missing, extra=extra, substitutions=subs)


def score_take(diff: TextDiff, audio: AudioQuality, target_min: float, target_max: float) -> tuple[float, list[str]]:
    """0-100. Exact reading dominates: every missing or extra word costs 4 points on top of WER
    (a repeated or skipped word is a real defect); substitutions cost less because many are
    transcription noise. Audio issues and duration fit adjust the rest."""
    issues = list(audio.issues)
    score = 100.0 * (1.0 - min(diff.wer, 1.0))
    score -= 4 * (len(diff.missing) + len(diff.extra)) + 1.5 * len(diff.substitutions)
    if diff.missing:
        issues.append(f"{len(diff.missing)} script word(s) not heard: {' '.join(diff.missing[:8])}")
    if diff.extra:
        issues.append(f"{len(diff.extra)} extra word(s) heard: {' '.join(diff.extra[:8])}")
    if diff.substitutions:
        issues.append(
            "possible mispronunciations/mis-hearings: " + ", ".join(f"{a}->{b}" for a, b in diff.substitutions[:6])
        )
    score -= 3 * len([i for i in audio.issues if "clipping" in i or "long pause" in i])
    if audio.duration > target_max:
        score -= min(15, (audio.duration - target_max) * 2)
        issues.append(f"{audio.duration:.1f}s is over the {target_max:.0f}s target")
    elif audio.duration < target_min:
        score -= min(10, (target_min - audio.duration))
        issues.append(f"{audio.duration:.1f}s is under the {target_min:.0f}s target")
    return round(max(score, 0.0), 2), issues
