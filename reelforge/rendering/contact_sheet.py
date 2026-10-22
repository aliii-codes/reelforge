"""Contact sheet: one labelled frame per scene (middle of each scene) in a grid."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from reelforge.visuals.scene_manifest import SceneManifest

THUMB_W, THUMB_H = 270, 480
LABEL_H = 44


def _font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    for name in ("DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def extract_frame(video: Path, t: float, out: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-y",
            "-ss",
            f"{t:.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            f"scale={THUMB_W}:{THUMB_H}",
            str(out),
        ],
        check=True,
    )


def make_contact_sheet(video: Path, manifest: SceneManifest, out: Path, cols: int = 4) -> Path:
    fps = manifest.fps
    scenes = manifest.scenes
    rows = (len(scenes) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * THUMB_W, rows * (THUMB_H + LABEL_H)), (18, 16, 32))
    draw = ImageDraw.Draw(sheet)
    font = _font(15)
    with tempfile.TemporaryDirectory() as td:
        for i, s in enumerate(scenes):
            mid = (s.start_frame + s.end_frame) / 2 / fps
            png = Path(td) / f"{i}.png"
            extract_frame(video, mid, png)
            x, y = (i % cols) * THUMB_W, (i // cols) * (THUMB_H + LABEL_H)
            with Image.open(png) as im:
                sheet.paste(im.convert("RGB"), (x, y))
            label = f"{s.id} {s.type}  {s.start_frame / fps:.1f}-{s.end_frame / fps:.1f}s"
            draw.text((x + 8, y + THUMB_H + 6), label, fill=(230, 230, 240), font=font)
            draw.text(
                (x + 8, y + THUMB_H + 24),
                (s.headline or (s.stat.label if s.stat else ""))[:34],
                fill=(150, 150, 175),
                font=font,
            )
    sheet.save(out, quality=90)
    return out
