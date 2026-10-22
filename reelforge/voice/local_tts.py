"""Kyutai Pocket TTS (CPU) — stock voices and the shared synthesis loop.

Pocket TTS: code MIT, weights CC-BY-4.0, ~100M params, 24 kHz output. Stock voices come from
the ungated `kyutai/pocket-tts-without-voice-cloning` repo. The default stock voice "marius"
is a CC0 voice donation (kyutai/tts-voices/voice-donations).
"""

from __future__ import annotations

import time
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf

from reelforge.schemas import Script
from reelforge.voice.base import VoiceEngine, VoiceUnavailable, apply_pronunciations

# Stock voices whose source recordings are permissively licensed for commercial use.
SAFE_STOCK_VOICES = {
    "marius": "CC0 (Kyutai voice donation 'Selfie.wav')",
    "javert": "CC0 (Kyutai voice donation 'Butter.wav')",
    "george": "CC-BY-4.0 (VCTK p315) - attribution required",
    "paul": "CC-BY-4.0 (VCTK p259) - attribution required",
    "michael": "CC-BY-4.0 (VCTK p360) - attribution required",
}

SECTION_PAUSE_S = 0.32


@lru_cache(maxsize=1)
def load_pocket_model():  # pragma: no cover - needs the model
    try:
        from pocket_tts import TTSModel
    except ImportError as e:
        raise VoiceUnavailable("pocket-tts is not installed. Run: uv sync --extra voice") from e
    return TTSModel.load_model()


class PocketTTSEngine(VoiceEngine):
    name = "pocket-tts"

    def __init__(self, conditioning: str | Path, voice_label: str, provenance: str, licence_note: str):
        self.conditioning = conditioning
        self.voice_label = voice_label
        self.provenance = provenance
        self.licence_note = licence_note
        self._state = None
        self.last_generation_seconds: float | None = None

    def _voice_state(self):  # pragma: no cover - needs the model
        if self._state is None:
            model = load_pocket_model()
            self._state = model.get_state_for_audio_prompt(self.conditioning)
        return self._state

    def synthesize(
        self, script: Script, out_path: Path, seed: int, pronunciations: dict[str, str]
    ) -> None:  # pragma: no cover
        import torch

        model = load_pocket_model()
        state = self._voice_state()
        sr = model.sample_rate
        torch.manual_seed(seed)
        pieces: list[np.ndarray] = []
        t0 = time.time()
        for i, sec in enumerate(script.sections):
            text = apply_pronunciations(sec.text, pronunciations)
            audio = model.generate_audio(state, text, copy_state=True).numpy().squeeze()
            pieces.append(audio.astype(np.float32))
            if i < len(script.sections) - 1:
                pieces.append(np.zeros(int(sr * SECTION_PAUSE_S), dtype=np.float32))
        self.last_generation_seconds = round(time.time() - t0, 2)
        full = np.concatenate(pieces)
        peak = float(np.max(np.abs(full))) or 1.0
        full = full * min(1.0, 0.89 / peak)  # leave ~1 dB headroom
        sf.write(out_path, full, sr, subtype="PCM_16")


def stock_engine(voice: str) -> PocketTTSEngine:
    if voice not in SAFE_STOCK_VOICES:
        raise VoiceUnavailable(
            f"stock voice {voice!r} is not in the vetted list {sorted(SAFE_STOCK_VOICES)}; "
            "other Kyutai voices include non-commercial (Expresso) recordings"
        )
    return PocketTTSEngine(
        conditioning=voice,
        voice_label=f"stock voice '{voice}' (NOT your voice)",
        provenance=f"Pocket TTS stock voice '{voice}' - this is NOT a clone of the user's voice",
        licence_note=f"Pocket TTS weights CC-BY-4.0 (Kyutai); voice: {SAFE_STOCK_VOICES[voice]}",
    )
