"""Voice-over import/processing, beat detection, audio-driven planning, caption sources, sync checks."""

import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from reelforge.captions.alignment import CaptionWord, build_caption_track
from reelforge.rendering.ffmpeg import build_mux_command
from reelforge.rendering.validation import caption_sync_report, check_render_completion, even_dim
from reelforge.scripting.manual import parse_script_text
from reelforge.tests.conftest import SCRIPT_TEXT, make_video, write_tone
from reelforge.tests.test_audio_captions import SCRIPT, full_heard, transcript_from
from reelforge.visuals.beats import candidate_beats, emphasis_word_indices, plan_segments
from reelforge.visuals.scene_planner import _fill_cues, _says_value, build_manifest
from reelforge.voice.voiceover import (
    ProcessingOptions,
    VoiceoverError,
    build_record_command,
    check_voiceover,
    process_voiceover,
)

SR = 48000


def speechlike(path: Path, *, lead=1.0, tail=1.5, pause=2.5, amp=0.3, stereo_dead=False, noise=0.0008) -> Path:
    """Two 'utterances' of syllable bursts with a long pause between, plus edge silence."""
    rng = np.random.default_rng(1)

    def burst(sec: float) -> np.ndarray:
        t = np.arange(int(sec * SR)) / SR
        env = (np.sin(2 * np.pi * 3.5 * t) > -0.3).astype(np.float32)
        return (amp * np.sin(2 * np.pi * 190 * t) * env).astype(np.float32)

    sil = lambda s: np.zeros(int(s * SR), dtype=np.float32)  # noqa: E731
    mono = np.concatenate([sil(lead), burst(7), sil(pause), burst(7), sil(tail)])
    mono += rng.normal(0, noise, len(mono)).astype(np.float32)
    data = np.stack([mono, np.zeros_like(mono)], axis=1) if stereo_dead else mono
    sf.write(path, data, SR)
    return path


def test_check_reports_clear_errors(tmp_path: Path):
    assert any("not found" in e for e in check_voiceover(tmp_path / "nope.wav").errors)
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    assert any("empty" in e for e in check_voiceover(empty).errors)
    junk = tmp_path / "junk.wav"
    junk.write_text("not audio")
    assert any("could not be read" in e for e in check_voiceover(junk).errors)
    short = speechlike(tmp_path / "short.wav", pause=0.2)
    chk = check_voiceover(short, min_seconds=30)
    assert any("at least 30s" in e for e in chk.errors)
    silent = tmp_path / "silent.wav"
    sf.write(silent, np.zeros(SR * 20, dtype=np.float32), SR)
    assert any("silent" in e.lower() for e in check_voiceover(silent).errors)
    clipped = speechlike(tmp_path / "clip.wav", amp=4.0)
    assert any("clipping" in e.lower() for e in check_voiceover(clipped).errors)


def test_check_describes_a_usable_recording(tmp_path: Path):
    chk = check_voiceover(speechlike(tmp_path / "vo.wav", stereo_dead=True))
    assert chk.ok, chk.errors
    assert chk.dead_channel == 1 and any("silent" in w for w in chk.warnings)
    assert 0.8 <= chk.leading_silence <= 1.2 and chk.longest_pause >= 2.0
    assert chk.integrated_lufs is not None


def test_processing_is_gentle_and_optional(tmp_path: Path):
    src = speechlike(tmp_path / "vo.wav", stereo_dead=True)
    out = tmp_path / "out.wav"
    rep = process_voiceover(src, out, ProcessingOptions())
    after = check_voiceover(out)
    assert after.leading_silence <= 0.25 and after.trailing_silence <= 0.45  # edges trimmed
    assert after.longest_pause >= 2.0  # internal pause kept by default
    assert after.integrated_lufs is not None and abs(after.integrated_lufs - (-16)) < 1.5
    assert any("channel 1" in step for step in rep["steps"])
    tight = tmp_path / "tight.wav"
    process_voiceover(src, tight, ProcessingOptions(max_pause=0.8))
    assert check_voiceover(tight).longest_pause <= 0.9
    raw = tmp_path / "raw.wav"
    process_voiceover(src, raw, ProcessingOptions(trim=False, normalize=False))
    assert abs(sf.info(raw).duration - sf.info(src).duration) < 0.05


