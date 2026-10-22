"""Local voice enrolment for cloning the user's OWN voice.

Recordings are copied into `voice_data/<profile>/` (git-ignored), checked, and combined into a
short reference clip. Nothing is uploaded anywhere. Pocket TTS uses the reference clip as an
audio prompt at synthesis time (no training/fine-tuning); a cached voice state is stored
alongside it to speed up later runs.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from reelforge.schemas import utcnow
from reelforge.voice.quality import analyze_audio, load_audio

CONSENT_STATEMENT = (
    "I confirm these recordings are of my own voice, recorded by me, and I authorize ReelForge to "
    "use them locally to synthesize narration in my voice."
)

RECORDING_GUIDE = """How to record a good voice reference
------------------------------------
- Quiet room, soft furnishings, no fan/AC hum, phone on silent.
- Phone voice-memo app or a USB/headset mic, ~15-20 cm from your mouth, slightly off-axis.
- Speak the way you want the reels to sound: energetic, clear, natural pace.
- Record 2-3 clips of 10-20 seconds each (minimum 5 s each, 10+ s total). Read any
  paragraph of tech text; avoid long pauses, laughter, background music and other voices.
- Keep peaks below clipping (no distorted loud syllables).
- Export as WAV, FLAC, M4A or MP3 and pass the files to `voice-enroll`.
Linux recording example (PulseAudio/PipeWire):
    ffmpeg -f pulse -i default -ac 1 -ar 48000 -t 20 my_voice_1.wav
"""

MIN_CLIP_S = 5.0
MIN_TOTAL_S = 8.0
REFERENCE_MAX_S = 20.0


class EnrollmentError(RuntimeError):
    pass


def profile_dir(voice_dir: Path, profile: str) -> Path:
    if not profile.replace("-", "").replace("_", "").isalnum():
        raise EnrollmentError("profile name may only contain letters, digits, '-' and '_'")
    d = (voice_dir / profile).resolve()
    if voice_dir.resolve() not in d.parents:
        raise EnrollmentError("profile path escapes the voice directory")
    return d


def load_profile(voice_dir: Path, profile: str) -> dict:
    p = profile_dir(voice_dir, profile) / "profile.json"
    if not p.exists():
        raise EnrollmentError(f"no voice profile {profile!r}; run `voice-enroll` first")
    return json.loads(p.read_text())


def _save_profile(d: Path, data: dict) -> None:
    (d / "profile.json").write_text(json.dumps(data, indent=2))


def _trim_and_normalize(src: Path, dst: Path) -> None:
    # 24 kHz mono (Pocket TTS's native rate), gentle high-pass to remove rumble, edge silence trimmed.
    af = (
        "highpass=f=60,"
        "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.1,"
        "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.2,areverse"
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
            "-ac",
            "1",
            "-ar",
            "24000",
            "-c:a",
            "pcm_s16le",
            str(dst),
        ],
        check=True,
    )
    audio, sr = sf.read(dst, dtype="float32")
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    if peak > 0:
        sf.write(dst, audio * (0.89 / peak), sr, subtype="PCM_16")


def enroll(voice_dir: Path, profile: str, files: list[Path], *, consent: bool, replace: bool = False) -> dict:
    if not consent:
        raise EnrollmentError("consent is required: only your own voice may be enrolled")
    if not files:
        raise EnrollmentError("provide at least one recording")
    for f in files:
        if not f.is_file():
            raise EnrollmentError(f"file not found: {f}")
    d = profile_dir(voice_dir, profile)
    if d.exists():
        if not replace:
            raise EnrollmentError(f"profile {profile!r} already exists; use --replace or `voice-delete` first")
        shutil.rmtree(d)
    (d / "raw").mkdir(parents=True)
    (d / "clips").mkdir()

    clips: list[dict[str, Any]] = []
    for i, f in enumerate(files, 1):
        raw = d / "raw" / f"clip{i}{f.suffix.lower()}"
        shutil.copyfile(f, raw)
        norm = d / "clips" / f"clip{i}.wav"
        _trim_and_normalize(raw, norm)
        q_raw = analyze_audio(raw, min_seconds=MIN_CLIP_S)  # clipping/noise judged on the original
        q_norm = analyze_audio(norm, min_seconds=MIN_CLIP_S)
        clips.append(
            {
                "original_name": f.name,
                "raw": str(raw.relative_to(d)),
                "clip": str(norm.relative_to(d)),
                "quality": q_raw.model_dump(),
                "trimmed_seconds": q_norm.duration,
            }
        )

    # Reference: cleanest clips first, joined up to REFERENCE_MAX_S.
    ordered = sorted(clips, key=lambda c: (-c["quality"]["snr_estimate_db"], c["quality"]["clipping_ratio"]))
    pieces: list[np.ndarray] = []
    total = 0.0
    gap = np.zeros(int(24000 * 0.3), dtype=np.float32)
    for c in ordered:
        if total >= REFERENCE_MAX_S:
            break
        audio = load_audio(d / c["clip"], 24000)
        room = REFERENCE_MAX_S - total
        audio = audio[: int(room * 24000)]
        pieces += [audio, gap]
        total += len(audio) / 24000
    ref = np.concatenate(pieces[:-1]) if pieces else np.zeros(0, dtype=np.float32)
    sf.write(d / "reference.wav", ref, 24000, subtype="PCM_16")

    total_trimmed = sum(c["trimmed_seconds"] for c in clips)
    problems = [f"{c['original_name']}: {issue}" for c in clips for issue in c["quality"]["issues"]]
    if total_trimmed < MIN_TOTAL_S:
        problems.append(f"only {total_trimmed:.1f}s of speech in total; record at least {MIN_TOTAL_S:.0f}s")
    data = {
        "profile": profile,
        "created_at": utcnow(),
        "consent": {"statement": CONSENT_STATEMENT, "confirmed_at": utcnow()},
        "status": "pending_review",
        "clips": clips,
        "reference": "reference.wav",
        "reference_seconds": round(len(ref) / 24000, 2),
        "total_speech_seconds": round(total_trimmed, 2),
        "problems": problems,
        "approved_at": None,
        "voice_state": None,
        "engine": "pocket-tts (reference-audio prompt, no training)",
    }
    _save_profile(d, data)
    return data


def approve(voice_dir: Path, profile: str) -> dict:
    d = profile_dir(voice_dir, profile)
    data = load_profile(voice_dir, profile)
    if data["reference_seconds"] < 3:
        raise EnrollmentError("reference audio is shorter than 3 s; re-record before approving")
    data["status"] = "approved"
    data["approved_at"] = utcnow()
    _save_profile(d, data)
    return data


def delete(voice_dir: Path, profile: str) -> bool:
    d = profile_dir(voice_dir, profile)
    if not d.exists():
        return False
    shutil.rmtree(d)
    return True


def list_profiles(voice_dir: Path) -> list[dict]:
    if not voice_dir.exists():
        return []
    out = []
    for p in sorted(voice_dir.glob("*/profile.json")):
        try:
            out.append(json.loads(p.read_text()))
        except json.JSONDecodeError:
            continue
    return out
