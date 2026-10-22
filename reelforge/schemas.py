"""Shared, validated data models for scripts, research, audio and jobs."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Average narration speed used for *estimates* only; real timing always comes from audio.
WORDS_PER_SECOND_ESTIMATE = 2.6

SectionRole = Literal["hook", "explain", "beat", "number", "analogy", "twist", "payoff", "cta"]
SceneType = Literal[
    "hook",
    "explain",
    "stat",
    "analogy",
    "diagram",
    "comparison",
    "twist",
    "cta",
    "demo",
    "reveal",
    "kinetic",
    "terminal",
    "evidence",
    "bars",
    "meme",
    "photo",
]
Expression = Literal["neutral", "surprised", "thoughtful", "happy", "skeptical"]


def utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- script


class VisualHint(StrictModel):
    """Optional author/LLM hints for the scene planner. Empty fields mean "decide for me"."""

    scene: SceneType | None = None
    headline: str = ""
    subtext: str = ""
    items: list[str] = Field(default_factory=list)
    left: str = ""
    right: str = ""
    stat_value: float | None = None
    stat_prefix: str = ""
    stat_suffix: str = ""
    stat_label: str = ""
    icon: str = ""
    expression: Expression | None = None
    lines: list[str] = Field(default_factory=list)  # demo scene: terminal/output lines
    # Audio-anchored editing: this visual starts when this phrase is spoken (beats after the first).
    at: str = ""
    # Real terminal footage recorded with `capture-terminal` (embedded so the approved script is
    # self-contained and its hash covers the footage).
    cast: dict | None = None
    # Evidence: a real screenshot of `source` with `quote` highlighted (captured at planning time).
    source: str = ""
    quote: str = ""
    # Meme beat: top/bottom impact text over an avatar reaction.
    top: str = ""
    bottom: str = ""


class ScriptSection(StrictModel):
    role: SectionRole
    text: str
    visual: VisualHint = Field(default_factory=VisualHint)
    # Further visuals for later beats of this section, each anchored with `at`.
    beats: list[VisualHint] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def _text_not_empty(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("section text must not be empty")
        return v


class Hook(StrictModel):
    text: str
    angle: str = ""
    rationale: str = ""
    llm_score: float | None = None
    heuristic_score: float = 0.0
    score: float = 0.0


class Script(StrictModel):
    title: str
    topic: str = ""
    sections: list[ScriptSection] = Field(min_length=1)
    hooks: list[Hook] = Field(default_factory=list)
    selected_hook: int | None = None
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)
    handle: str = ""

    @property
    def full_text(self) -> str:
        return " ".join(s.text for s in self.sections)

    @property
    def word_count(self) -> int:
        return len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'’.%-]*", self.full_text))

    @property
    def estimated_seconds(self) -> float:
        return round(self.word_count / WORDS_PER_SECOND_ESTIMATE, 1)


# --------------------------------------------------------------------------- research


class ClaimStatus(StrEnum):
    UNVERIFIED = "unverified"  # nothing checked (no sources, or sources could not be opened)
    AUTO_SUPPORTED = "auto_supported"  # fetched source text lexically matches; human review advised
    WEAK_EVIDENCE = "weak_evidence"  # partial lexical match only
    NOT_FOUND_IN_SOURCE = "not_found_in_source"  # sources opened, claim not found in their text
    CONFLICTING = "conflicting"
    HUMAN_VERIFIED = "human_verified"
    HUMAN_REJECTED = "human_rejected"


class Source(StrictModel):
    id: str
    url: str
    title: str = ""
    origin: Literal["wikipedia", "tavily", "manual", "llm_suggested"] = "manual"
    notes: str = ""
    fetched: bool = False
    http_status: int | None = None
    accessed_at: str | None = None
    excerpt: str = ""  # trimmed text actually retrieved from the page (empty if not fetched)
    fetch_error: str = ""

    @field_validator("url")
    @classmethod
    def _http_url(cls, v: str) -> str:
        v = v.strip()
        if not re.match(r"^https?://[^\s/$.?#].[^\s]*$", v):
            raise ValueError(f"not an http(s) URL: {v!r}")
        return v

    @property
    def domain(self) -> str:
        m = re.match(r"^https?://([^/]+)", self.url)
        host = m.group(1) if m else self.url
        return host.removeprefix("www.")


class Claim(StrictModel):
    id: str
    text: str
    section_index: int | None = None
    source_ids: list[str] = Field(default_factory=list)
    support_explanation: str = ""
    status: ClaimStatus = ClaimStatus.UNVERIFIED
    uncertainty: str = ""
    check_details: str = ""


class ResearchBundle(StrictModel):
    sources: list[Source] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    research_mode: Literal["online", "manual", "none"] = "none"
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _claims_reference_known_sources(self) -> ResearchBundle:
        ids = {s.id for s in self.sources}
        if len(ids) != len(self.sources):
            raise ValueError("duplicate source ids")
        for c in self.claims:
            missing = [sid for sid in c.source_ids if sid not in ids]
            if missing:
                raise ValueError(f"claim {c.id} references unknown sources {missing}")
        return self


class ScriptVersion(StrictModel):
    version: int
    created_at: str = Field(default_factory=utcnow)
    origin: str  # "manual", "llm:groq:<model>", "revision:manual", ...
    note: str = ""
    script: Script
    research: ResearchBundle = Field(default_factory=ResearchBundle)
    warnings: list[str] = Field(default_factory=list)

    def content_hash(self) -> str:
        payload = json.dumps(
            {"script": self.script.model_dump(mode="json"), "research": self.research.model_dump(mode="json")},
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


# --------------------------------------------------------------------------- audio


class Word(StrictModel):
    text: str
    start: float
    end: float
    probability: float | None = None


class Segment(StrictModel):
    text: str
    start: float
    end: float


class Transcript(StrictModel):
    text: str
    words: list[Word]
    segments: list[Segment]
    language: str = "en"
    model: str
    word_level: bool = True
    duration: float


class AudioQuality(StrictModel):
    duration: float
    sample_rate: int
    channels: int
    peak_dbfs: float
    rms_dbfs: float
    clipping_ratio: float
    silence_ratio: float
    longest_pause: float
    noise_floor_dbfs: float
    snr_estimate_db: float
    issues: list[str] = Field(default_factory=list)


class TakeReport(StrictModel):
    index: int
    path: str
    engine: str
    voice_label: str
    seed: int | None = None
    generation_seconds: float | None = None
    duration: float
    transcript_path: str
    wer: float
    missing_words: list[str]
    extra_words: list[str]
    substitutions: list[tuple[str, str]]
    audio: AudioQuality
    score: float
    issues: list[str] = Field(default_factory=list)


class JobConfig(StrictModel):
    """Per-job choices, frozen into project_config.json. Never contains secrets."""

    voice_mode: Literal["clone", "stock", "file"] = "stock"
    voice_profile: str = "default"
    stock_voice: str = "marius"
    narration_file: str | None = None
    takes: int = Field(default=3, ge=1, le=5)
    speaking_rate: float = Field(default=1.0, ge=0.8, le=1.25)
    pronunciations: dict[str, str] = Field(default_factory=dict)
    music: str = "generated"  # "generated", "none", or a path to a licensed audio file
    music_licence: str = ""
    music_volume_db: float = Field(default=-30.0, le=-12.0)
    sfx: bool = True
    sfx_volume_db: float = Field(default=-22.0, le=-10.0)
    llm_provider: str = "auto"
    research: bool = True
    fetch_sources: bool = True
    handle: str = ""
    render_concurrency: int = Field(default=4, ge=1, le=8)
    target_min_seconds: float = 45.0
    target_max_seconds: float = 60.0
    # Human voice-over processing (voice_mode="file"); conservative defaults.
    vo_trim: bool = True
    vo_max_pause: float | None = Field(default=None, ge=0.3, le=3.0)
    vo_denoise: bool = False
    vo_normalize: bool = True
    # Caption words: the script's spelling (timed by Whisper), the transcript's own words, or
    # "auto" = script unless the recording departs from it noticeably.
    caption_source: Literal["auto", "script", "transcript"] = "auto"
    # Stop after a low-resolution preview so it can be checked before the long final render.
    preview_gate: bool = True
    preview_scale: float = Field(default=1 / 3, ge=0.2, le=0.75)  # 360x640
    # Target seconds between visual changes (audio-driven editing pace).
    edit_pace_s: float = Field(default=3.2, ge=1.8, le=6.0)