def test_processing_rejects_bad_input(tmp_path: Path):
    silent = tmp_path / "silent.wav"
    sf.write(silent, np.zeros(SR * 20, dtype=np.float32), SR)
    with pytest.raises(VoiceoverError):
        process_voiceover(silent, tmp_path / "o.wav", ProcessingOptions())


def test_record_command_uses_pulse():
    cmd = build_record_command(Path("x.wav"), device="alsa_input.foo", max_seconds=90)
    assert cmd[cmd.index("-f") + 1] == "pulse" and "alsa_input.foo" in cmd and "90" in cmd


def words_from(spec: list[tuple[str, float, float, int]]) -> list[CaptionWord]:
    return [CaptionWord(text=t, start=s, end=e, section_index=si) for t, s, e, si in spec]


def test_beats_prefer_sentences_and_pauses():
    ws = words_from(
        [
            ("One", 0.0, 0.3, 0),
            ("two.", 0.35, 0.7, 0),
            ("Three", 0.75, 1.0, 0),
            ("four,", 1.05, 1.3, 0),
            ("five", 1.9, 2.2, 0),
            ("six", 2.25, 2.5, 0),
            ("New", 2.6, 2.9, 1),
        ]
    )
    beats = {b.word_index: b for b in candidate_beats(ws)}
    assert beats[2].reason == "sentence" and beats[6].reason == "section"
    assert beats[4].reason.startswith("pause") and beats[4].strength > beats.get(4).strength - 1
    assert beats[2].time < ws[2].start  # cut lands just before the word


def test_segments_follow_target_pace():
    spec = []
    t = 0.0
    for i in range(60):
        text = f"w{i}." if i % 6 == 5 else f"w{i}"
        spec.append((text, t, t + 0.3, 0 if i < 30 else 1))
        t += 0.4
    segs = plan_segments(words_from(spec), t + 0.5, pace=3.0)
    lengths = [s.length for s in segs]
    assert all(seg.length >= 1.8 for seg in segs[:-1])
    assert 2.0 <= sum(lengths) / len(lengths) <= 4.5
    assert any(abs(s.start - 12.0) < 0.2 for s in segs)  # section start is always a cut


def test_emphasis_words():
    ws = words_from(
        [
            ("seven-billion", 0, 0.5, 0),
            ("parameters", 0.5, 1, 0),
            ("need", 1, 1.2, 0),
            ("fourteen", 1.2, 1.6, 0),
            ("gigabytes.", 1.6, 2, 0),
            ("3.5", 2, 2.4, 0),
        ]
    )
    assert emphasis_word_indices(ws) == [0, 3, 5]


def test_fill_cues_keeps_steps_readable():
    out = _fill_cues([100, None, 296], 0, 300, beat_frames=[150])
    assert out[1] == 150 and out[2] <= 270 and out == sorted(out)
    assert _fill_cues([None, None], 10, 200, [])[0] == 14


def test_says_value():
    assert _says_value("about fourteen gigabytes", 14)
    assert _says_value("roughly three and a half gigabytes", 3.5)
    assert not _says_value("sixteen-bit precision, two bytes", 14)


def test_caption_source_auto_switches_when_reading_differs():
    heard = [
        ("Seven", 0.3, 0.6),
        ("billion", 0.65, 0.9),
        ("weights", 0.95, 1.2),
        ("use", 1.25, 1.5),
        ("about", 1.55, 1.8),
        ("fourteen", 1.85, 2.2),
        ("gigs.", 2.25, 2.6),
        ("Share", 3.0, 3.3),
        ("it", 3.35, 3.5),
        ("with", 3.55, 3.7),
        ("your", 3.75, 3.9),
        ("friends.", 3.95, 4.4),
    ]
    tr = transcript_from(heard, duration=5.0)
    auto = build_caption_track(SCRIPT, tr, "auto")
    assert auto.words_source == "transcript" and [w.text for w in auto.words][-1] == "friends."
    assert auto.words[0].section_index == 0 and auto.words[-1].section_index == 1
    close = build_caption_track(SCRIPT, transcript_from(full_heard()), "auto")
    assert close.words_source == "script"


