"""Voice engine interface and the user-recording "engine".

Every engine reports a `provenance` string that ends up in render metadata, so the output
package always states truthfully whose voice the narration is.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

from reelforge.schemas import Script


class VoiceUnavailable(RuntimeError):
    pass


class VoiceEngine(ABC):
    name = "base"
    #: e.g. "user voice clone (Pocket TTS)", "stock voice 'marius' - NOT the user's voice"
    voice_label = ""
    provenance = ""
    licence_note = ""
    supports_takes = True
    allow_rate_change = True  # False for human recordings (time-stretching a real voice sounds off)

    @abstractmethod
    def synthesize(self, script: Script, out_path: Path, seed: int, pronunciations: dict[str, str]) -> None:
        """Write narration for the whole script to `out_path` (WAV)."""


def apply_pronunciations(text: str, pronunciations: dict[str, str]) -> str:
    """Replace whole words for TTS only (the approved script itself is never changed)."""
    for word, spoken in sorted(pronunciations.items(), key=lambda kv: -len(kv[0])):
        text = re.sub(rf"(?<![\w-]){re.escape(word)}(?![\w-])", spoken, text)
    return text


def change_speed(in_path: Path, out_path: Path, rate: float) -> None:
    """Pitch-preserving tempo change via FFmpeg's atempo (0.5-2.0)."""
    if abs(rate - 1.0) < 1e-3:
        shutil.copyfile(in_path, out_path)
        return
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(in_path),
            "-filter:a",
            f"atempo={rate:.3f}",
            str(out_path),
        ],
        check=True,
    )


class RecordedNarration(VoiceEngine):
    """A voice-over the user recorded. One take; validated and gently processed, never synthesized.

    The processed file (not the original) becomes the timing source for everything downstream.
    """

    name = "recording"
    supports_takes = False
    allow_rate_change = False

    def __init__(self, path: Path, options: object | None = None):
        from reelforge.voice.voiceover import ProcessingOptions

        if not path.exists():
            raise VoiceUnavailable(f"voice-over file not found: {path}")
        self.path = path
        self.options = options if isinstance(options, ProcessingOptions) else ProcessingOptions()
        self.voice_label = "your recorded voice-over"
        self.provenance = f"user-recorded voice-over ({path.name}), processed: {self.options.key()}"
        self.licence_note = "the user's own recording"
        self.last_report: dict | None = None

    def synthesize(self, script: Script, out_path: Path, seed: int, pronunciations: dict[str, str]) -> None:
        import json

        from reelforge.voice.voiceover import process_voiceover

        self.last_report = process_voiceover(self.path, out_path, self.options)
        out_path.with_name(out_path.stem + ".processing.json").write_text(json.dumps(self.last_report, indent=1))
