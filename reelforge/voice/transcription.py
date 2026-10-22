"""Local transcription with faster-whisper (CTranslate2, int8 on CPU).

Model weights download from Hugging Face on first use (base.en ~148 MB, MIT). Audio is
decoded by FFmpeg and passed as an array, which avoids faster-whisper's PyAV path.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np

from reelforge.schemas import Segment, Transcript, Word
from reelforge.voice.quality import frame_rms, load_audio


class TranscriptionUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=2)
def _load_model(name: str, threads: int):  # pragma: no cover - needs the model
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise TranscriptionUnavailable("faster-whisper is not installed. Run: uv sync --extra transcribe") from e
    return WhisperModel(name, device="cpu", compute_type="int8", cpu_threads=threads)


def refine_word_starts(words: list[Word], audio: np.ndarray, sr: int, max_word_s: float = 0.7) -> list[Word]:
    """Whisper often stretches a word's start back over preceding silence (especially the
    first word of a segment). Move such starts forward to where the audio becomes voiced."""
    hop_s = 0.01
    env = frame_rms(audio, sr, hop_s)
    if not len(env):
        return words
    env_db = 20 * np.log10(np.maximum(env, 1e-9))
    thresh = max(float(np.percentile(env_db, 10)) + 10, float(np.percentile(env_db, 90)) - 30)
    out = []
    for w in words:
        if w.end - w.start > max_word_s:
            a, b = int(w.start / hop_s), int(w.end / hop_s)
            voiced = np.where(env_db[a:b] > thresh)[0]
            if len(voiced):
                new_start = min((a + voiced[0]) * hop_s, w.end - 0.12)
                if new_start > w.start:
                    w = w.model_copy(update={"start": round(new_start, 3)})
        out.append(w)
    return out


def transcribe(
    path: Path, model_name: str = "base.en", threads: int = 4, initial_prompt: str | None = None
) -> Transcript:
    sr = 16000
    audio = load_audio(path, sr)
    model = _load_model(model_name, threads)
    segments, info = model.transcribe(
        audio,
        language="en",
        word_timestamps=True,
        beam_size=5,
        vad_filter=False,
        condition_on_previous_text=False,
        initial_prompt=initial_prompt,
    )
    segs: list[Segment] = []
    words: list[Word] = []
    for s in segments:
        segs.append(Segment(text=s.text.strip(), start=round(s.start, 3), end=round(s.end, 3)))
        for w in s.words or []:
            words.append(
                Word(
                    text=w.word.strip(),
                    start=round(w.start, 3),
                    end=round(w.end, 3),
                    probability=round(w.probability, 3),
                )
            )
    word_level = bool(words)
    if word_level:
        words = refine_word_starts(words, audio, sr)
    return Transcript(
        text=" ".join(s.text for s in segs).strip(),
        words=words,
        segments=segs,
        language=info.language,
        model=f"faster-whisper:{model_name}:int8",
        word_level=word_level,
        duration=round(len(audio) / sr, 3),
    )
