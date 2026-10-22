"""Job state machine, persistence, approval and resume, with fake voice/transcriber/renderer.

The fake renderer encodes a real (test-pattern) MP4 with FFmpeg, so muxing, validation and the
package writer run for real. Remotion itself is exercised by the demo, not by unit tests.
"""

import json
import os
from pathlib import Path

import pytest

from reelforge.database import Database
from reelforge.jobs.orchestrator import Pipeline, PipelineError
from reelforge.jobs.state import InvalidTransition, JobState, check_transition
from reelforge.rendering.validation import even_dim
from reelforge.schemas import JobConfig, Script, Segment, Transcript, Word
from reelforge.tests.conftest import make_video, write_tone
from reelforge.voice.base import VoiceEngine

STEP = 0.15


class FakeEngine(VoiceEngine):
    name = "fake"
    voice_label = "fake test voice"
    provenance = "synthetic test tone"
    licence_note = "n/a"

    def __init__(self):
        self.calls = 0

    def synthesize(self, script: Script, out_path: Path, seed: int, pronunciations: dict[str, str]) -> None:
        self.calls += 1
        n = sum(len(s.text.split()) for s in script.sections)
        write_tone(out_path, n * STEP + 0.6)


class FakeTranscriber:
    def __init__(self, script_words: list[str]):
        self.words = script_words

    def __call__(self, path: Path) -> Transcript:
        ws = [
            Word(text=w, start=round(0.2 + i * STEP, 3), end=round(0.2 + i * STEP + 0.12, 3))
            for i, w in enumerate(self.words)
        ]
        return Transcript(
            text=" ".join(self.words),
            words=ws,
            segments=[Segment(text=" ".join(self.words), start=ws[0].start, end=ws[-1].end)],
            model="fake",
            duration=len(self.words) * STEP + 0.6,
        )


class FakeRenderer:
    def __init__(self, fail_times: int = 0):
        self.fail_times = fail_times
        self.calls = 0

    def render_video(
        self, renderer_dir, *, props, public_dir, output, concurrency=4, log=print, log_file=None, scale=1.0, **kw
    ):
        if scale != 1.0:
            self.preview_calls = getattr(self, "preview_calls", 0) + 1
        else:
            self.calls += 1
            if self.calls <= self.fail_times:
                raise RuntimeError("simulated renderer crash")
        frames = json.loads(Path(props).read_text())["duration_frames"]
        w, h = even_dim(1080 * scale), even_dim(1920 * scale)
        make_video(output, frames / 30, size=f"{w}x{h}", frames=frames)

        class R:
            seconds = 0.1
            command = ["fake-render"]

        return R()

    def render_still(self, renderer_dir, *, props, public_dir, output, log=print):
        raise RuntimeError("no still renderer in tests")  # exercises the cover fallback


def make_pipeline(settings, script_file, fail_render=0):
    from reelforge.scripting.manual import parse_script_file

    script, _, _ = parse_script_file(script_file)
    words = [w for s in script.sections for w in s.text.split()]
    engine = FakeEngine()
    renderer = FakeRenderer(fail_render)
    p = Pipeline(
        settings,
        log=lambda m: None,
        engine_factory=lambda cfg: engine,
        transcriber=FakeTranscriber(words),
        renderer=renderer,
    )
    return p, engine, renderer


CFG = JobConfig(
    takes=2, fetch_sources=False, music="generated", target_min_seconds=1, target_max_seconds=60, preview_gate=False
)


def test_state_transitions():
    check_transition(JobState.CREATED, JobState.AWAITING_SCRIPT_APPROVAL)
    check_transition(JobState.FAILED, JobState.RENDERING)
    with pytest.raises(InvalidTransition):
        check_transition(JobState.CREATED, JobState.RENDERING)
    with pytest.raises(InvalidTransition):
        check_transition(JobState.AWAITING_SCRIPT_APPROVAL, JobState.RENDERING)
    with pytest.raises(InvalidTransition):
        check_transition(JobState.COMPLETED, JobState.RENDERING)


