"""Validate a rendered reel: container, codecs, geometry, frame rate, duration, audio,
decode integrity, black frames and long silences."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from reelforge.rendering.ffmpeg import probe


def _fps(rate: str) -> float:
    num, _, den = rate.partition("/")
    return float(num) / float(den or 1) if float(den or 1) else 0.0


def check_stream_info(
    info: dict,
    *,
    expected_duration: float | None,
    width: int = 1080,
    height: int = 1920,
    fps: float = 30.0,
    require_audio: bool = True,
    duration_tol: float = 0.25,
) -> tuple[list[str], list[str], dict]:
    errors: list[str] = []
    warnings: list[str] = []
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    fmt = info.get("format", {})
    summary: dict = {"container": fmt.get("format_name"), "size_bytes": int(fmt.get("size", 0) or 0)}
    if "mp4" not in (fmt.get("format_name") or ""):
        errors.append(f"container is {fmt.get('format_name')}, expected MP4")
    if v is None:
        errors.append("no video stream")
    else:
        vfps = _fps(v.get("avg_frame_rate") or v.get("r_frame_rate", "0/1"))
        summary.update(
            video_codec=v.get("codec_name"),
            width=v.get("width"),
            height=v.get("height"),
            fps=round(vfps, 3),
            pix_fmt=v.get("pix_fmt"),
            video_frames=int(v.get("nb_frames", 0) or 0),
        )
        if v.get("codec_name") != "h264":
            errors.append(f"video codec {v.get('codec_name')}, expected h264")
        if (v.get("width"), v.get("height")) != (width, height):
            errors.append(f"resolution {v.get('width')}x{v.get('height')}, expected {width}x{height}")
        if abs(vfps - fps) > 0.01:
            errors.append(f"frame rate {vfps:.3f}, expected {fps}")
        if v.get("pix_fmt") != "yuv420p":
            warnings.append(f"pixel format {v.get('pix_fmt')} (yuv420p is the most compatible)")
    if a is None:
        if require_audio:
            errors.append("no audio stream")
    else:
        summary.update(
            audio_codec=a.get("codec_name"), sample_rate=int(a.get("sample_rate", 0) or 0), channels=a.get("channels")
        )
        if a.get("codec_name") != "aac":
            errors.append(f"audio codec {a.get('codec_name')}, expected aac")
    dur = float(fmt.get("duration", 0) or 0)
    summary["duration"] = round(dur, 3)
    if expected_duration is not None and abs(dur - expected_duration) > duration_tol:
        errors.append(f"duration {dur:.2f}s differs from expected {expected_duration:.2f}s")
    if v is not None and a is not None:
        vd, ad = float(v.get("duration", dur) or dur), float(a.get("duration", dur) or dur)
        summary["av_duration_gap"] = round(abs(vd - ad), 3)
        if abs(vd - ad) > 0.2:
            warnings.append(f"audio ({ad:.2f}s) and video ({vd:.2f}s) durations differ")
    return errors, warnings, summary


def decode_check(path: Path) -> list[str]:
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    lines = [ln for ln in proc.stderr.splitlines() if ln.strip()]
    if proc.returncode != 0:
        return [f"decode failed: {lines[-1] if lines else 'unknown error'}"]
    return [f"decoder reported: {ln}" for ln in lines[:5]]


def black_segments(path: Path, min_s: float = 0.25) -> list[tuple[float, float]]:
    proc = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "info",
            "-nostdin",
            "-i",
            str(path),
            "-vf",
            f"scale=270:-2,blackdetect=d={min_s}:pix_th=0.06",
            "-an",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", proc.stderr)]


def silence_segments(path: Path, min_s: float = 1.5) -> list[tuple[float, float]]:
    proc = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "info",
            "-nostdin",
            "-i",
            str(path),
            "-af",
            f"silencedetect=n=-45dB:d={min_s}",
            "-vn",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", proc.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", proc.stderr)]
    return list(zip(starts, ends + [float("nan")] * (len(starts) - len(ends)), strict=False))


def validate_video(
    path: Path,
    *,
    expected_duration: float | None,
    target_min: float = 45.0,
    target_max: float = 60.0,
    full: bool = True,
    width: int = 1080,
    height: int = 1920,
) -> dict:
    if not path.exists():
        return {"ok": False, "errors": [f"{path} does not exist"], "warnings": [], "summary": {}}
    errors, warnings, summary = check_stream_info(
        probe(path), expected_duration=expected_duration, width=width, height=height
    )
    dur = summary.get("duration", 0)
    if not target_min <= dur <= target_max:
        warnings.append(f"duration {dur:.1f}s is outside the {target_min:.0f}-{target_max:.0f}s target")
    checks = ["ffprobe streams/format"]
    if full:
        errors += decode_check(path)
        blacks = black_segments(path)
        if blacks:
            errors.append(f"black frames detected: {[(round(a, 2), round(b, 2)) for a, b in blacks]}")
        sil = silence_segments(path)
        if sil:
            warnings.append(f"long silences in audio: {[(round(a, 2), round(b, 2)) for a, b in sil]}")
        checks += ["full decode", "blackdetect (>=0.25s)", "silencedetect (>=1.5s, -45dB)"]
    return {"ok": not errors, "errors": errors, "warnings": warnings, "summary": summary, "checks": checks}


def even_dim(x: float) -> int:
    """Pixel size Remotion/H.264 will produce for a scaled dimension (rounded to even)."""
    n = int(round(x))
    return n - (n % 2)


def check_render_completion(path: Path, expected_frames: int, tolerance: int = 1) -> dict:
    """The encoded video must contain every frame of the manifest (a crash or kill mid-render
    leaves no file or a short one)."""
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_packets",
            "-show_entries",
            "stream=nb_read_packets",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        frames = int(proc.stdout.strip().split(",")[0])
    except ValueError:
        return {"frames": None, "expected": expected_frames, "errors": ["could not count video frames"]}
    errors = []
    if abs(frames - expected_frames) > tolerance:
        errors.append(f"render incomplete: {frames} frames encoded, manifest has {expected_frames}")
    return {"frames": frames, "expected": expected_frames, "errors": errors}


def audio_onset_and_end(path: Path, hop_s: float = 0.01) -> tuple[float | None, float | None]:
    """First/last time the (mixed) audio is clearly voiced: 20 dB below the loud speech level,
    which sits well above the -30 dB music bed."""
    import numpy as np

    from reelforge.voice.quality import frame_rms, load_audio

    audio = load_audio(path, 16000)
    env = frame_rms(audio, 16000, hop_s)
    if not len(env):
        return None, None
    env_db = 20 * np.log10(np.maximum(env, 1e-9))
    loud = float(np.percentile(env_db, 95))
    idx = np.where(env_db > loud - 20)[0]
    if not len(idx):
        return None, None
    return round(idx[0] * hop_s, 3), round((idx[-1] + 1) * hop_s, 3)


def caption_sync_report(path: Path, manifest, tolerance_s: float = 0.3) -> dict:
    """Do captions line up with the audio actually in the file?"""
    errors: list[str] = []
    warnings: list[str] = []
    fps = manifest.fps
    groups = manifest.caption_groups
    if not groups:
        return {"errors": ["no captions in manifest"], "warnings": []}
    first_word = groups[0].words[0].start_frame / fps
    last_word = groups[-1].words[-1].end_frame / fps
    video_end = manifest.duration_frames / fps
    onset, end = audio_onset_and_end(path)
    out: dict = {
        "first_caption_s": round(first_word, 3),
        "last_caption_end_s": round(last_word, 3),
        "audio_onset_s": onset,
        "audio_end_s": end,
        "video_end_s": round(video_end, 3),
    }
    if onset is None:
        errors.append("no audible narration found in the output")
    else:
        drift = first_word - onset
        out["first_word_offset_s"] = round(drift, 3)
        if abs(drift) > tolerance_s:
            errors.append(f"first caption starts {drift:+.2f}s from the narration onset (tolerance {tolerance_s}s)")
        if end is not None and last_word > end + 0.5:
            warnings.append(f"last caption ends {last_word - end:.2f}s after the narration")
    if any(g.end_frame > manifest.duration_frames for g in groups):
        errors.append("a caption group runs past the end of the video")
    if video_end - last_word < 0.2:
        warnings.append("captions run to the very last frame; consider a longer tail")
    out.update(errors=errors, warnings=warnings)
    return out


def music_balance(narration: Path, music_stem: Path, too_quiet_lu: float = 22.0, too_loud_lu: float = 8.0) -> dict:
    """Integrated loudness of the voice vs the ducked music stem. Creator reels usually keep music
    ~10-16 LU under the voice: quieter reads as "no music", louder fights the words."""
    from reelforge.voice.voiceover import measure_lufs

    voice, music = measure_lufs(narration), measure_lufs(music_stem)
    out: dict = {"voice_lufs": voice, "music_lufs": music, "voice_minus_music_lu": None, "warnings": []}
    if voice is None or music is None or music < -70:
        out["warnings"].append("music is enabled but the music stem is silent")
        return out
    gap = round(voice - music, 1)
    out["voice_minus_music_lu"] = gap
    if gap > too_quiet_lu:
        out["warnings"].append(f"music is {gap} LU under the voice - practically inaudible (aim for 10-16)")
    elif gap < too_loud_lu:
        out["warnings"].append(f"music is only {gap} LU under the voice - it may mask the narration")
    return out
