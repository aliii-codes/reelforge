# ReelForge AI

Local-first, free-first pipeline that turns a topic or a script into a finished vertical
(1080×1920, 30 fps, H.264/AAC) faceless explainer reel for Instagram Reels / YouTube Shorts:
researched and fact-labelled script → human approval → narration takes (your cloned voice, a
labelled stock voice, or your own recording) → transcription check → word-timed captions →
original animated SVG avatar + timed motion-graphic scenes → Remotion + FFmpeg render →
validation → cover, caption, 5 hashtags and metadata → human approval. **It never publishes
anything.**

> Status summary: see [What works / what's pending](#what-works-whats-pending). Voice cloning
> of *your* voice is implemented but waits on your recordings + Hugging Face gate acceptance.

## Hardware assumptions

Built and measured on a Dell Latitude E5550: i5-5300U (2C/4T), 16 GB RAM, GeForce 830M (not
used — no CUDA required), SSD, Kali Linux. Everything runs on CPU.

## Install (Kali Linux, no sudo needed if FFmpeg and Node are present)

Requirements: Python 3.12 (uv installs/uses it), `uv`, Node.js ≥ 18 (tested 22.23), FFmpeg +
FFprobe (tested 8.1.1).

```bash
cd ~/Documents/ReelForge
ffmpeg -version | head -1 && ffprobe -version | head -1 && node --version   # checks
uv sync --extra transcribe --extra voice      # Python deps (CPU-only PyTorch, ~1 GB installed)
(cd renderer && npm install && npx remotion browser ensure)   # Remotion 4 + Chrome Headless Shell (~600 MB)
cp .env.example .env                          # optional: API keys, handle, etc.
uv run python -m reelforge.main doctor        # verify everything
```

Disk: ~1 GB Python env, ~520 MB `renderer/node_modules` (incl. 99 MB Chrome Headless Shell),
models in `~/.cache/huggingface`: Whisper base.en 148 MB, Pocket TTS ~220 MB (+220 MB for the
cloning weights once unlocked). Each job output is ~30–60 MB.

Models download on first use: Whisper `base.en` (148 MB, MIT) and Pocket TTS English weights
(219 MB, CC-BY-4.0). See [docs/licences.md](docs/licences.md).

## Configure (optional)

`.env` (never committed; see `.env.example`):

- `GROQ_API_KEY` (primary) / `COHERE_API_KEY` (alternative) for topic → script generation.
  Free access verified 2026-10-22, with limits; see [docs/providers.md](docs/providers.md).
  Not needed for `--script-file`.
- `TAVILY_API_KEY` optional; Wikipedia search needs no key. Set `REELFORGE_CONTACT` (email/URL)
  for the Wikipedia User-Agent.
- `REELFORGE_HANDLE=@you` to show your handle on videos and the cover.

## Web UI

```bash
python -m reelforge.web          # or: reelforge-web   → opens http://127.0.0.1:8765/
```

No extra dependencies (standard library server, one HTML page). Reels on the left; the selected
reel's script, rendered frames and checks on the right, with only the buttons that make sense
for its state (pick a draft, record voice, use an audio file, AI voice, approve, render, resume).
Previews and final videos play in the page; voice is recorded in the browser and checked before
you use it. Every button runs the same CLI command you could type, so jobs started in the web UI
can be inspected or resumed from the terminal and vice versa. One step runs at a time; the
activity drawer shows the live log. It listens on 127.0.0.1 only.

## Run it

```bash
# A. From your own script (works offline; no API key)
uv run python -m reelforge.main create --script-file examples/sample_script.txt --handle @you
#    → shows the script, claims (with check status) and sources; then:
uv run python -m reelforge.main approve-script JOB_ID          # confirm, then voice → render
#    or revise first:
uv run python -m reelforge.main revise JOB_ID --file my_edit.txt        # manual edit → v2
uv run python -m reelforge.main revise JOB_ID --feedback "punchier hook" # LLM revision → v2

# B. From a topic (needs GROQ_API_KEY or COHERE_API_KEY)
uv run python -m reelforge.main create --topic "How small AI models work" [--sources-file my_links.txt]

# Voice options for create:
#   --voice stock   (default; labelled stock voice, NOT you)
#   --voice clone   (your enrolled voice; see docs/voice-cloning.md)
#   --voice file --narration my_read.wav   (your own recording)
#   --takes 3  --rate 1.05  --music generated|none|path --music-licence "..."  --no-sfx

uv run python -m reelforge.main status JOB_ID
uv run python -m reelforge.main list
uv run python -m reelforge.main takes JOB_ID            # compare narration takes
uv run python -m reelforge.main select-take JOB_ID 2    # use another take (re-captions + re-renders)
uv run python -m reelforge.main render-preview JOB_ID --scale 0.5   # fast 540x960 preview with audio
uv run python -m reelforge.main resume JOB_ID           # continue after a failure / interruption
uv run python -m reelforge.main approve-video JOB_ID    # after watching final_reel.mp4
uv run python -m reelforge.main export JOB_ID [--dest ~/Videos/reels]
uv run python -m reelforge.main claims JOB_ID C2 --status human_verified --note "checked HF docs"
uv run python -m reelforge.main benchmark               # render-speed check on this machine
```

(With the venv activated — `source .venv/bin/activate` — you can drop `uv run`, and the
`reelforge` console script is also available.)

### From a topic: research → 3 drafts → you pick → you choose the voice → video

```bash
python -m reelforge.main create --topic "Why AI image generators struggle with hands"
```

1. ReelForge asks the LLM for encyclopedia search queries, opens the matching Wikipedia
   articles (keeping the relevant paragraphs), and drops off-topic results.
2. It writes **3 drafts with different angles** (numbers-first, story & analogy, myth-busting),
   each with its own hook, and shows them side by side with "facts matched in sources".
3. **It asks which draft you want.**
4. **It asks how to narrate it:** record your voice now (recommended), use an audio file you
   already have, or the AI voice (a synthetic stock voice, only after you confirm, and labelled
   as not you).
5. It times everything to the voice and builds the quick preview; then the full render.

Non-interactive equivalents: `drafts JOB`, `pick JOB N`, `voice JOB --record | --file F | --ai`.
The app does the same: **New Reel → From a topic → Use Draft N → Record Voice / audio file / AI voice**.
Needs `GROQ_API_KEY` and/or `COHERE_API_KEY` in `.env` (when both are set, drafts alternate
between them to stay inside the free per-minute limits). About 30 s for research + 3 drafts.

### Recorded voice-over (recommended for natural delivery)

```bash
python -m reelforge.main voiceover-record --script-file examples/voiceover_demo_script.txt --out voice_data/recordings/demo2.wav
python -m reelforge.main create --script-file examples/voiceover_demo_script.txt --voice file --narration voice_data/recordings/demo2.wav
python -m reelforge.main approve-script JOB_ID --yes     # -> low-res preview + checks, then stops
python -m reelforge.main approve-preview JOB_ID          # -> full render
```

Your processed voice-over drives the edit: cuts land on sentence ends and pauses, graphics,
stat count-ups, diagram steps and terminal lines appear on the frame their word is spoken, the
avatar raises its brows on emphasised numbers/terms and nods at sentence ends, and whooshes only
mark section changes. See [docs/voice-over.md](docs/voice-over.md).

### Script file format

Plain paragraphs work (roles are inferred). Optional markup gives control — see
`examples/sample_script.txt`:

```
# title: ...            # caption: ...      # hashtags: #A #B #C #D #E
# say: CPU = C P U      (pronunciation for TTS only)
[hook] ... text ...
> headline: On-screen words | kicker: Small label
> scene: stat | value: 14 | suffix: GB | label: at 16-bit
> scene: diagram | items: Step one ; Step two ; Step three
> left: A | right: B          > expression: surprised|thoughtful|happy|skeptical|neutral
[explain] [beat] [number] [analogy] [twist] [payoff] [cta]
[source] https://url | note
[claim] Claim text | https://url1, https://url2
```

## Approvals

1. **Script**: `create` shows the full script, word count/estimate, hook candidates, every
   claim with its check status and sources. `approve-script` freezes that exact version
   (sha256 stored in SQLite; version files are read-only). Any later change creates a new
   version that must be approved again.
2. **Final video**: the job stops at `awaiting_video_approval`. Watch
   `output/JOB_ID/final_reel.mp4` (`xdg-open`, `mpv`, `ffplay`), look at `contact_sheet.jpg`
   and `validation_report.json`, then `approve-video` (or `rework --stage ...`).

## Output package (`output/JOB_ID/`)

`final_reel.mp4`, `cover.png`, `caption.txt`, `hashtags.txt` (5), `script.md`,
`sources.json`, `claims.json`, `narration.wav`, `transcript.json`, `captions.json`,
`scene_manifest.json`, `render_metadata.json` (versions, timings, voice provenance, licences),
`validation_report.json`, `contact_sheet.jpg`, `project_config.json` (secrets redacted),
`package_manifest.json` (sha256 of each file), plus `script_versions/` and `work/` (takes,
silent render, mix, logs, archives). Job directories are never reused or overwritten.

## Resuming failed jobs

Every stage persists its outputs and status in SQLite (`data/reelforge.db`). If a stage fails,
`status` shows the error and `resume JOB_ID` restarts at that stage, reusing earlier outputs
(e.g. narration takes are not regenerated after a render crash).

## Offline vs online

| Needs internet | Works offline (after setup + model download) |
|---|---|
| `--topic` script generation (Groq/Cohere), web research, opening source URLs, first-time model downloads | `--script-file` jobs with `--offline`, TTS (stock/clone), transcription, captions, scenes, rendering, validation, export |

## Privacy

- Voice recordings stay in `voice_data/` (git-ignored); never uploaded. Delete with
  `voice-delete`. Cloning requires an explicit consent confirmation that only your own voice
  is used.
- Scripts and audio are processed locally. The only data sent out: prompts to the LLM
  provider you configured (topic, sources excerpts, script for revision) and HTTP requests to
  open source URLs.
- API keys live only in `.env`; logs and job files record `set`/`missing` only.

## Docs

- [docs/architecture.md](docs/architecture.md) — pipeline, modules, contracts, design choices
- [docs/voice-over.md](docs/voice-over.md) — recording, checks, processing, caption source, preview gate
- [docs/providers.md](docs/providers.md) — Groq/Cohere/Tavily/Wikipedia findings (dated)
- [docs/voice-cloning.md](docs/voice-cloning.md) — enrolment, model, licence, limits
- [docs/licences.md](docs/licences.md) — dependency/model/asset licences and sizes
- [docs/troubleshooting.md](docs/troubleshooting.md)

## Tests

```bash
uv run pytest            # all tests (mocked providers; FFmpeg used for real; ~1 min)
uv run pytest -m "not slow"
uv run ruff check reelforge && uv run mypy reelforge
(cd renderer && npx tsc --noEmit)
```

## Demo results (measured on this laptop, 2026-10-22)

Job `20261022-0852-how-a-laptop-runs-a-7-billion-pa-44d1` from `examples/sample_script.txt`
(161 words, 7 claims, 5 sources opened), stock voice `marius` (**not** a clone):

- `output/<job>/final_reel.mp4`: H.264 1080×1920 yuv420p @ 30 fps + AAC 48 kHz stereo,
  58.6 s, 13.6 MB, integrated loudness −15.5 LUFS. Checks: ffprobe, full decode,
  blackdetect, silencedetect — 0 errors, 0 warnings.
- Narration: 3 takes in 194 s total (Pocket TTS ≈ 0.8–1× real time + Whisper base.en).
  Auto-selected take 3 (WER 0 %). The checker caught real TTS defects in take 2 (repeated
  "16. 16." and "compression. compression.") and a trailing "either" in take 1.
- Remotion: 1563 frames in ≈ 4 min on an idle machine (≈ 6 fps, concurrency 4); 1760 frames
  took ≈ 10.4 min with the desktop busy. With heavy load after a reboot the estimate rose
  above 1 h and the laptop shut down twice during long renders — **close heavy apps and
  consider `REELFORGE_RENDER_CONCURRENCY=2` for full renders** (likely thermal; unconfirmed).
- Final assembly (cover still, mix, mux, validation, contact sheet): 51 s.
- So "≈ 10–15 min after script approval" is achievable on an idle machine (≈ 9–10 min
  measured from parts), not guaranteed.

## What works / what's pending

| Area | Status |
|---|---|
| Manual script → approved, hash-frozen version → narration → captions → scenes → Remotion/FFmpeg render → validation → package | **Working, demonstrated end to end** |
| Multiple takes, transcript check, scoring, `takes` / `select-take` | Working (real run) |
| Resume after failure (real crash in the sound generator, Node not on PATH, session kills) | Working (real runs + tests) |
| Word-level captions from Whisper aligned to script spelling | Working; 3/161 words interpolated in demo (flagged) |
| Original SVG avatar, loudness mouth + viseme guesses, expressions per scene, blinks | Working (heuristic lip-sync, not phoneme-accurate) |
| Explainer visual style (default for new jobs, `--style explainer`): dotted canvas, outlined cards, presenter with poses + speech-bubble captions, per-beat diagrams chosen from the narration (network / knobs / data stream / steps / chain / stat / scale / compare / code), chapter tabs from `step:` hints | Working, demonstrated end to end ("How AI models learn from data"); see [docs/editing-style.md](docs/editing-style.md). `--style creator` keeps the original dark look |
| Cover, caption, 5 hashtags, sources/claims, metadata, contact sheet | Working |
| Claim checking | Lexical match against pages actually fetched; labelled, needs human review |
| Groq / Cohere / Ollama script generation | Implemented, **mock-tested only** (no keys configured) |
| Wikipedia / Tavily search | Implemented; Tavily mock-only; Wikipedia article fetching works live, **Wikipedia API search got HTTP 403 (robot policy) without `REELFORGE_CONTACT`** |
| Cloning **your** voice | Implemented + unit-tested; **pending your recordings and HF gate acceptance** |
| Local web UI (`python -m reelforge.web`) | Working |
