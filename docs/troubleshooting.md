# Troubleshooting

Start with `uv run python -m reelforge.main doctor` and `... status JOB_ID`.

| Symptom | Cause / fix |
|---|---|
| `No LLM provider is configured` when using `--topic` | Add `GROQ_API_KEY` or `COHERE_API_KEY` to `.env` (see `.env.example`), then `resume JOB_ID`. Or use `--script-file`. |
| `groq: authentication failed (HTTP 401)` | Wrong/expired key. Keys are never printed; regenerate at console.groq.com/keys. |
| `rate limit reached (HTTP 429)` | Free-plan limits. ReelForge retries briefly then tries the next provider; wait and `resume`. |
| `JSON did not match schema` | The model returned unusable JSON twice. Retry, or set `GROQ_MODEL=openai/gpt-oss-120b`. |
| `Voice cloning weights are gated` | Accept the conditions at huggingface.co/kyutai/pocket-tts, run `uv run hf auth login`, retry. Until then use `--voice stock` or `--voice file`. |
| `voice profile 'default' is not approved yet` | Listen to `voice_data/default/reference.wav`, then `voice-approve`. |
| `pocket-tts is not installed` / `faster-whisper is not installed` | `uv sync --extra voice --extra transcribe` |
| `TypeError: open() got an unexpected keyword argument 'metadata_errors'` | faster-whisper ↔ PyAV mismatch. ReelForge avoids it by decoding with FFmpeg; if you call faster-whisper yourself, pass a numpy array. |
| `Remotion is not installed` | `cd renderer && npm install` (Node 18+; tested with Node 22). |
| Remotion: missing shared libraries (`libnss3`, `libatk`, `libgbm`, …) | Install the Linux deps listed at remotion.dev/docs/miscellaneous/linux-dependencies (needs sudo). Not needed on this Kali install. |
| Render very slow / laptop hot | Use `render-preview JOB --scale 0.5` while iterating; lower `REELFORGE_RENDER_CONCURRENCY` to 2 if the system swaps. |
| `caption validation failed: ... interpolated timing` | Whisper heard something very different from the script (bad take). Check `takes JOB`, `select-take JOB N`, or regenerate. |
| `scene manifest invalid` after hand-editing | Fix the listed fields (headline ≤ 60 chars, diagram 2–4 items, contiguous frames), then `rework JOB --stage rendering`. |
| `video validation failed: black frames` | A scene or the background rendered empty — open `contact_sheet.jpg` and `work/remotion_render.log`. |
| `approved script ... was modified on disk after approval` | Version files are immutable by design. Create a new version with `revise --file`, approve it, `resume`. |
| Wrong word in captions | Captions use the approved script's spelling; timings come from the audio. If a word is mis-timed, it is flagged `approximate` in `captions.json`. |
| A job is stuck in `generating_voice` after Ctrl-C | `resume JOB_ID` — existing takes are reused. |
