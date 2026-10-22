"""The JSON contract between Python and the Remotion renderer (mirrors renderer/src/types.ts)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from reelforge.schemas import Expression, SceneType

Viseme = Literal["rest", "mbp", "ee", "aa", "oo", "fv"]
Transition = Literal["fade", "slide", "pop", "wipe", "cut", "whip", "zoom", "flash"]
Background = Literal["grid", "glow", "accent", "terminal", "paper"]
Camera = Literal["none", "push", "drift", "punch", "track"]
AvatarMode = Literal["hidden", "center", "corner", "reaction"]
SfxKind = Literal["whoosh", "tick", "impact", "riser", "pop", "keys", "shutter"]
Layout = Literal["center", "focus"]  # focus: bigger graphics panel, small avatar bottom-left
CueKind = Literal["emphasis", "item", "count", "word", "line", "output", "highlight"]
ICONS = {"chip", "brain", "phone", "bolt", "book", "chart", "bulb", "warning", "share", "layers", "globe", "scale"}

# Layout constants shared with the renderer (1080x1920 canvas).
SAFE_TOP = 200  # platform header
SAFE_BOTTOM = 1920 - 380  # captions/description/buttons overlay on Reels & Shorts


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StatData(_M):
    value: float
    decimals: int = Field(default=0, ge=0, le=2)
    prefix: str = Field(default="", max_length=3)
    suffix: str = Field(default="", max_length=6)
    label: str = Field(default="", max_length=48)


class Cue(_M):
    """A timed visual change inside a scene, at the frame the related word is spoken."""

    frame: int = Field(ge=0)  # absolute frame
    kind: CueKind
    index: int = 0  # item/line/word index the cue applies to


class SfxCue(_M):
    frame: int = Field(ge=0)
    kind: SfxKind
    duration_frames: int = Field(default=0, ge=0)  # for sustained sounds (key clicks while typing)


class MusicCue(_M):
    """Bed automation: drop the music out (e.g. for a dramatic beat) and bring it back."""

    frame: int = Field(ge=0)
    kind: Literal["drop", "return"]


class Scene(_M):
    id: str
    type: SceneType
    start_frame: int = Field(ge=0)
    end_frame: int
    headline: str = Field(max_length=60)
    subtext: str = Field(default="", max_length=70)
    emphasis: list[str] = Field(default_factory=list)
    items: list[str] = Field(default_factory=list, max_length=4)
    left: str | None = Field(default=None, max_length=60)
    right: str | None = Field(default=None, max_length=60)
    stat: StatData | None = None
    expression: Expression = "neutral"
    transition: Transition = "fade"
    source_label: str | None = None
    icon: str = "chip"
    layout: Layout = "center"
    background: Background = "grid"
    camera: Camera = "none"
    avatar: AvatarMode = "center"
    hide_captions: bool = False  # e.g. kinetic typography already shows the spoken words
    asset: str | None = None  # file in the job's public dir (evidence screenshot)
    meta: dict = Field(default_factory=dict)  # per-type data: terminal cast/timing, evidence rects, bars
    cues: list[Cue] = Field(default_factory=list)
    lines: list[str] = Field(default_factory=list, max_length=6)  # demo scene: terminal/output lines
    section_index: int | None = Field(default=None, exclude=True)


class CaptionWordF(_M):
    text: str
    start_frame: int
    end_frame: int
    emphasis: bool = False


class CaptionGroupF(_M):
    start_frame: int
    end_frame: int
    words: list[CaptionWordF] = Field(min_length=1)


class Theme(_M):
    bg_from: str = "#1B1446"
    bg_to: str = "#07061A"
    accent: str = "#4DF0C8"
    accent2: str = "#FF6B9A"
    text: str = "#FFFFFF"
    muted: str = "#C4C1E3"
    panel: str = "rgba(255,255,255,0.07)"
    font_family: str = "Lato, 'DejaVu Sans', sans-serif"


class CaptionStyle(_M):
    font_size: int = Field(default=76, ge=40, le=110)
    center_y: int = 1430
    highlight: str = "#FFE14D"
    uppercase: bool = False
    max_width: int = Field(default=880, le=940)


class AvatarTrack(_M):
    mouth_open: list[float]
    visemes: list[Viseme]
    blink_frames: list[int]
    emphasis_frames: list[int] = Field(default_factory=list)  # brow raise + small head tilt
    nod_frames: list[int] = Field(default_factory=list)  # sentence ends
    center_x: int = 540
    center_y: int = 1105
    size: int = 440


class SceneManifest(_M):
    schema_version: int = 3
    job_id: str
    title: str
    cover_title: str = Field(default="", max_length=48)
    width: int = 1080
    height: int = 1920
    fps: int = 30
    duration_frames: int = Field(gt=0)
    handle: str = ""
    audio_src: str | None = "narration.wav"
    theme: Theme = Field(default_factory=Theme)
    caption_style: CaptionStyle = Field(default_factory=CaptionStyle)
    scenes: list[Scene] = Field(min_length=1)
    caption_groups: list[CaptionGroupF]
    avatar: AvatarTrack
    sfx_cues: list[SfxCue] = Field(default_factory=list)
    music_cues: list[MusicCue] = Field(default_factory=list)


def validate_manifest(m: SceneManifest) -> list[str]:
    """Structural checks beyond field types. Returns a list of errors (empty = valid)."""
    errs: list[str] = []
    if (m.width, m.height) != (1080, 1920):
        errs.append(f"canvas is {m.width}x{m.height}, expected 1080x1920")
    if m.fps != 30:
        errs.append(f"fps is {m.fps}, expected 30")
    if m.scenes[0].start_frame != 0:
        errs.append("first scene does not start at frame 0 (would show an empty frame)")
    if m.scenes[-1].end_frame != m.duration_frames:
        errs.append(f"last scene ends at {m.scenes[-1].end_frame}, video ends at {m.duration_frames}")
    ids = set()
    for i, s in enumerate(m.scenes):
        if s.id in ids:
            errs.append(f"duplicate scene id {s.id}")
        ids.add(s.id)
        if s.end_frame - s.start_frame < 12:
            errs.append(f"scene {s.id} is shorter than 12 frames")
        if i and s.start_frame != m.scenes[i - 1].end_frame:
            errs.append(f"gap/overlap between scene {m.scenes[i - 1].id} and {s.id}")
        if s.type == "stat" and s.stat is None:
            errs.append(f"stat scene {s.id} has no stat data")
        if s.type in ("analogy", "comparison") and not (s.left and s.right):
            errs.append(f"{s.type} scene {s.id} needs left and right text")
        if s.type == "diagram" and not 2 <= len(s.items) <= 4:
            errs.append(f"diagram scene {s.id} needs 2-4 items")
        if s.icon not in ICONS:
            errs.append(f"scene {s.id} uses unknown icon {s.icon!r}")
        if any(len(it) > 32 for it in s.items):
            errs.append(f"scene {s.id} has a diagram item longer than 32 chars")
        if s.type == "terminal" and not (s.meta.get("cast") and s.meta.get("timing")):
            errs.append(f"terminal scene {s.id} needs a recorded cast and its timing")
        if s.type == "evidence" and not (s.asset or s.meta.get("fallback")):
            errs.append(f"evidence scene {s.id} has neither a screenshot nor a quote fallback")
        if s.type == "bars" and len(s.meta.get("bars", [])) < 2:
            errs.append(f"bars scene {s.id} needs at least two bars")
        if s.type == "demo" and not s.lines:
            errs.append(f"demo scene {s.id} needs lines")
        if any(len(line) > 34 for line in s.lines):
            errs.append(f"scene {s.id} has a demo line longer than 34 chars")
        for c in s.cues:
            if not s.start_frame <= c.frame < s.end_frame:
                errs.append(f"scene {s.id} has a cue at frame {c.frame} outside the scene")
        if [c.frame for c in s.cues] != sorted(c.frame for c in s.cues):
            errs.append(f"scene {s.id} cues are not in time order")
    prev_end = 0
    for gi, g in enumerate(m.caption_groups):
        if g.start_frame < prev_end:
            errs.append(f"caption group {gi} overlaps the previous group")
        if g.end_frame <= g.start_frame or g.end_frame > m.duration_frames:
            errs.append(f"caption group {gi} has bad bounds {g.start_frame}-{g.end_frame}")
        prev_end = g.end_frame
        for w in g.words:
            if not (g.start_frame <= w.start_frame < w.end_frame <= g.end_frame):
                errs.append(f"caption word '{w.text}' frames {w.start_frame}-{w.end_frame} outside its group")
    cs = m.caption_style
    if cs.center_y + cs.font_size * 1.2 > SAFE_BOTTOM or cs.center_y - cs.font_size * 1.2 < SAFE_TOP:
        errs.append("caption position falls outside the platform safe area")
    if len(m.avatar.mouth_open) != m.duration_frames or len(m.avatar.visemes) != m.duration_frames:
        errs.append("avatar tracks must have one value per frame")
    if any(not 0 <= v <= 1 for v in m.avatar.mouth_open):
        errs.append("avatar mouth_open values must be within 0..1")
    if any(not 0 <= c.frame < m.duration_frames for c in m.sfx_cues):
        errs.append("a sound-effect cue lies outside the video")
    return errs
