# Voice cloning (your own voice)

## Status — read this first

| Capability | Status on this machine (2026-10-22) |
|---|---|
| Enrolment (record → check → store → listen → approve → delete) | **Implemented and tested** (unit tests with synthetic audio). |
| Pocket TTS synthesis on CPU | **Working** — used for the demo with a *stock* voice. |
| Cloning **your** voice | **Implemented, NOT yet tested with your voice.** Two things are pending: (1) your recordings, (2) access to the gated cloning weights (see below). Until both exist, `--voice clone` refuses to run; it never substitutes a stock voice. |
| Stock voice | Available and always labelled `stock voice '…' (NOT your voice)` in the CLI, `render_metadata.json` and `validation_report.json`. |

## Model selected: Kyutai Pocket TTS

Chosen because it is the only candidate checked that does reference-audio cloning **and** is
designed for CPUs (it targets 2 CPU cores, which matches the i5-5300U).

| Item | Value | Source |
|---|---|---|
| Repo / package | https://github.com/kyutai-labs/pocket-tts · `pocket-tts` 4.0.1 on PyPI (Python 3.10–3.14) | GitHub, PyPI |
| Size | ~100M params. English weights `languages/english/model.safetensors` = **219 MB**; tokenizer < 1 MB | HF API file listing |
| Licence | Code **MIT**; weights **CC-BY-4.0** (attribution: Kyutai) | GitHub README, HF model card |
| Cloning | Reference WAV passed as an audio prompt (`get_state_for_audio_prompt`); **no training/fine-tuning**. Voice state can be cached to `.safetensors`. | GitHub README |
| Gating | `kyutai/pocket-tts` (cloning-capable weights) is gated: you must log in to Hugging Face and accept conditions, which forbid "voice impersonation or cloning without explicit and lawful consent". `kyutai/pocket-tts-without-voice-cloning` is ungated (stock voices only). | HF model card |
| Dependencies | PyTorch ≥ 2.5 (CPU wheel ≈ 200 MB download, installed from the PyTorch CPU index), safetensors, sentencepiece, scipy | pyproject |
| Measured speed here | ~0.8–1.05× real time (≈ 50–60 s of compute per 55 s take) after the model is cached; first load ~100 s incl. download | measured 2026-10-22 |
| RAM | ~1.5–2 GB during synthesis (fits in 16 GB alongside Whisper and Chromium) | observed |

Candidates considered and why they were not chosen as the default:

- **Chatterbox (Resemble AI)** — MIT, cloning from ~10 s; Turbo is 350M, Nano 110M targets CPU
  ("3× real time on 8 cores"). All output carries Resemble's PerTh watermark. Recommended
  Python 3.11 and pinned deps. A good alternative if Pocket TTS quality disappoints; not
  installed.
- **NeuTTS Air (Neuphonic)** — Apache-2.0, 0.7B, GGUF for CPU, cloning from 3–15 s. Needs the
  `espeak-ng` system package (would require `sudo apt`), and is gated on HF. Not installed.
- **F5-TTS** — code MIT but the released weights are CC-BY-NC (non-commercial); slow on CPU.
- **Kokoro-82M** — Apache-2.0 and fast, but **no voice cloning** (preset voices only).

## Minimum viable voice sample

- 2–3 clips, **10–20 s each** (hard minimum 5 s per clip, 8 s total; ReelForge uses up to
  20 s as the reference prompt).
- Quiet room, no music/other voices, no clipping, consistent mic distance.
- Speak in the energy you want for the reels — the clone copies style and recording quality,
  including room echo and noise.

`uv run python -m reelforge.main voice-guide` prints the full checklist.

## Setup steps

```bash
# 1. Record (any phone voice-memo app works; or on Linux):
ffmpeg -f pulse -i default -ac 1 -ar 48000 -t 20 my_voice_1.wav

# 2. Enrol (asks you to confirm the consent statement; files stay in voice_data/)
uv run python -m reelforge.main voice-enroll --file my_voice_1.wav --file my_voice_2.wav

# 3. Listen to the reference clip it built, then approve it
ffplay -autoexit -nodisp voice_data/default/reference.wav
uv run python -m reelforge.main voice-approve

# 4. Unlock the cloning weights (one-time):
#    - log in at https://huggingface.co/kyutai/pocket-tts and accept the conditions
#    - make sure this machine has your HF token: uv run hf auth login
#    - if the no-cloning weights were cached earlier, Pocket TTS picks the gated ones once access works

# 5. Test, then use it in a job
uv run python -m reelforge.main voice-test --text "Testing my cloned voice."
uv run python -m reelforge.main create --script-file examples/sample_script.txt --voice clone
```

## What happens to your recordings

- Copied to `voice_data/<profile>/raw/`, trimmed/normalised copies in `clips/`, the combined
  prompt in `reference.wav`, and (after first use) a cached `voice_state.safetensors`.
- `voice_data/` is in `.gitignore`. Nothing is uploaded: Pocket TTS runs locally; the only
  network access is the one-time model download from Hugging Face.
- Consent text and timestamp are stored in `profile.json` and referenced in each job's
  `render_metadata.json`.
- Replace: `voice-enroll --replace ...`. Delete everything: `voice-delete --profile default`.

## Expected quality and limitations

- Short-prompt cloning captures timbre and general style, not every nuance; accent and
  prosody can drift on long or unusual sentences. Generate several takes (default 3) and pick.
- The take checker transcribes each take with Whisper and compares it with the approved
  script (missing/extra/substituted words, long pauses, clipping, duration). **This does not
  prove pronunciation or naturalness** — always listen before approving.
- Pronunciation fixes: add `# say: WORD = how to say it` lines to the script (TTS-only; the
  approved text and captions keep the original spelling). Speaking rate: `--rate 0.9..1.15`
  (FFmpeg `atempo`, pitch preserved).
- If cloning cannot be made to work, `--voice file --narration my_read.wav` uses your own
  recorded narration directly (one take, still transcribed and checked).
