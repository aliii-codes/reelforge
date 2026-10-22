# Architecture

```
topic ──► research (Wikipedia/Tavily/manual, pages actually opened)
      ──► LLM: 5 hooks → ranked (LLM score + heuristics) → script draft + claims   (Groq → Cohere → Ollama)
script file ──► parser (sections, visual hints, [source]/[claim], # say: pronunciations)
                         │
                         ▼
          script version vN (immutable JSON, sha256)  ◄── revise (LLM feedback or edited file) = new version
                         │  human approval (hash frozen in SQLite)
                         ▼
 generating_voice   N takes (Pocket TTS clone | stock | your recording) → Whisper transcript per take
                    → WER/missing/extra + audio checks → score → best take = narration.wav
 aligning_captions  script words ↔ Whisper word timestamps (difflib) → groups (≤3 words) → validation
 planning_scenes    beats from the final narration (section starts, sentence ends, pauses, commas) →
                    DP picks cuts near the target pace (default 3.2 s) → scenes (hints > LLM plan >
                    heuristics; diagram/demo hold and reveal steps on beats) + word-synced cues
                    (count-ups, steps, reveal words, emphasis punch) + layouts (center/focus) +
                    avatar gestures (brows on emphasis, nods at sentence ends) + SFX cues
                    → scene_manifest.json v2 (validated)
 previewing         360x640 Remotion render + real mix → preview checks + preview contact sheet
 awaiting_preview_approval ──► approve-preview
 rendering          Remotion (muted H.264 1080x1920@30) + Cover still
                    → generated bed/whooshes → FFmpeg mix (sidechain duck, loudnorm −14 LUFS) → mux AAC
                    → ffprobe/decode/blackdetect/silencedetect → contact sheet → package files
 awaiting_video_approval ──► approve-video → completed      (never auto-published)
```

## Packages (`reelforge/`)

| Module | Responsibility |
|---|---|
| `config.py` | Settings from `.env`/environment; `public_dict()` redacts secrets |
| `schemas.py` | Pydantic models: Script, ScriptVersion, Source, Claim, Transcript, TakeReport, JobConfig |
| `database.py` | SQLite: `jobs`, `script_versions`, `stage_runs`, `events` (paths/metadata only) |
| `jobs/state.py` | `JobState` enum + explicit transition table |
| `jobs/orchestrator.py` | `Pipeline`: create, revise, approve, run stages, resume, package |
| `providers/` | `LLMProvider` base (4 operations, JSON validation, retries, repair) + Groq, Cohere, Ollama, `FallbackLLM` |
| `research/` | search providers, real page fetching, lexical claim checks |
| `scripting/` | manual script parser, hook ranking, generation/revision, pre-approval checks |
| `voice/` | engine interface, recorded voice-over (`voiceover.py`: record/check/process), Pocket TTS (stock + clone), enrolment, takes, Whisper, quality checks |
| `captions/` | alignment to script, grouping, validation |
| `visuals/` | beat detection (`beats.py`), scene planner, avatar tracks, SceneManifest schema (the Python↔Remotion contract) |
| `rendering/` | Remotion runner, FFmpeg mix/mux/probe, generated sound, video validation, contact sheet |
| `export/` | captions/hashtags/script.md, package completeness, safe paths, export copy |
| `main.py` | Typer CLI |

## Python ↔ Remotion contract

`scene_manifest.json` (Pydantic `SceneManifest`, mirrored by `renderer/src/types.ts`) is
passed as `--props`; the job's `work/public/` is passed as `--public-dir` (holds
`narration.wav` for Studio previews). Remotion renders **muted**; all audio goes through FFmpeg
so mixing/ducking/loudness stay in Python. You can hand-edit `scene_manifest.json` and run
`rework JOB --stage rendering` (it is re-validated first).

Layout on the 1080×1920 canvas: scene panel y 210–910; avatar centred at y≈1105; captions at
y≈1430; bottom 380 px and top 200 px kept clear for platform UI.

## Why these choices

- **Remotion 4 + FFmpeg** (as requested): benchmarked on this laptop at ~4.6 fps for full
  1080×1920 frames (JPEG frame capture, concurrency 4), i.e. ~6 min for a 55 s reel. No GPU
  needed (`swangle` software GL). Kept.
- **Pocket TTS**: only checked option with reference-audio cloning built for 2 CPU cores.
- **faster-whisper base.en int8**: ~0.3× real time on this CPU with word timestamps; audio is
  decoded by FFmpeg and passed as an array (avoids a PyAV API mismatch in faster-whisper 1.2.1).
- **JSON-object mode + local Pydantic validation** for LLMs: works on every Groq/Cohere model,
  so model retirements don't break the pipeline.
- **No FastAPI/Docker/queues**: a CLI + SQLite is enough for 1–3 videos per batch.

## Resume semantics

Each stage reads inputs from disk and writes outputs before the state advances. A failure
records `failed_stage` + error; `resume` re-enters that stage. The voice stage reuses existing
takes (keyed by the approved script hash — takes for an older script are archived, not
deleted). Replaced outputs (e.g. a re-rendered `final_reel.mp4`) are moved to
`work/archive/<timestamp>/`.