def test_manifest_cues_sfx_and_avatar_beats(tmp_path: Path):
    script, research, _ = parse_script_text(SCRIPT_TEXT)
    words = [w for s in script.sections for w in s.text.split()]
    heard = [(w, 0.2 + i * 0.32, 0.2 + i * 0.32 + 0.26) for i, w in enumerate(words)]
    dur = heard[-1][2] + 0.5
    track = build_caption_track(script, transcript_from(heard, duration=dur))
    m = build_manifest(
        job_id="j",
        script=script,
        track=track,
        research=research,
        narration=write_tone(tmp_path / "n.wav", dur),
        audio_duration=dur,
    )
    from reelforge.visuals.scene_manifest import validate_manifest

    assert validate_manifest(m) == []
    stat = next(s for s in m.scenes if s.type == "stat")
    count = next(c for c in stat.cues if c.kind == "count")
    fourteen = next(w for w in track.words if w.text == "fourteen")
    assert abs(count.frame - round(fourteen.start * 30)) <= 1  # counts up as "fourteen" is spoken
    diagram = next(s for s in m.scenes if s.type == "diagram")
    assert [c.index for c in diagram.cues if c.kind == "item"] == [0, 1, 2]
    assert {s.layout for s in m.scenes} == {"center", "focus"}
    assert all(c.kind in ("whoosh", "tick") for c in m.sfx_cues) and any(c.kind == "tick" for c in m.sfx_cues)
    gaps = [b.frame - a.frame for a, b in zip(m.sfx_cues, m.sfx_cues[1:], strict=False) if a.kind == b.kind == "whoosh"]
    assert all(g >= 75 for g in gaps)
    assert m.avatar.nod_frames and m.avatar.emphasis_frames
    assert any(w.emphasis for g in m.caption_groups for w in g.words)


def test_exact_length_mux_and_sync_checks(tmp_path: Path):
    from reelforge.rendering.ffmpeg import build_mix_command

    frames = 150
    v = tmp_path / "v.mp4"
    make_video(v, frames / 30, size="360x640", frames=frames)
    voice = tmp_path / "voice.wav"
    sig = np.zeros(int(5 * SR), dtype=np.float32)
    t = np.arange(int(3.5 * SR)) / SR
    sig[int(0.5 * SR) : int(0.5 * SR) + len(t)] = 0.3 * np.sin(2 * np.pi * 200 * t)
    sf.write(voice, sig, SR)
    mix = tmp_path / "mix.wav"
    subprocess.run(build_mix_command(narration=voice, output=mix, duration=frames / 30), check=True)
    assert abs(sf.info(mix).duration - frames / 30) < 0.002  # padded back after loudnorm
    out = tmp_path / "o.mp4"
    subprocess.run(build_mux_command(video=v, audio=mix, output=out, duration=frames / 30), check=True)
    assert check_render_completion(out, frames)["frames"] == frames
    assert check_render_completion(out, frames + 10)["errors"]

    from reelforge.visuals.scene_manifest import AvatarTrack, CaptionGroupF, CaptionWordF, Scene, SceneManifest

    def manifest(first_word_frame: int) -> SceneManifest:
        w = CaptionWordF(text="hi", start_frame=first_word_frame, end_frame=first_word_frame + 20)
        return SceneManifest(
            job_id="t",
            title="t",
            duration_frames=frames,
            scenes=[Scene(id="s1", type="hook", start_frame=0, end_frame=frames, headline="x")],
            caption_groups=[CaptionGroupF(start_frame=w.start_frame, end_frame=w.end_frame, words=[w])],
            avatar=AvatarTrack(mouth_open=[0.0] * frames, visemes=["rest"] * frames, blink_frames=[]),
        )

    ok = caption_sync_report(out, manifest(15))  # narration starts at 0.5 s = frame 15
    assert not ok["errors"] and abs(ok["first_word_offset_s"]) < 0.1
    late = caption_sync_report(out, manifest(45))
    assert any("narration onset" in e for e in late["errors"])
    assert even_dim(1080 / 3) == 360 and even_dim(1920 / 3) == 640