def test_sqlite_persistence(settings, script_file):
    p, _, _ = make_pipeline(settings, script_file)
    job = p.create_from_script(script_file, CFG)
    again = Database(settings.db_path).get_job(job.id)  # fresh connection
    assert again.state == JobState.AWAITING_SCRIPT_APPROVAL
    assert again.config["takes"] == 2 and again.config["pronunciations"] == {"CPU": "C P U"}
    assert len(Database(settings.db_path).script_versions(job.id)) == 1


def test_manual_workflow_end_to_end(settings, script_file):
    p, engine, renderer = make_pipeline(settings, script_file)
    job = p.create_from_script(script_file, CFG)
    with pytest.raises(PipelineError):
        p.resume(job.id)  # not approved yet
    p.approve_script(job.id)
    job = p.run(job.id)
    assert job.state == JobState.AWAITING_VIDEO_APPROVAL, job.last_error
    assert engine.calls == 2
    out = job.output_dir
    check = json.loads((out / "package_manifest.json").read_text())
    assert check["complete"], check["missing"]
    rep = json.loads((out / "validation_report.json").read_text())
    assert rep["video"]["ok"] and rep["captions"]["ok"] and rep["scene_manifest"]["ok"]
    meta = json.loads((out / "render_metadata.json").read_text())
    assert meta["voice"]["provenance"] == "synthetic test tone" and meta["published"] is False
    assert meta["cover"] == "frame at 1.0s"
    assert "set" not in json.dumps(json.loads((out / "project_config.json").read_text())["settings"]["groq_api_key"])
    assert len((out / "hashtags.txt").read_text().split()) == 5
    job = p.approve_video(job.id)
    assert job.state == JobState.COMPLETED and (out / "approval.json").exists()


def test_resume_after_failed_render_reuses_voice(settings, script_file):
    p, engine, renderer = make_pipeline(settings, script_file, fail_render=1)
    job = p.create_from_script(script_file, CFG)
    p.approve_script(job.id)
    job = p.run(job.id)
    assert job.state == JobState.FAILED and job.failed_stage == JobState.RENDERING
    assert "simulated renderer crash" in job.last_error
    job = p.resume(job.id)
    assert job.state == JobState.AWAITING_VIDEO_APPROVAL, job.last_error
    assert engine.calls == 2  # takes were not regenerated
    runs = [(r["stage"], r["status"]) for r in p.db.stage_runs(job.id)]
    assert ("rendering", "failed") in runs and ("rendering", "succeeded") in runs


def test_approved_script_is_immutable(settings, script_file):
    p, _, _ = make_pipeline(settings, script_file)
    job = p.create_from_script(script_file, CFG)
    p.approve_script(job.id)
    v1 = Path(p.db.script_versions(job.id)[0]["path"])
    os.chmod(v1, 0o644)
    v1.write_text(v1.read_text().replace("laptop", "toaster"))
    job = p.run(job.id)
    assert job.state == JobState.FAILED and "modified on disk after approval" in job.last_error


def test_revision_creates_new_version_and_clears_approval(settings, script_file, tmp_path):
    p, _, _ = make_pipeline(settings, script_file)
    job = p.create_from_script(script_file, CFG)
    edited = tmp_path / "edited.txt"
    edited.write_text(script_file.read_text().replace("loves tech", "loves gadgets"))
    sv = p.revise(job.id, script_file=edited)
    assert sv.version == 2 and sv.origin == "revision:manual"
    assert p.load_version(p.db.get_job(job.id), 1).script.sections[-1].text.endswith("loves tech.")
    p.approve_script(job.id)
    assert p.db.get_job(job.id).approved_version == 2


def test_select_take_reruns_downstream(settings, script_file):
    p, engine, renderer = make_pipeline(settings, script_file)
    job = p.create_from_script(script_file, CFG)
    p.approve_script(job.id)
    p.run(job.id)
    p.select_take(job.id, 2)
    job = p.run(job.id)
    assert job.state == JobState.AWAITING_VIDEO_APPROVAL and job.selected_take == 2
    # fake takes are identical, so the new manifest is identical and the Remotion render is reused
    assert engine.calls == 2 and renderer.calls == 1
    assert (job.output_dir / "narration.wav").read_bytes() == (p.work_dir(job) / "takes" / "take_2.wav").read_bytes()


