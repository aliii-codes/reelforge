# Human voice-over workflow

Your own recorded narration is the most natural-sounding option and needs no model. The final,
processed voice-over is the **single timing source** for everything: caption words, scene cuts,
word-synced graphics, avatar mouth and gestures, and sound effects.

## 1. Record (or import)

```bash
# Shows the narration to read, counts down, records from the default mic, Enter stops.
python -m reelforge.main voiceover-record --script-file examples/voiceover_demo_script.txt \
    --out voice_data/recordings/demo2.wav

# Or check a file you recorded elsewhere (phone voice memo, Audacity, ...):
python -m reelforge.main voiceover-check my_read.m4a
```

Recording uses FFmpeg's PulseAudio input (works with PipeWire on Kali). Pick another mic with
`--device <name>` from `pactl list short sources`. Recordings stay in `voice_data/` (git-ignored).

Tips: quiet room, fans off, 15–20 cm from the mic, read naturally — pauses and emphasis are
good; they drive the editing. Re-record a sentence rather than leaving a stumble in.

## 2. Use it

```bash
# New job from the script + your recording (stops at the preview):
python -m reelforge.main create --script-file examples/voiceover_demo_script.txt \
    --voice file --narration voice_data/recordings/demo2.wav --handle @you
python -m reelforge.main approve-script JOB_ID --yes          # voice -> captions -> scenes -> preview

# Or attach/replace the voice-over on an existing job (redoes voice, captions, scenes, preview):
python -m reelforge.main voiceover JOB_ID --file voice_data/recordings/demo2_take2.wav
```

## Checks (`voiceover-check`, also run automatically)

| Check | Error (blocks) | Warning |
|---|---|---|
| File | missing, empty, not decodable, no audio stream | — |
| Length | < 10 s or > 120 s | — |
| Sample rate | < 16 kHz | — |
| Level | peak below −40 dBFS (muted/wrong mic) | peak below −24 dBFS |
| Clipping | > 0.5 % of samples | > 0.05 % |
| Noise | speech < 15 dB above background | < 25 dB (try `--denoise`) |
| Channels | — | one channel of a stereo file is silent (the live one is used) |
| Pauses | — | longest pause > 2 s (try `--max-pause 0.8`) |

## Processing (conservative by default)

1. Mono: live channel if the other is silent, else downmix.
2. 70 Hz high-pass (rumble only).
3. `--denoise` (off by default): light FFmpeg `afftdn` (nr=10).
4. Edge trim (on; `--no-trim` to disable): leading/trailing silence only, keeping 0.15 s
   lead-in and 0.35 s tail. **Internal pauses are kept.**
5. `--max-pause S` (off by default): pauses longer than S seconds are shortened to S (the middle
   of the silence is removed with 10 ms crossfades). Nothing is removed below S.
6. Two-pass EBU R128 loudnorm to −16 LUFS, linear mode (dynamics kept); `--no-normalize` to skip.
   The final mix with music/SFX is normalised again to about −14 LUFS.

The processing report (steps, before/after duration and loudness) is saved next to the take:
`output/JOB/work/takes/take_1.raw.processing.json`. Speaking-rate changes (`--rate`) are never
applied to human recordings.

## Captions when you don't read word-for-word

`--caption-source auto` (default) compares Whisper's transcript of your final audio with the
script. If more than 8 % of words differ, captions show **what you actually said** (Whisper's
words and timing); otherwise they show the script's spelling with your timing. Force either with
`--caption-source script|transcript`. The choice and the difference are logged.

## Preview gate

After scene planning the job renders a 360×640 preview with the real audio mix, a preview
contact sheet and the same checks as the final render (frame count vs manifest, size, fps, audio
present, full decode, black frames, long silences, first caption vs narration onset, captions
within the video). It then waits:

```bash
xdg-open output/JOB_ID/preview.mp4
python -m reelforge.main approve-preview JOB_ID       # full 1080x1920 render + final checks
python -m reelforge.main rework JOB_ID --stage planning_scenes   # after editing scene_manifest.json
```

Use `create ... --no-preview-gate` to go straight to the final render.
