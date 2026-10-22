"""Measure and compare two rendered ReelForge jobs (e.g. draft 1 vs the voice-over draft).

    python scripts/compare_drafts.py output/<job_a> output/<job_b> [--out docs/draft-comparison.json]

All numbers come from files in the job folders (scene_manifest.json, captions.json, the final or
preview MP4) and FFmpeg/ffprobe measurements - nothing is estimated by hand.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
from collections import Counter
from pathlib import Path

from reelforge.rendering.validation import audio_onset_and_end, check_render_completion

FPS = 30


def _video(job: Path) -> Path:
    for name in ("final_reel.mp4", "preview.mp4"):
        if (job / name).exists():
            return job / name
    raise SystemExit(f"{job} has no final_reel.mp4 or preview.mp4")


def lufs(path: Path) -> float | None:
    p = subprocess.run(
        ["ffmpeg", "-v", "info", "-nostdin", "-i", str(path), "-af", "ebur128=framelog=quiet", "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", p.stderr)
    return float(m[-1]) if m else None


def metrics(job: Path) -> dict:
    m = json.loads((job / "scene_manifest.json").read_text())
    cap = json.loads((job / "captions.json").read_text())
    video = _video(job)
    scenes = m["scenes"]
    dur_s = m["duration_frames"] / FPS
    lengths = [(s["end_frame"] - s["start_frame"]) / FPS for s in scenes]
    cuts = [s["start_frame"] for s in scenes[1:]]
    cues = [c for s in scenes for c in s.get("cues", [])]
    content_cues = [c for c in cues if c["kind"] in ("item", "count", "word", "line")]
    # a cut is "on a beat" if it lands within 0.15 s before a spoken word's onset
    onsets = [w["start"] for w in cap["words"]]
    on_beat = sum(1 for f in cuts if any(0 <= o - f / FPS <= 0.15 for o in onsets))
    sfx = m.get("sfx_cues") or [{"frame": f, "kind": "whoosh"} for f in cuts]  # v1 put a whoosh on every cut
    layouts = [s.get("layout", "center") for s in scenes]
    expressions = [s["expression"] for s in scenes]
    first_word = m["caption_groups"][0]["words"][0]["start_frame"] / FPS
    onset, _ = audio_onset_and_end(video)
    av = m["avatar"]
    return {
        "job": job.name,
        "video": video.name,
        "duration_s": round(dur_s, 2),
        "frames_manifest": m["duration_frames"],
        "frames_encoded": check_render_completion(video, m["duration_frames"])["frames"],
        "scenes": len(scenes),
        "scene_types": sorted({s["type"] for s in scenes}),
        "scene_len_mean_s": round(statistics.mean(lengths), 2),
        "scene_len_median_s": round(statistics.median(lengths), 2),
        "scene_len_max_s": round(max(lengths), 2),
        "scenes_over_6s": sum(1 for x in lengths if x > 6),
        "cuts_on_word_onset_pct": round(100 * on_beat / max(len(cuts), 1), 1),
        "word_synced_visual_cues": len(content_cues),
        "visual_events_per_min": round((len(cuts) + len(content_cues)) / dur_s * 60, 1),
        "avatar_layout_changes": sum(1 for a, b in zip(layouts, layouts[1:], strict=False) if a != b),
        "avatar_expression_changes": sum(1 for a, b in zip(expressions, expressions[1:], strict=False) if a != b),
        "avatar_gestures": len(av.get("emphasis_frames", [])) + len(av.get("nod_frames", [])),
        "sfx_whooshes": sum(1 for c in sfx if c["kind"] == "whoosh"),
        "sfx_ticks": sum(1 for c in sfx if c["kind"] == "tick"),
        "transitions": dict(Counter(s.get("transition", "fade") for s in scenes[1:])),
        "backgrounds": len({s.get("background", "grid") for s in scenes}),
        "avatar_on_screen_pct": round(
            100
            * sum(s["end_frame"] - s["start_frame"] for s in scenes if s.get("avatar", "center") != "hidden")
            / m["duration_frames"],
            1,
        ),
        "real_footage_s": round(
            sum(
                s["end_frame"] - s["start_frame"]
                for s in scenes
                if s["type"] == "terminal" or (s["type"] == "evidence" and s.get("asset"))
            )
            / FPS,
            1,
        ),
        "text_duplicated_on_screen_s": round(
            sum(
                s["end_frame"] - s["start_frame"]
                for s in scenes
                if s["type"] == "reveal" and not s.get("hide_captions")
            )
            / FPS,
            1,
        ),
        "captions_hidden_s": round(
            sum(s["end_frame"] - s["start_frame"] for s in scenes if s.get("hide_captions")) / FPS, 1
        ),
        "sfx_kinds": dict(Counter(c["kind"] for c in sfx)),
        "music_drops": sum(1 for c in m.get("music_cues", []) if c["kind"] == "drop"),
        "caption_words": len(cap["words"]),
        "caption_words_interpolated": cap.get("approximate_words", 0),
        "caption_source": cap.get("words_source", "script"),
        "first_caption_vs_audio_onset_s": round(first_word - onset, 3) if onset is not None else None,
        "integrated_lufs": lufs(video),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("a", type=Path)
    ap.add_argument("b", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    a, b = metrics(args.a), metrics(args.b)
    width = max(len(k) for k in a)
    print(f"{'metric'.ljust(width)}  {'A':>40}  {'B':>40}")
    for k in a:
        print(f"{k.ljust(width)}  {str(a[k])[:40]:>40}  {str(b[k])[:40]:>40}")
    if args.out:
        args.out.write_text(json.dumps({"a": a, "b": b}, indent=2))
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
