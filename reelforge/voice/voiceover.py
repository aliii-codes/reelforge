"""Human voice-over: record or import, validate, and gently process.

Processing is deliberately conservative — a voice-over should still sound like the person who
recorded it:

1. channel handling: if one channel of a "stereo" mic recording is (near) silent, use the live
   channel instead of averaging noise into it; otherwise downmix to mono.
2. 70 Hz high-pass (removes rumble/handling noise only).
3. optional light FFT denoise (off by default).
4. edge trim: leading/trailing silence only, keeping a short natural lead-in and tail.
   Internal pauses are untouched unless `max_pause` is set, in which case only pauses longer
   than that are shortened (with short crossfades) — never removed.
5. two-pass EBU R128 loudness normalisation to -16 LUFS (linear mode, so dynamics are kept;
   the final mix is normalised again to about -14 LUFS with music/SFX).

All timing (captions, avatar, scenes, SFX) is later derived from the processed file.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

from reelforge.schemas import utcnow
from reelforge.voice.quality import frame_rms

SR = 48000
LEAD_IN_S = 0.15
TAIL_S = 0.35
TARGET_LUFS = -16.0


class VoiceoverError(ValueError):
    """A problem with the voice-over file, phrased so the user knows what to do."""


@dataclass
class VoiceoverCheck:
    path: str
    duration: float = 0.0
    sample_rate: int = 0
    channels: int = 0
    codec: str = ""
    peak_dbfs: float = -120.0
    clipping_ratio: float = 0.0
    snr_estimate_db: float = 0.0
    speech_seconds: float = 0.0
    leading_silence: float = 0.0
    trailing_silence: float = 0.0
    longest_pause: float = 0.0
    pauses_over_1s: int = 0
    dead_channel: int | None = None  # index of a near-silent channel in a 2-channel file
    integrated_lufs: float | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return asdict(self) | {"ok": self.ok}


@dataclass
class ProcessingOptions:
    trim: bool = True
    max_pause: float | None = None  # seconds; None keeps every pause as recorded
    denoise: bool = False
    normalize: bool = True

    def key(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


# --------------------------------------------------------------------------- analysis


def _probe(path: Path) -> dict:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise VoiceoverError(
            f"{path.name} could not be read as audio ({proc.stderr.strip()[:200] or 'unknown format'})."
        )
    return json.loads(proc.stdout)


def _decode(path: Path, channels: int | None = None) -> np.ndarray:
    """Decode to float32 at 48 kHz, shape (samples, channels)."""
    ch = ["-ac", str(channels)] if channels else []
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), *ch, "-ar", str(SR), "-f", "f32le", "-"],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise VoiceoverError(f"FFmpeg could not decode {path.name}: {proc.stderr.decode(errors='replace')[:200]}")
    data = np.frombuffer(proc.stdout, dtype=np.float32)
    n = channels or 1
    return data[: len(data) - len(data) % n].reshape(-1, n)


def _db(x: float) -> float:
    return float(20 * np.log10(max(x, 1e-9)))


def _voiced_mask(mono: np.ndarray, hop_s: float = 0.02) -> tuple[np.ndarray, float, float]:
    env = frame_rms(mono, SR, hop_s)
    env_db = 20 * np.log10(np.maximum(env, 1e-9))
    if not len(env_db):
        return np.zeros(0, dtype=bool), -120.0, -120.0
    floor = float(np.percentile(env_db, 10))
    speech = float(np.percentile(env_db, 95))
    thresh = max(floor + 8, speech - 32)
    return env_db > thresh, floor, speech


def measure_lufs(path: Path) -> float | None:
    proc = subprocess.run(
        ["ffmpeg", "-v", "info", "-nostdin", "-i", str(path), "-af", "ebur128=framelog=quiet", "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", proc.stderr)
    return float(m[-1]) if m else None


def check_voiceover(path: Path, *, min_seconds: float = 10.0, max_seconds: float = 120.0) -> VoiceoverCheck:
    """Validate a voice-over file and describe it. Errors block use; warnings don't."""
    chk = VoiceoverCheck(path=str(path))
    if not path.exists():
        chk.errors.append(f"File not found: {path}")
        return chk
    if path.stat().st_size == 0:
        chk.errors.append(f"{path.name} is empty (0 bytes) - the recording probably failed.")
        return chk
    try:
        info = _probe(path)
    except VoiceoverError as e:
        chk.errors.append(str(e))
        return chk
    audio_streams = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    if not audio_streams:
        chk.errors.append(f"{path.name} has no audio stream.")
        return chk
    st = audio_streams[0]
    chk.codec = st.get("codec_name", "")
    chk.sample_rate = int(st.get("sample_rate", 0) or 0)
    chk.channels = int(st.get("channels", 0) or 0)
    if chk.sample_rate and chk.sample_rate < 16000:
        chk.errors.append(f"Sample rate is {chk.sample_rate} Hz; record at 44.1 or 48 kHz (16 kHz minimum).")

    multi = _decode(path, channels=2 if chk.channels >= 2 else 1)
    if multi.shape[1] == 2:
        rms = [float(np.sqrt(np.mean(multi[:, c] ** 2))) for c in (0, 1)]
        if min(rms) < 1e-6 or _db(max(rms)) - _db(min(rms)) > 20:
            chk.dead_channel = int(np.argmin(rms))
            chk.warnings.append(
                f"Channel {chk.dead_channel + 1} of 2 is (almost) silent - a mono mic on a stereo input. "
                "The live channel will be used."
            )
            mono = multi[:, 1 - chk.dead_channel]
        else:
            mono = multi.mean(axis=1)
    else:
        mono = multi[:, 0]

    chk.duration = round(len(mono) / SR, 2)
    peak = float(np.max(np.abs(mono))) if len(mono) else 0.0
    chk.peak_dbfs = round(_db(peak), 1)
    chk.clipping_ratio = round(float(np.mean(np.abs(mono) >= 0.999)) if len(mono) else 0.0, 5)
    voiced, floor, speech = _voiced_mask(mono)
    chk.snr_estimate_db = round(speech - floor, 1)
    hop = 0.02
    chk.speech_seconds = round(float(np.sum(voiced)) * hop, 1)
    idx = np.where(voiced)[0]
    if len(idx):
        chk.leading_silence = round(idx[0] * hop, 2)
        chk.trailing_silence = round((len(voiced) - 1 - idx[-1]) * hop, 2)
        inner = voiced[idx[0] : idx[-1] + 1]
        runs, run = [], 0
        for v in inner:
            if not v:
                run += 1
            elif run:
                runs.append(run * hop)
                run = 0
        chk.longest_pause = round(max(runs, default=0.0), 2)
        chk.pauses_over_1s = sum(r > 1.0 for r in runs)
    chk.integrated_lufs = measure_lufs(path)

    if chk.duration < min_seconds:
        chk.errors.append(f"Only {chk.duration:.1f}s long; a reel voice-over needs at least {min_seconds:.0f}s.")
    if chk.duration > max_seconds:
        chk.errors.append(f"{chk.duration:.0f}s long; keep the voice-over under {max_seconds:.0f}s (target 45-60s).")
    if peak < 10 ** (-40 / 20):
        chk.errors.append(
            f"Almost silent (peak {chk.peak_dbfs} dBFS). Check the mic is unmuted and selected "
            "(`pactl list short sources`) and record again."
        )
    elif chk.peak_dbfs < -24:
        chk.warnings.append(f"Quiet recording (peak {chk.peak_dbfs} dBFS); it will be normalised but noise rises too.")
    if chk.clipping_ratio > 0.005:
        chk.errors.append(
            f"Heavy clipping on {chk.clipping_ratio:.2%} of samples - distortion can't be repaired. "
            "Lower the mic gain or move back and record again."
        )
    elif chk.clipping_ratio > 0.0005:
        chk.warnings.append(f"Some clipping ({chk.clipping_ratio:.2%} of samples); listen for distorted syllables.")
    if chk.snr_estimate_db < 15 and peak >= 10 ** (-40 / 20):
        chk.errors.append(
            f"Very noisy: speech is only ~{chk.snr_estimate_db:.0f} dB above the background. "
            "Record somewhere quieter (fans/AC off) or closer to the mic."
        )
    elif chk.snr_estimate_db < 25:
        chk.warnings.append(f"Background noise is audible (~{chk.snr_estimate_db:.0f} dB SNR); consider --denoise.")
    if chk.duration and chk.speech_seconds < 0.4 * chk.duration and not chk.errors:
        chk.warnings.append(f"Only {chk.speech_seconds:.0f}s of speech in {chk.duration:.0f}s - lots of silence.")
    if chk.longest_pause > 2.0:
        chk.warnings.append(
            f"Longest pause is {chk.longest_pause:.1f}s; consider --max-pause 0.8 to tighten (natural pauses are kept)."
        )
    return chk


