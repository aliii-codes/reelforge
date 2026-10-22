"""Job state machine. Every state change goes through `check_transition`."""

from __future__ import annotations

from enum import StrEnum


class JobState(StrEnum):
    CREATED = "created"
    RESEARCHING = "researching"
    AWAITING_SCRIPT_APPROVAL = "awaiting_script_approval"
    GENERATING_VOICE = "generating_voice"
    ALIGNING_CAPTIONS = "aligning_captions"
    PLANNING_SCENES = "planning_scenes"
    PREVIEWING = "previewing"
    AWAITING_PREVIEW_APPROVAL = "awaiting_preview_approval"
    RENDERING = "rendering"
    AWAITING_VIDEO_APPROVAL = "awaiting_video_approval"
    COMPLETED = "completed"
    FAILED = "failed"


# Stages that do work, in pipeline order. A failed job resumes at the stage that failed.
WORK_STAGES: tuple[JobState, ...] = (
    JobState.RESEARCHING,
    JobState.GENERATING_VOICE,
    JobState.ALIGNING_CAPTIONS,
    JobState.PLANNING_SCENES,
    JobState.PREVIEWING,
    JobState.RENDERING,
)

POST_APPROVAL_STAGES: tuple[JobState, ...] = WORK_STAGES[1:]

_REWORK = {
    JobState.AWAITING_SCRIPT_APPROVAL,  # script revision after seeing the video
    JobState.GENERATING_VOICE,
    JobState.ALIGNING_CAPTIONS,  # e.g. a different take was selected
    JobState.PLANNING_SCENES,  # manifest edited
    JobState.PREVIEWING,
    JobState.RENDERING,
}

TRANSITIONS: dict[JobState, set[JobState]] = {
    JobState.CREATED: {JobState.RESEARCHING, JobState.AWAITING_SCRIPT_APPROVAL, JobState.FAILED},
    JobState.RESEARCHING: {JobState.AWAITING_SCRIPT_APPROVAL, JobState.FAILED},
    JobState.AWAITING_SCRIPT_APPROVAL: {
        JobState.AWAITING_SCRIPT_APPROVAL,  # a revision creates a new version, still unapproved
        JobState.GENERATING_VOICE,  # approval
        JobState.FAILED,
    },
    JobState.GENERATING_VOICE: {JobState.ALIGNING_CAPTIONS, JobState.FAILED},
    JobState.ALIGNING_CAPTIONS: {JobState.PLANNING_SCENES, JobState.FAILED},
    JobState.PLANNING_SCENES: {JobState.PREVIEWING, JobState.RENDERING, JobState.FAILED},
    JobState.PREVIEWING: {JobState.AWAITING_PREVIEW_APPROVAL, JobState.RENDERING, JobState.FAILED},
    # approve -> rendering; or send back for rework (e.g. a different voice-over, edited manifest)
    JobState.AWAITING_PREVIEW_APPROVAL: (_REWORK - {JobState.RENDERING}) | {JobState.RENDERING},
    JobState.RENDERING: {JobState.AWAITING_VIDEO_APPROVAL, JobState.FAILED},
    JobState.AWAITING_VIDEO_APPROVAL: {JobState.COMPLETED} | _REWORK,
    JobState.COMPLETED: set(),  # final; start a new job for a new version
    JobState.FAILED: set(WORK_STAGES) | {JobState.AWAITING_SCRIPT_APPROVAL},
}


class InvalidTransition(Exception):
    pass


def check_transition(current: JobState, target: JobState) -> None:
    if target not in TRANSITIONS[current]:
        raise InvalidTransition(f"cannot move job from '{current}' to '{target}'")


def next_stage(state: JobState, preview_gate: bool = True) -> JobState | None:
    """The state that follows a completed work stage (None if `state` is not a work stage)."""
    if state == JobState.PREVIEWING:
        return JobState.AWAITING_PREVIEW_APPROVAL if preview_gate else JobState.RENDERING
    order = [
        JobState.GENERATING_VOICE,
        JobState.ALIGNING_CAPTIONS,
        JobState.PLANNING_SCENES,
        JobState.PREVIEWING,
    ]
    if state in order[:-1]:
        return order[order.index(state) + 1]
    if state == JobState.RENDERING:
        return JobState.AWAITING_VIDEO_APPROVAL
    return None
