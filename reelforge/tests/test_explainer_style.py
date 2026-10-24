"""Explainer style: semantic visual choice, chapters, speech-bubble captions, sparse sound, hashes."""

from pathlib import Path

from reelforge.captions.alignment import CaptionWord, build_caption_track
from reelforge.schemas import ScriptVersion
from reelforge.scripting.manual import parse_script_text
from reelforge.tests.conftest import write_tone
from reelforge.tests.test_audio_captions import transcript_from
from reelforge.visuals import explainer
from reelforge.visuals.scene_manifest import validate_manifest
from reelforge.visuals.scene_planner import build_manifest

SCRIPT = """# title: How AI learns
[hook]
An AI model starts out knowing absolutely nothing. So how does it learn?

[explain]
A model is a neural network: layers of simple units connected by weights.
> scene: diagram | headline: A neural network | items: Input ; Layer 1 ; Layer 2 ; Output

[explain]
First, it needs data. Training feeds it text, images, and examples from the internet.
> step: data

[explain]
Second, it guesses. The model predicts the next word in a sentence.
> step: guess | scene: diagram | items: The cat ; sat on the ; mat

[explain]
Third, it adjusts. It nudges every weight a tiny bit to be less wrong.
> step: adjust

[number]
GPT-3 has one hundred seventy-five billion weights.
> scene: stat | value: 175 | suffix: B | label: weights in GPT-3

[analogy]
It's like learning darts blindfolded. Every throw lands a little closer.
> left: Darts: throw, miss, aim | right: AI: guess, error, nudge

[twist]
But here's the catch. It learns the mistakes in its data too.

[payoff]
So a model doesn't memorize a textbook. It learns patterns.

[cta]
Follow for more AI, explained simply.
"""


def build(tmp_path: Path, text: str = SCRIPT, style: str = "explainer"):
    script, research, _ = parse_script_text(text)
    words = [w for s in script.sections for w in s.text.split()]
    heard = [(w, 0.2 + i * 0.36, 0.2 + i * 0.36 + 0.3) for i, w in enumerate(words)]
    dur = heard[-1][2] + 0.5
    track = build_caption_track(script, transcript_from(heard, duration=dur))
    m = build_manifest(
        job_id="t", script=script, track=track, research=research,
        narration=write_tone(tmp_path / "n.wav", dur), audio_duration=dur, handle="@me", style=style,
    )  # fmt: skip
    return script, track, m


def visual_for(m, phrase: str) -> str:
    """Visual of the first beat whose caption words include `phrase`'s first word."""
    want = phrase.lower().split()
    ws = [w for g in m.caption_groups for w in g.words]
    texts = [w.text.lower().strip(".,:!?") for w in ws]
    for k in range(len(texts)):
        if texts[k : k + len(want)] == want:
            f = ws[k].start_frame
            return next(s.visual for s in m.scenes if s.start_frame <= f < s.end_frame)
    raise AssertionError(f"phrase not spoken: {phrase}")


def test_visuals_follow_what_is_said(tmp_path: Path):
    _, _, m = build(tmp_path)
    assert validate_manifest(m) == []
    assert m.style == "explainer"
    assert m.scenes[0].visual == "hook" and m.scenes[-1].visual == "cta"
    assert visual_for(m, "neural network") == "network"
    assert visual_for(m, "it needs data") == "datastream"
    assert visual_for(m, "predicts the next") == "chain"  # short tokens -> horizontal chain
    assert visual_for(m, "nudges every weight") == "dials"
    assert visual_for(m, "seventy-five") == "stat"
    assert visual_for(m, "darts") == "compare"
    assert visual_for(m, "the catch") == "twist"
    # never the same generic card three beats in a row
    vs = [s.visual for s in m.scenes]
    assert not any(a == b == c and a in ("card", "keyword") for a, b, c in zip(vs, vs[1:], vs[2:], strict=False))