# --------------------------------------------------------------------------- processing


def _shorten_pauses(mono: np.ndarray, max_pause: float, hop_s: float = 0.02) -> tuple[np.ndarray, int]:
    """Shorten internal silences longer than `max_pause` to exactly `max_pause` by removing the
    middle of the silence; joins are crossfaded over 10 ms so there are no clicks."""
    voiced, _, _ = _voiced_mask(mono, hop_s)
    idx = np.where(voiced)[0]
    if not len(idx):
        return mono, 0
    hop = int(SR * hop_s)
    half = int(max_pause * SR) // 2
    cuts: list[tuple[int, int]] = []
    i, last = int(idx[0]), int(idx[-1])
    while i <= last:
        if voiced[i]:
            i += 1
            continue
        j = i
        while j <= last and not voiced[j]:
            j += 1
        start, end = i * hop, j * hop
        if end - start > 2 * half:
            cuts.append((start + half, end - half))
        i = j
    if not cuts:
        return mono, 0
    pieces, prev = [], 0
    for a, b in cuts:
        pieces.append(mono[prev:a])
        prev = b
    pieces.append(mono[prev:])
    fade = int(0.01 * SR)
    out = pieces[0]
    for p in pieces[1:]:
        f = min(fade, len(out), len(p))
        if f:
            r = np.linspace(0, 1, f, dtype=np.float32)
            out = np.concatenate([out[:-f], out[-f:] * (1 - r) + p[:f] * r, p[f:]])
        else:
            out = np.concatenate([out, p])
    return out.astype(np.float32), len(cuts)