def test_topic_job_without_llm_fails_cleanly_and_can_resume(settings):
    p = Pipeline(settings, log=lambda m: None)
    job = p.create_from_topic("How tiny models work", JobConfig(research=False))
    assert job.state == JobState.FAILED and job.failed_stage == JobState.RESEARCHING
    assert "No LLM provider is configured" in job.last_error
    assert p.resume(job.id).state == JobState.FAILED  # still no key: fails again, no crash


def test_output_directory_never_reused(settings, script_file):
    p, _, _ = make_pipeline(settings, script_file)
    a = p.create_from_script(script_file, CFG)
    b = p.create_from_script(script_file, CFG)
    assert a.output_dir != b.output_dir and a.output_dir.exists() and b.output_dir.exists()


def test_rework_rendering_reuses_matching_silent_render(settings, script_file):
    p, engine, renderer = make_pipeline(settings, script_file)
    job = p.create_from_script(script_file, CFG)
    p.approve_script(job.id)
    p.run(job.id)
    p.request_rework(job.id, JobState.RENDERING, "re-mix only")
    job = p.run(job.id)
    assert job.state == JobState.AWAITING_VIDEO_APPROVAL
    assert renderer.calls == 1  # manifest unchanged -> Remotion output reused


def test_resume_from_earlier_stage_rescoring_takes(settings, script_file):
    p, engine, renderer = make_pipeline(settings, script_file, fail_render=1)
    job = p.create_from_script(script_file, CFG)
    p.approve_script(job.id)
    job = p.run(job.id)
    assert job.state == JobState.FAILED
    with pytest.raises(PipelineError):
        p.resume(job.id, JobState.AWAITING_VIDEO_APPROVAL)
    job = p.resume(job.id, JobState.GENERATING_VOICE)
    assert job.state == JobState.AWAITING_VIDEO_APPROVAL, job.last_error
    assert engine.calls == 2  # takes re-scored from existing audio, not re-synthesized


def test_preview_gate_then_final_render(settings, script_file):
    p, engine, renderer = make_pipeline(settings, script_file)
    job = p.create_from_script(script_file, CFG.model_copy(update={"preview_gate": True}))
    p.approve_script(job.id)
    job = p.run(job.id)
    assert job.state == JobState.AWAITING_PREVIEW_APPROVAL, job.last_error
    out = job.output_dir
    rep = json.loads((out / "preview_report.json").read_text())
    assert rep["ok"] and rep["summary"]["width"] == 360 and rep["summary"]["height"] == 640
    assert rep["render_completion"]["frames"] == rep["render_completion"]["expected"]
    assert abs(rep["caption_timing"]["first_word_offset_s"]) <= 0.3
    assert (out / "preview_contact_sheet.jpg").exists() and not (out / "final_reel.mp4").exists()
    assert renderer.calls == 0 and renderer.preview_calls == 1
    with pytest.raises(PipelineError):
        p.approve_video(job.id)
    p.approve_preview(job.id)
    job = p.run(job.id)
    assert job.state == JobState.AWAITING_VIDEO_APPROVAL and renderer.calls == 1
    final = json.loads((out / "validation_report.json").read_text())["video"]
    assert final["ok"] and final["render_completion"]["frames"] == final["render_completion"]["expected"]


def test_rework_from_preview(settings, script_file):
    p, _, _ = make_pipeline(settings, script_file)
    job = p.create_from_script(script_file, CFG.model_copy(update={"preview_gate": True}))
    p.approve_script(job.id)
    p.run(job.id)
    p.request_rework(job.id, JobState.PLANNING_SCENES, "edited manifest")
    assert p.run(job.id).state == JobState.AWAITING_PREVIEW_APPROVAL