def test_chapters_advance_and_presenter_poses(tmp_path: Path):
    _, _, m = build(tmp_path)
    assert m.chapters == ["data", "guess", "adjust"]
    seq = [s.chapter for s in m.scenes if s.chapter is not None]
    assert seq == sorted(seq) and seq[0] == 0 and seq[-1] == len(m.chapters)  # ends "all done"
    assert any(s.label.startswith("step 2: guess") for s in m.scenes)
    assert m.scenes[0].chapter is None and m.scenes[-1].chapter is None  # no tabs on hook/CTA
    assert {s.pose for s in m.scenes} >= {"wave", "point"}
    assert all(s.avatar == "corner" for s in m.scenes if s.visual not in ("hook", "cta", "reaction"))


def test_bubble_captions_are_phrases_with_one_keyword(tmp_path: Path):
    _, track, m = build(tmp_path)
    groups = m.caption_groups
    assert len(groups) < len(track.groups)  # phrase-level, fewer flashes than 3-word groups
    assert all(len(g.words) <= 6 for g in groups)
    assert all(sum(w.emphasis for w in g.words) <= 1 for g in groups)
    assert sum(len(g.words) == 1 for g in groups) <= 2  # orphans merged
    assert not any(w.text.lower() == "here's" and w.emphasis for g in groups for w in g.words)


def test_sound_is_sparse(tmp_path: Path):
    _, _, m = build(tmp_path)
    frames = [c.frame for c in m.sfx_cues]
    assert all(b - a >= 18 for a, b in zip(frames, frames[1:], strict=False))
    assert len(m.sfx_cues) <= len(m.scenes) + 4
    assert any(c.kind == "riser" for c in m.sfx_cues) and {c.kind for c in m.music_cues} == {"drop", "return"}


def test_creator_style_is_unchanged(tmp_path: Path):
    _, _, m = build(tmp_path, style="creator")
    assert m.style == "creator" and all(s.visual == "" for s in m.scenes)
    assert validate_manifest(m) == []


def test_bubble_groups_merge_lone_words():
    ws = [
        CaptionWord(text=t, start=i * 0.3, end=i * 0.3 + 0.25, section_index=0)
        for i, t in enumerate("every parameter takes two bytes.".split())
    ]
    assert explainer.bubble_groups(ws) == [[0, 1, 2, 3, 4]]


def test_new_hint_keys_keep_old_script_hashes():
    script, research, _ = parse_script_text("[hook]\nHello there friend.\n")
    import hashlib
    import json

    sv = ScriptVersion(version=1, origin="manual", script=script, research=research)
    h = sv.content_hash()
    # the hash the code produced before tag/visual/step existed
    old = sv.script.model_dump(mode="json")
    for sec in old["sections"]:
        for k in ("tag", "visual", "step"):
            sec["visual"].pop(k)
    payload = json.dumps({"script": old, "research": sv.research.model_dump(mode="json")}, sort_keys=True)
    assert h == hashlib.sha256(payload.encode()).hexdigest()
    sv2 = sv.model_copy(deep=True)
    sv2.script.sections[0].visual.step = "data"
    assert sv2.content_hash() != h  # a set key is covered by the hash


def test_rich_diagrams_are_not_repeated_endlessly(tmp_path: Path):
    text = SCRIPT.replace(
        "[payoff]\nSo a model doesn't memorize a textbook. It learns patterns.",
        "[payoff]\nSo training is just tuning knobs. Adjusting, adjusting, adjusting.\n\n"
        "[beat]\nAnd then it keeps adjusting the same knobs again.",
    )
    _, _, m = build(tmp_path, text)
    vs = [s.visual for s in m.scenes]
    runs = sum(1 for i, v in enumerate(vs) if v == "dials" and (i == 0 or vs[i - 1] != "dials"))
    assert runs <= explainer.MAX_RUNS
    assert validate_manifest(m) == []
