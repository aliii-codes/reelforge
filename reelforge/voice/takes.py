"""Generate multiple narration takes, transcribe each, score and rank them."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

from reelforge.schemas import JobConfig, Script, TakeReport, Transcript
from reelforge.voice.base import VoiceEngine, change_speed
from reelforge.voice.quality import analyze_audio, compare_transcript, score_take

Transcriber = Callable[[Path], Transcript]

BASE_SEED = 1234


def take_paths(takes_dir: Path, index: int) -> tuple[Path, Path, Path]:
    return (
        takes_dir / f"take_{index}.raw.wav",
        takes_dir / f"take_{index}.wav",
        takes_dir / f"take_{index}.transcript.json",
    )


def generate_takes(
    engine: VoiceEngine,
    script: Script,
    cfg: JobConfig,
    takes_dir: Path,
    transcriber: Transcriber,
    log: Callable[[str], None] = print,
) -> list[TakeReport]:
    """Create/check up to cfg.takes takes. Existing valid takes are reused (resume-safe)."""
    takes_dir.mkdir(parents=True, exist_ok=True)
    n = cfg.takes if engine.supports_takes else 1
    reports: list[TakeReport] = []
    for i in range(1, n + 1):
        raw, final, tr_path = take_paths(takes_dir, i)
        seed = BASE_SEED + i
        gen_s: float | None = None
        if not final.exists():
            log(f"  take {i}/{n}: synthesizing with {engine.voice_label} ...")
            t0 = time.time()
            engine.synthesize(script, raw, seed, cfg.pronunciations)
            change_speed(raw, final, cfg.speaking_rate if engine.allow_rate_change else 1.0)
            gen_s = round(time.time() - t0, 1)
            if tr_path.exists():
                tr_path.unlink()
        else:
            log(f"  take {i}/{n}: reusing existing audio")
        if tr_path.exists():
            transcript = Transcript.model_validate_json(tr_path.read_text())
        else:
            log(f"  take {i}/{n}: transcribing ...")
            transcript = transcriber(final)
            tr_path.write_text(transcript.model_dump_json(indent=1))
        audio = analyze_audio(final)
        diff = compare_transcript(script.full_text, transcript.text)
        score, issues = score_take(diff, audio, cfg.target_min_seconds, cfg.target_max_seconds)
        reports.append(
            TakeReport(
                index=i,
                path=str(final),
                engine=engine.name,
                voice_label=engine.voice_label,
                seed=seed if engine.supports_takes else None,
                generation_seconds=gen_s,
                duration=audio.duration,
                transcript_path=str(tr_path),
                wer=diff.wer,
                missing_words=diff.missing,
                extra_words=diff.extra,
                substitutions=diff.substitutions,
                audio=audio,
                score=score,
                issues=issues,
            )
        )
        log(f"  take {i}: score {score:.1f}, WER {diff.wer:.1%}, {audio.duration:.1f}s")
    (takes_dir / "takes_report.json").write_text(json.dumps([r.model_dump(mode="json") for r in reports], indent=1))
    return reports


def best_take(reports: list[TakeReport]) -> TakeReport:
    return sorted(reports, key=lambda r: (-r.score, r.audio.longest_pause, r.index))[0]
