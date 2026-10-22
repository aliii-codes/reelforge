from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from reelforge.config import Settings

SCRIPT_TEXT = """# title: Test reel about tiny models
# hashtags: #AI #LLM #Quantization #TechExplained #MachineLearning
# say: CPU = C P U

[hook]
A seven-billion-parameter model can run on a laptop CPU. No data center needed.
> headline: A 7B model on a laptop | kicker: No data center

[explain]
Here's how it works. A model is a giant list of numbers called weights, held in memory.
> scene: diagram | headline: Running a model | items: Weights ; Memory ; Math

[number]
At sixteen-bit precision each weight takes two bytes, so seven billion weights need fourteen gigabytes.
> scene: stat | value: 14 | suffix: GB | label: at 16-bit

[analogy]
Think of it like saving a photo as a smaller JPEG file.
> left: A huge photo | right: A small JPEG

[twist]
But here's the catch. Squeeze too hard and quality drops.

[cta]
Send this to a friend who loves tech.

[claim] One float16 has 16 bits, or 2 bytes. | https://en.wikipedia.org/wiki/Half-precision_floating-point_format
"""


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    s = Settings(
        data_dir=tmp_path / "data",
        output_dir=tmp_path / "output",
        voice_dir=tmp_path / "voice",
        renderer_dir=tmp_path / "renderer",
    )
    s.ensure_dirs()
    return s


@pytest.fixture
def script_file(tmp_path: Path) -> Path:
    p = tmp_path / "script.txt"
    p.write_text(SCRIPT_TEXT)
    return p


def write_tone(
    path: Path, seconds: float, sr: int = 24000, amp: float = 0.3, gaps: bool = True, noise: float = 0.0005
) -> Path:
    """Speech-like test signal: syllable bursts of a tone with short gaps."""
    t = np.arange(int(seconds * sr)) / sr
    sig = amp * np.sin(2 * np.pi * 180 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))
    if gaps:
        sig *= (np.sin(2 * np.pi * 2.2 * t) > -0.6).astype(float)
    sig += np.random.default_rng(0).normal(0, noise, len(t))
    sf.write(path, sig.astype(np.float32), sr)
    return path


def make_video(path: Path, seconds: float, size: str = "1080x1920", frames: int | None = None) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size={size}:rate=30:duration={seconds + 1 if frames else seconds}",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            *(["-frames:v", str(frames)] if frames else []),
            str(path),
        ],
        check=True,
    )