def _loudnorm_two_pass(src: Path, dst: Path, target: float = TARGET_LUFS) -> dict:
    first = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "info",
            "-nostdin",
            "-i",
            str(src),
            "-af",
            f"loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", first.stderr, re.S)
    if not m:
        raise VoiceoverError("Loudness measurement failed (FFmpeg loudnorm pass 1).")
    meas = json.loads(m.group(0))
    af = (
        f"loudnorm=I={target}:TP=-1.5:LRA=11:measured_I={meas['input_i']}:measured_TP={meas['input_tp']}:"
        f"measured_LRA={meas['input_lra']}:measured_thresh={meas['input_thresh']}:offset={meas['target_offset']}:"
        "linear=true"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(src),
            "-af",
            af,
            "-ar",
            str(SR),
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(dst),
        ],
        check=True,
    )
    return {"measured_input_lufs": float(meas["input_i"]), "target_lufs": target}


def process_voiceover(src: Path, dst: Path, opts: ProcessingOptions, check: VoiceoverCheck | None = None) -> dict:
    """Validate then process `src` into a mono 48 kHz WAV at `dst`. Returns a processing report."""
    chk = check or check_voiceover(src)
    if not chk.ok:
        raise VoiceoverError("Voice-over rejected:\n  - " + "\n  - ".join(chk.errors))
    report: dict = {"source": str(src), "processed_at": utcnow(), "options": asdict(opts), "steps": []}

    if chk.dead_channel is not None:
        pan = f"pan=mono|c0=c{1 - chk.dead_channel}"
        report["steps"].append(f"used channel {2 - chk.dead_channel} (other channel silent)")
    else:
        pan = "aformat=channel_layouts=mono"
    filters = [pan, "highpass=f=70"]
    report["steps"].append("high-pass 70 Hz")
    if opts.denoise:
        filters.append("afftdn=nr=10:nf=-50")
        report["steps"].append("light FFT denoise (afftdn nr=10)")

    with tempfile.TemporaryDirectory() as td:
        stage1 = Path(td) / "stage1.wav"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-y",
                "-i",
                str(src),
                "-af",
                ",".join(filters),
                "-ar",
                str(SR),
                "-c:a",
                "pcm_f32le",
                str(stage1),
            ],
            check=True,
        )
        mono, _ = sf.read(stage1, dtype="float32")
        mono = np.asarray(mono, dtype=np.float32).reshape(-1)
        before = len(mono) / SR

        if opts.trim:
            voiced, _, _ = _voiced_mask(mono)
            idx = np.where(voiced)[0]
            if len(idx):
                a = max(0, int((idx[0] * 0.02 - LEAD_IN_S) * SR))
                b = min(len(mono), int(((idx[-1] + 1) * 0.02 + TAIL_S) * SR))
                mono = mono[a:b]
                report["steps"].append(
                    f"trimmed edges: {a / SR:.2f}s at start, {before - b / SR:.2f}s at end (internal pauses kept)"
                )
        if opts.max_pause:
            mono, n = _shorten_pauses(mono, opts.max_pause)
            report["steps"].append(f"shortened {n} pause(s) longer than {opts.max_pause:.2f}s")

        stage2 = Path(td) / "stage2.wav"
        sf.write(stage2, mono, SR, subtype="FLOAT")
        if opts.normalize:
            report["loudness"] = _loudnorm_two_pass(stage2, dst)
            report["steps"].append(f"two-pass loudnorm to {TARGET_LUFS} LUFS (linear, dynamics kept)")
        else:
            sf.write(dst, mono, SR, subtype="PCM_16")
    report["duration_before"] = round(before, 2)
    report["duration_after"] = round(sf.info(dst).duration, 2)
    report["lufs_after"] = measure_lufs(dst)
    report["check"] = chk.as_dict()
    return report


# --------------------------------------------------------------------------- recording


def build_record_command(out: Path, *, device: str = "default", max_seconds: int = 120) -> list[str]:
    return [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-f",
        "pulse",
        "-i",
        device,
        "-t",
        str(max_seconds),
        "-ac",
        "2",
        "-ar",
        str(SR),
        "-c:a",
        "pcm_s16le",
        str(out),
    ]


def record(out: Path, *, device: str = "default", max_seconds: int = 120, wait_for_stop=input) -> Path:
    """Record from PulseAudio/PipeWire until Enter is pressed (or max_seconds)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        build_record_command(out, device=device, max_seconds=max_seconds), stdin=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        wait_for_stop()
    finally:
        if proc.poll() is None and proc.stdin:
            try:
                proc.stdin.write(b"q")  # graceful stop: FFmpeg finalises the WAV header
                proc.stdin.flush()
            except BrokenPipeError:
                pass
        proc.wait(timeout=15)
    if proc.returncode not in (0, 255) or not out.exists():
        err = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        raise VoiceoverError(f"Recording failed: {err.strip()[:300] or 'no output file'}")
    return out


def narration_text(sections_text: list[str]) -> str:
    """Script formatted for reading aloud: one section per paragraph."""
    return "\n\n".join(sections_text)