def test_attach_voiceover_regenerates_takes(settings, script_file, tmp_path):
    p, engine, renderer = make_pipeline(settings, script_file)
    job = p.create_from_script(script_file, CFG)
    p.approve_script(job.id)
    p.run(job.id)
    bad = tmp_path / "silent.wav"
    write_tone(bad, 20, amp=0.0, noise=0.0)
    with pytest.raises(PipelineError, match="silent"):
        p.attach_voiceover(job.id, bad)
    vo = write_tone(tmp_path / "vo.wav", 30, sr=48000)
    job = p.attach_voiceover(job.id, vo, vo_max_pause=0.8)
    cfg = p.config(job)
    assert job.state == JobState.GENERATING_VOICE and cfg.voice_mode == "file" and cfg.takes == 1
    assert Path(cfg.narration_file).parent.name == "voiceover_source"
    archived_before = (
        list((p.work_dir(job) / "archive").glob("*/takes")) if (p.work_dir(job) / "archive").exists() else []
    )
    assert not archived_before


def test_voiceover_job_needs_recording_before_approval(settings, script_file, tmp_path):
    p, _, _ = make_pipeline(settings, script_file)
    job = p.create_from_script(script_file, CFG.model_copy(update={"voice_mode": "file", "takes": 1}))
    with pytest.raises(PipelineError, match="no voice-over attached"):
        p.approve_script(job.id)
    p.attach_voiceover(job.id, write_tone(tmp_path / "vo.wav", 30, sr=48000))
    assert p.approve_script(job.id).state == JobState.GENERATING_VOICE


class FakeLLM:
    """Stands in for Groq/Cohere: canned queries, hooks and one distinct draft per angle."""

    name = "fake"
    model = "fake-1"
    label = "fake:fake-1"

    def research_queries(self, topic):
        from reelforge.providers.base import QueriesOut

        return QueriesOut(queries=[topic])

    def generate_hooks(self, topic, context):
        from reelforge.providers.base import HookSetOut

        return HookSetOut.model_validate(
            {"hooks": [{"text": f"Hook {i} about tiny models", "score": 8 - i} for i in range(3)]}
        )

    def generate_script(self, topic, hook, sources, style=""):
        from reelforge.providers.base import ScriptDraftOut

        body = "A model is a giant list of numbers called weights, held in memory while it runs. " * 3
        return ScriptDraftOut.model_validate(
            {
                "title": f"Draft angle: {style[:20]}",
                "sections": [
                    {"role": "hook", "text": hook + "."},
                    {"role": "explain", "text": body},
                    {"role": "twist", "text": "But here's the catch, quality drops when you squeeze too hard."},
                    {"role": "cta", "text": "Send this to a friend who codes."},
                ],
                "claims": [],
                "caption": "c",
                "hashtags": ["#AI"],
            }
        )


def test_topic_gives_drafts_then_pick_then_voice(settings):
    from reelforge.providers import FallbackLLM

    p = Pipeline(settings, log=lambda m: None, llm_factory=lambda pref: FallbackLLM([FakeLLM()]))
    job = p.create_from_topic("How small models work", JobConfig(voice_mode="ask", research=False, drafts=3))
    assert job.state == JobState.AWAITING_SCRIPT_APPROVAL, job.last_error
    drafts = p.drafts(job)
    assert [d.version for d in drafts] == [1, 2, 3]
    assert len({d.script.title for d in drafts}) == 3  # three different angles
    assert all(" · " in d.note for d in drafts) and drafts[1].script.selected_hook == 1
    p.pick_script(job.id, 2)
    assert p.config(p.db.get_job(job.id)).picked_version == 2
    with pytest.raises(PipelineError, match="choose the voice first"):
        p.approve_script(job.id)  # never runs without a voice decision
    p.choose_voice(job.id, "ai")
    cfg = p.config(p.db.get_job(job.id))
    assert cfg.voice_mode == "stock"
    job = p.approve_script(job.id)
    assert job.approved_version == 2 and job.state == JobState.GENERATING_VOICE  # the picked draft, not the latest


def test_choose_voice_with_a_recording(settings, script_file, tmp_path):
    p, _, _ = make_pipeline(settings, script_file)
    job = p.create_from_script(script_file, CFG.model_copy(update={"voice_mode": "ask"}))
    p.choose_voice(job.id, "file", write_tone(tmp_path / "vo.wav", 30, sr=48000))
    assert p.config(p.db.get_job(job.id)).voice_mode == "file"
    assert p.approve_script(job.id).state == JobState.GENERATING_VOICE
