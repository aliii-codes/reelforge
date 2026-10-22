"""Editing grammar: anchored beats, real terminal casts, evidence fallbacks, director rules, sound sync."""

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from reelforge.captions.alignment import build_caption_track
from reelforge.rendering import sound
from reelforge.scripting.manual import ScriptParseError, parse_script_text
from reelforge.tests.conftest import write_tone
from reelforge.tests.test_audio_captions import transcript_from
from reelforge.visuals import director
from reelforge.visuals.scene_manifest import validate_manifest
from reelforge.visuals.scene_planner import build_manifest
from reelforge.visuals.terminal_capture import capture, load_cast

CAST = {
    "kind": "reelforge-terminal-cast",
    "version": 1,
    "recorded_at": "2026-10-22T11:47:15+00:00",
    "host": "Linux x86_64",
    "cwd": "demo",
    "steps": [
        {
            "command": "python3 inspect_weights.py model.safetensors",
            "output": ["params: 494,032,768", "dtype: BF16  (2 bytes each)"],
            "exit_code": 0,
            "seconds": 0.05,
        },
        {
            "command": "python3 -c \"print(7e9 * 2 / 1e9, 'GB')\"",
            "output": ["14.0 GB"],
            "exit_code": 0,
            "seconds": 0.03,
        },
    ],
}


def script_text(tmp_path: Path) -> str:
    (tmp_path / "casts").mkdir(exist_ok=True)
    (tmp_path / "casts" / "w.json").write_text(json.dumps(CAST))
    return """# title: Edit test
[hook]
A seven-billion-parameter model runs on a laptop. No data center required.
> scene: kinetic
> at: No data center | scene: meme | top: Data center? | bottom: Not required

[number]
Every parameter takes two bytes. So seven billion parameters need fourteen gigabytes.
> scene: terminal | cast: casts/w.json | headline: Real file | quote: 2 bytes each
> at: So seven billion | scene: stat | value: 14 | suffix: GB | label: at 16-bit

[beat]
The trick is quantization. You store weights with fewer bits, now it needs three and a half gigabytes.
> scene: kinetic
> at: You store weights | scene: evidence | source: https://example.org/q | quote: "fewer bits | less memory"
> at: now it needs | scene: bars | headline: 4x smaller | items: 16-bit = 14 ; 4-bit = 3.5 | suffix: GB

[twist]
But here's the catch. Squeeze too hard and quality drops.
> scene: twist | kicker: BUT…

[cta]
Send this to a friend who codes.
"""


def build(tmp_path: Path, evidence=None):
    script, research, _ = parse_script_text(script_text(tmp_path), base_dir=tmp_path)
    words = [w for s in script.sections for w in s.text.split()]
    heard = [(w, 0.2 + i * 0.4, 0.2 + i * 0.4 + 0.32) for i, w in enumerate(words)]
    dur = heard[-1][2] + 0.5
    track = build_caption_track(script, transcript_from(heard, duration=dur))
    m = build_manifest(
        job_id="t",
        script=script,
        track=track,
        research=research,
        narration=write_tone(tmp_path / "n.wav", dur),
        audio_duration=dur,
        evidence=evidence,
    )
    return script, track, m


def test_parser_beats_casts_and_quotes(tmp_path: Path):
    script, _, _ = parse_script_text(script_text(tmp_path), base_dir=tmp_path)
    hook, number, beat = script.sections[:3]
    assert (
        hook.visual.scene == "kinetic" and hook.beats[0].at == "No data center" and hook.beats[0].top == "Data center?"
    )
    assert (
        number.visual.cast is not None and number.visual.cast["steps"][0]["output"][1] == "dtype: BF16  (2 bytes each)"
    )  # embedded, not a path
    assert beat.beats[0].quote == "fewer bits | less memory"  # quoted value keeps its '|'
    with pytest.raises(ScriptParseError, match="terminal cast not found"):
        parse_script_text("[hook]\nHello there friend.\n> scene: terminal | cast: missing.json", base_dir=tmp_path)


def test_anchored_cuts_and_scene_types(tmp_path: Path):
    _, track, m = build(tmp_path)
    assert validate_manifest(m) == []
    types = [s.type for s in m.scenes]
    assert types[:4] == ["kinetic", "meme", "terminal", "stat"]
    meme = m.scenes[1]
    no_word = next(w for w in track.words if w.text == "No")
    assert abs(meme.start_frame - round(no_word.start * 30)) <= 3  # cut lands on the anchor phrase
    assert meme.headline == "Data center?" and meme.subtext == "Not required"


