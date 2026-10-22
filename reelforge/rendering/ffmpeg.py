"""FFmpeg/FFprobe helpers: audio mixing with ducking, muxing, probing."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


class FFmpegUnavailable(RuntimeError):
    pass


def check_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise FFmpegUnavailable(f"{tool} not found on PATH. Install FFmpeg (e.g. `sudo apt install ffmpeg`).")


def ffmpeg_version() -> str:
    out = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=False).stdout
    return out.splitlines()[0] if out else "unknown"


def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {out.stderr[:300]}")
    return json.loads(out.stdout)


def build_mix_command(
    *,
    narration: Path,
    output: Path,
    duration: float,
    music: Path | None = None,
    music_db: float = -10.0,
    sfx: Path | None = None,
    sfx_db: float = -26.0,
    music_stem: Path | None = None,
) -> list[str]:
    """Narration + optional music bed (sidechain-ducked under speech) + optional SFX track,
    loudness-normalised to about -14 LUFS (typical for short-form platforms).

    The music bed is expected at the -16 LUFS reference (see `sound.REFERENCE_LUFS`), so the
    default `music_db=-10` puts it ~13-14 LU under a continuously talking voice, dipping ~6 dB more while words are
    spoken. `music_stem` also writes the ducked bed on its own so its level can be verified."""
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(narration)]
    filters = [f"[0:a]aresample=48000,aformat=channel_layouts=stereo,apad,atrim=0:{duration:.3f}[voice]"]
    mix_inputs = ["[voicemix]"]
    idx = 1
    if music is not None:
        cmd += ["-stream_loop", "-1", "-i", str(music)]
        filters.append("[voice]asplit=2[voicemix][sc]")
        filters.append(
            f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{duration:.3f},volume={music_db}dB[bed]"
        )
        duck = "sidechaincompress=threshold=0.05:ratio=3:attack=30:release=350"
        if music_stem is not None:
            filters.append(f"[bed][sc]{duck}[duckedall]")
            filters.append("[duckedall]asplit=2[ducked][stem]")
        else:
            filters.append(f"[bed][sc]{duck}[ducked]")
        mix_inputs.append("[ducked]")
        idx += 1
    else:
        filters[0] = filters[0].replace("[voice]", "[voicemix]")
    if sfx is not None:
        cmd += ["-i", str(sfx)]
        filters.append(f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,volume={sfx_db}dB[fx]")
        mix_inputs.append("[fx]")
    if len(mix_inputs) > 1:
        filters.append("".join(mix_inputs) + f"amix=inputs={len(mix_inputs)}:duration=first:normalize=0[mixed]")
        last = "[mixed]"
    else:
        last = "[voicemix]"
    # loudnorm can return slightly fewer samples than it received; pad back to the exact length
    # so the mux never has to shorten the video to match the audio.
    filters.append(f"{last}loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000,apad,atrim=0:{duration:.3f}[out]")
    cmd += ["-filter_complex", ";".join(filters), "-map", "[out]", "-ar", "48000", "-c:a", "pcm_s16le", str(output)]
    if music is not None and music_stem is not None:
        cmd += ["-map", "[stem]", "-ar", "48000", "-c:a", "pcm_s16le", str(music_stem)]
    return cmd


def build_music_normalize_command(src: Path, dst: Path, lufs: float = -16.0) -> list[str]:
    """Bring a user-supplied music file to the same loudness reference as the generated bed."""
    return [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(src),
        "-af",
        f"loudnorm=I={lufs}:TP=-2:LRA=11",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-c:a",
        "pcm_s16le",
        str(dst),
    ]


def build_mux_command(*, video: Path, audio: Path, output: Path, duration: float | None = None) -> list[str]:
    """Copy the video stream, encode AAC. With `duration` the output is cut to exactly the video
    length (no `-shortest`, which drops trailing video frames when the audio is a hair short)."""
    length = ["-t", f"{duration:.3f}"] if duration else ["-shortest"]
    return [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(video),
        "-i",
        str(audio),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        *length,
        "-movflags",
        "+faststart",
        str(output),
    ]


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd[:6])} ...\n{proc.stderr[-800:]}")
