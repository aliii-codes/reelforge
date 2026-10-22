from pathlib import Path

import pytest

from reelforge.captions.alignment import build_caption_track
from reelforge.export import package as pkg
from reelforge.rendering.ffmpeg import build_mix_command, build_mux_command, probe
from reelforge.rendering.remotion import RendererUnavailable, build_render_command, check_renderer
from reelforge.rendering.validation import check_stream_info, validate_video
from reelforge.schemas import ResearchBundle
from reelforge.scripting.manual import parse_script_text
from reelforge.tests.conftest import SCRIPT_TEXT, make_video, write_tone
from reelforge.tests.test_audio_captions import transcript_from
from reelforge.visuals.scene_manifest import validate_manifest
from reelforge.visuals.scene_planner import build_manifest, find_number, short_headline


def test_render_command_construction(tmp_path: Path):
    cmd = build_render_command(
        props=tmp_path / "m.json",
        public_dir=tmp_path,
        output=tmp_path / "o.mp4",
        scale=0.5,
        concurrency=2,
        frames="0-89",
    )
    assert cmd[:6] == ["npx", "remotion", "render", "src/index.ts", "Reel", str(tmp_path / "o.mp4")]
    assert "--muted" in cmd and "--codec=h264" in cmd and "--scale=0.5" in cmd and "--frames=0-89" in cmd
    assert "--pixel-format=yuv420p" in cmd and "--concurrency=2" in cmd
    full = build_render_command(props=tmp_path / "m.json", public_dir=tmp_path, output=tmp_path / "o.mp4")
    assert not any(a.startswith("--scale") or a.startswith("--frames") for a in full)
    with pytest.raises(ValueError):
        build_render_command(props=tmp_path, public_dir=tmp_path, output=tmp_path, frames="0-9; rm -rf /")


def test_mix_and_mux_commands(tmp_path: Path):
    n = tmp_path / "n.wav"
    cmd = build_mix_command(
        narration=n, output=tmp_path / "m.wav", duration=50.0, music=tmp_path / "b.wav", sfx=tmp_path / "s.wav"
    )
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "sidechaincompress" in fc and "amix=inputs=3" in fc and "loudnorm=I=-14" in fc
    solo = build_mix_command(narration=n, output=tmp_path / "m.wav", duration=50.0)
    assert "amix" not in solo[solo.index("-filter_complex") + 1]
    mux = build_mux_command(video=tmp_path / "v.mp4", audio=n, output=tmp_path / "o.mp4")
    assert mux[mux.index("-c:v") + 1] == "copy" and mux[mux.index("-c:a") + 1] == "aac" and "+faststart" in mux


def test_renderer_missing_is_reported(tmp_path: Path):
    with pytest.raises(RendererUnavailable):
        check_renderer(tmp_path)


def test_stream_info_checks():
    info = {
        "format": {"format_name": "mov,mp4,m4a", "duration": "50.0", "size": "100"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1080,
                "height": 1920,
                "avg_frame_rate": "30/1",
                "pix_fmt": "yuv420p",
                "duration": "50.0",
            },
            {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "channels": 2, "duration": "50.0"},
        ],
    }
    errors, warnings, summary = check_stream_info(info, expected_duration=50.0)
    assert not errors and summary["fps"] == 30
    info["streams"][0].update(width=720, codec_name="hevc", avg_frame_rate="25/1")
    info["streams"].pop()
    errors, _, _ = check_stream_info(info, expected_duration=40.0)
    joined = " ".join(errors)
    for needle in ("hevc", "720x1920", "25.000", "no audio", "duration"):
        assert needle in joined


@pytest.mark.slow
def test_validate_real_mp4(tmp_path: Path):
    v = tmp_path / "v.mp4"
    make_video(v, 2, size="270x480")
    a = write_tone(tmp_path / "a.wav", 2)
    out = tmp_path / "o.mp4"
    import subprocess

    subprocess.run(build_mux_command(video=v, audio=a, output=out), check=True)
    rep = validate_video(out, expected_duration=2.0, width=270, height=480)
    assert rep["ok"], rep["errors"]
    assert probe(out)["streams"][1]["codec_name"] == "aac"