def test_terminal_scene_replays_the_real_cast(tmp_path: Path):
    _, _, m = build(tmp_path)
    term = next(s for s in m.scenes if s.type == "terminal")
    assert term.meta["cast"]["steps"] == CAST["steps"]  # exact recorded output, nothing invented
    t = term.meta["timing"]
    assert t[0]["type_start"] >= term.start_frame and t[-1]["out_at"] < term.end_frame
    assert all(a["out_at"] <= b["type_start"] for a, b in zip(t, t[1:], strict=False))
    assert any(c.kind == "highlight" for c in term.cues)  # "2 bytes each" line is emphasised
    keys = [c for c in m.sfx_cues if c.kind == "keys"]
    assert [k.frame for k in keys] == [x["type_start"] for x in t]  # key clicks only while typing


def test_terminal_without_cast_is_never_faked(tmp_path: Path):
    script, research, _ = parse_script_text(
        "[hook]\nA model runs on a laptop CPU today, no data center needed.\n> scene: terminal"
    )
    words = script.sections[0].text.split()
    heard = [(w, 0.2 + i * 0.4, 0.5 + i * 0.4) for i, w in enumerate(words)]
    track = build_caption_track(script, transcript_from(heard, duration=heard[-1][2] + 0.5))
    m = build_manifest(
        job_id="t",
        script=script,
        track=track,
        research=research,
        narration=write_tone(tmp_path / "n.wav", 6),
        audio_duration=heard[-1][2] + 0.5,
    )
    assert all(s.type != "terminal" for s in m.scenes)


def test_evidence_uses_screenshot_or_honest_fallback(tmp_path: Path):
    _, _, failed = build(tmp_path, evidence=lambda url, quote: {"ok": False, "error": "offline"})
    ev = next(s for s in failed.scenes if s.type == "evidence")
    assert ev.asset is None and ev.meta["fallback"] and ev.meta["quote"] == "fewer bits | less memory"
    assert not any(c.kind == "shutter" for c in failed.sfx_cues)
    shot = {
        "ok": True,
        "asset": "assets/e.png",
        "rects": [{"x": 1, "y": 2, "w": 3, "h": 4}],
        "width": 1080,
        "height": 1920,
        "captured_at": "2026-10-22T00:00:00Z",
        "title": "t",
    }
    _, _, ok = build(tmp_path, evidence=lambda url, quote: shot)
    ev2 = next(s for s in ok.scenes if s.type == "evidence")
    assert ev2.asset == "assets/e.png" and ev2.meta["rects"] and ev2.avatar == "hidden"
    assert any(c.kind == "shutter" and c.frame >= ev2.start_frame for c in ok.sfx_cues)


def test_director_rules(tmp_path: Path):
    _, _, m = build(tmp_path)
    for a, b in zip(m.scenes, m.scenes[1:], strict=False):
        if a.section_index == b.section_index:
            assert b.transition == "cut"
        else:
            assert b.transition in ("whip", "zoom", "flash")
            if b.type in director.IMPACT_TYPES:
                assert b.transition == "flash"
    fx = [s.transition for s in m.scenes if s.transition in ("whip", "zoom")]
    assert all(x != y for x, y in zip(fx, fx[1:], strict=False))  # never the same move twice in a row
    for s in m.scenes:
        if s.type in ("terminal", "evidence", "bars", "kinetic"):
            assert s.avatar == "hidden"
        assert s.hide_captions == (s.type in ("kinetic", "meme"))
    twist = next(s for s in m.scenes if s.type == "twist")
    riser = next(c for c in m.sfx_cues if c.kind == "riser")
    assert riser.frame + riser.duration_frames == twist.start_frame  # riser ends on the cut
    assert [c.kind for c in m.music_cues] == ["drop", "return"] and m.music_cues[0].frame <= twist.start_frame


def test_real_capture_sanitises_home(tmp_path: Path):
    cast = capture(["echo hello from $HOME", "exit 3"], tmp_path)
    assert cast.steps[0].output == ["hello from ~"] and "~" in cast.steps[0].output[0]
    assert cast.steps[1].exit_code == 3 and cast.cwd == tmp_path.name
    p = tmp_path / "c.json"
    p.write_text(cast.model_dump_json())
    assert load_cast(p).steps[0].command == "echo hello from $HOME"


def test_music_drop_and_all_sfx(tmp_path: Path):
    sound.write_bed(tmp_path / "bed.wav", 6.0, drops=[(2.0, 3.0)])
    bed, sr = sf.read(tmp_path / "bed.wav")
    mid = bed[int(2.2 * sr) : int(2.8 * sr)]
    assert np.max(np.abs(mid)) < 1e-3 and np.max(np.abs(bed[int(1.0 * sr) : int(1.5 * sr)])) > 0.01
    cues = [
        (0.5, "whoosh", 0),
        (1.0, "impact", 0),
        (1.5, "riser", 0.8),
        (2.5, "pop", 0),
        (3.0, "keys", 0.6),
        (4.0, "shutter", 0),
    ]
    sound.write_sfx_track(tmp_path / "sfx.wav", 6.0, cues)
    sfx, sr = sf.read(tmp_path / "sfx.wav")
    for t, _, _ in cues:
        assert np.max(np.abs(sfx[int(t * sr) : int((t + 0.3) * sr)])) > 0.02