def test_planner_and_manifest_validation(tmp_path: Path):
    script, research, _ = parse_script_text(SCRIPT_TEXT)
    words = [w for s in script.sections for w in s.text.split()]
    heard = [(w, 0.2 + i * 0.4, 0.2 + i * 0.4 + 0.35) for i, w in enumerate(words)]
    dur = heard[-1][2] + 0.5
    track = build_caption_track(script, transcript_from(heard, duration=dur))
    narration = write_tone(tmp_path / "n.wav", dur)
    m = build_manifest(
        job_id="j", script=script, track=track, research=research, narration=narration, audio_duration=dur
    )
    assert validate_manifest(m) == []
    types = [s.type for s in m.scenes]
    assert types[0] == "hook" and "stat" in types and "diagram" in types and types[-1] == "cta"
    stat = next(s for s in m.scenes if s.type == "stat")
    assert stat.stat and stat.stat.value == 14 and stat.stat.suffix == "GB"
    assert m.scenes[0].headline == "A 7B model on a laptop"
    assert len(m.avatar.mouth_open) == m.duration_frames and max(m.avatar.mouth_open) > 0.3
    assert m.cover_title
    broken = m.model_copy(deep=True)
    broken.scenes[1].start_frame += 3
    assert any("gap/overlap" in e for e in validate_manifest(broken))


def test_planner_heuristics():
    assert find_number("needs about 14 gigabytes").suffix == "GB"
    st = find_number("roughly three and a half gigabytes")
    assert st.value == 3.5 and st.suffix == "GB"
    assert find_number("no numbers here") is None
    assert (
        len(short_headline("Here's how it actually works. A model is a giant list of numbers called weights.").split())
        <= 6
    )


def test_output_path_safety(tmp_path: Path):
    assert pkg.safe_child(tmp_path, "job1") == (tmp_path / "job1").resolve()
    with pytest.raises(pkg.UnsafeOutputPath):
        pkg.safe_child(tmp_path, "../escape")


def test_package_completeness_and_export(tmp_path: Path):
    job = tmp_path / "job"
    job.mkdir()
    check = pkg.check_package(job)
    assert not check["complete"] and "final_reel.mp4" in check["missing"]
    for name in pkg.PACKAGE_FILES:
        (job / name).write_text("x")
    (job / "hashtags.txt").write_text("#a #b #c #d #e\n")
    assert pkg.check_package(job)["complete"]
    (job / "hashtags.txt").write_text("#a #b\n")
    assert not pkg.check_package(job)["complete"]
    dest = tmp_path / "exports"
    target = pkg.export_copy(job, dest)
    assert (target / "final_reel.mp4").exists()
    with pytest.raises(FileExistsError):
        pkg.export_copy(job, dest)


def test_hashtags_and_caption():
    script, research, _ = parse_script_text(SCRIPT_TEXT)
    tags = pkg.make_hashtags(script)
    assert len(tags) == 5 and all(t.startswith("#") for t in tags)
    script2 = script.model_copy(update={"hashtags": []})
    assert len(pkg.make_hashtags(script2)) == 5
    cap = pkg.make_caption(script, ResearchBundle(), tags)
    assert "REVIEW BEFORE POSTING" in cap and tags[0] in cap


def test_headlines_are_complete_phrases():
    from reelforge.visuals.scene_planner import compact_numbers, source_label_text

    assert (
        short_headline("Now the same model needs roughly three and a half gigabytes.", 8)
        == "The same model needs roughly 3.5 GB"
    )
    h = short_headline("To use it, your computer has to hold those numbers in memory.", 8)
    assert h == "Your computer has to hold those numbers in memory"
    assert compact_numbers("seven billion parameters need fourteen gigabytes") == "7 billion parameters need 14 GB"
    assert (
        source_label_text("https://raw.githubusercontent.com/ggml-org/llama.cpp/master/README.md", "x")
        == "github.com/ggml-org/llama.cpp"
    )
