"""ReelForge AI command-line interface.

uv run python -m reelforge.main --help
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from reelforge.config import load_settings
from reelforge.database import JobNotFound
from reelforge.export import package as pkg
from reelforge.jobs.orchestrator import Pipeline, PipelineError
from reelforge.jobs.state import JobState
from reelforge.schemas import ClaimStatus, JobConfig, ScriptVersion
from reelforge.scripting.validation import validate_script

app = typer.Typer(
    help="ReelForge AI: topic or script -> approved script -> narration -> captions -> scenes -> "
    "rendered vertical reel. Nothing is ever published automatically.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


def _pipeline() -> Pipeline:
    return Pipeline(load_settings(), log=lambda m: console.print(m, highlight=False, markup=False))


def _job(p: Pipeline, job_id: str):
    try:
        return p.db.get_job(job_id)
    except JobNotFound:
        console.print(f"[red]No job {job_id!r}.[/] Run `list` to see jobs.")
        raise typer.Exit(1) from None


def _abort(e: Exception) -> None:
    console.print(f"[red]Error:[/] {e}")
    raise typer.Exit(1)


STATUS_STYLE = {
    ClaimStatus.HUMAN_VERIFIED: "green",
    ClaimStatus.AUTO_SUPPORTED: "green",
    ClaimStatus.WEAK_EVIDENCE: "yellow",
    ClaimStatus.UNVERIFIED: "red",
    ClaimStatus.NOT_FOUND_IN_SOURCE: "red",
    ClaimStatus.CONFLICTING: "red",
    ClaimStatus.HUMAN_REJECTED: "red",
}


def show_version(sv: ScriptVersion, job_id: str) -> None:
    s = sv.script
    console.print(
        Panel.fit(
            f"[bold]{s.title}[/]\njob {job_id} · script v{sv.version} · origin {sv.origin}\n"
            f"{s.word_count} words · estimated {s.estimated_seconds}s (real timing comes from the narration)",
            title="Script for review",
        )
    )
    if s.hooks:
        t = Table("#", "hook candidate", "score", title="Hook candidates (ranked)")
        for i, h in enumerate(s.hooks):
            t.add_row(str(i + 1) + (" ✓" if i == s.selected_hook else ""), h.text, f"{h.score:.1f}")
        console.print(t)
    for sec in s.sections:
        hint = f"  [dim](on screen: {sec.visual.headline})[/]" if sec.visual.headline else ""
        console.print(f"[cyan]\\[{sec.role}][/] {sec.text}{hint}")
    console.print()
    if sv.research.claims:
        t = Table("id", "claim", "status", "sources", title=f"Claims (research: {sv.research.research_mode})")
        by_id = {x.id: x for x in sv.research.sources}
        for c in sv.research.claims:
            srcs = ", ".join(f"{sid} {by_id[sid].domain}" for sid in c.source_ids if sid in by_id) or "-"
            t.add_row(c.id, c.text, f"[{STATUS_STYLE.get(c.status, 'white')}]{c.status.value}[/]", srcs)
        console.print(t)
        for c in sv.research.claims:
            if c.check_details or c.uncertainty:
                console.print(f"[dim]{c.id}: {c.check_details} {c.uncertainty}[/]")
    else:
        console.print("[yellow]No factual claims recorded: this job will be labelled unverified.[/]")
    if sv.research.sources:
        console.print("\n[bold]Sources[/]")
        for src in sv.research.sources:
            state = "opened" if src.fetched else f"NOT opened ({src.fetch_error or 'not fetched'})"
            console.print(f"  {src.id}: {src.url} [dim]({state}, {src.origin})[/]")
    chk = validate_script(sv.script, sv.research)
    for w in chk.warnings:
        console.print(f"[yellow]warning:[/] {w}")
    for e in chk.errors:
        console.print(f"[red]blocking:[/] {e}")


# --------------------------------------------------------------------------- jobs


@app.command()
def create(
    topic: Annotated[
        str | None, typer.Option(help="Topic to research and script with an LLM (needs an API key).")
    ] = None,
    script_file: Annotated[
        Path | None, typer.Option(exists=True, dir_okay=False, help="Hand-written script file.")
    ] = None,
    sources_file: Annotated[
        Path | None, typer.Option(exists=True, dir_okay=False, help="Extra sources: 'URL | note' per line.")
    ] = None,
    voice: Annotated[
        str, typer.Option(help="clone (your enrolled voice) | stock (labelled stock voice) | file")
    ] = "stock",
    narration: Annotated[
        Path | None, typer.Option(exists=True, dir_okay=False, help="Your recorded narration (voice=file).")
    ] = None,
    stock_voice: Annotated[str, typer.Option(help="Stock Pocket TTS voice (vetted licences only).")] = "",
    takes: Annotated[
        int, typer.Option(min=0, max=5, help="Narration takes to compare (0 = REELFORGE_TAKES, default 3).")
    ] = 0,
    rate: Annotated[float, typer.Option(min=0.8, max=1.25, help="Speaking-rate multiplier (pitch preserved).")] = 1.0,
    music: Annotated[str, typer.Option(help="generated | none | path to a licensed audio file")] = "generated",
    music_licence: Annotated[str, typer.Option(help="Licence of the music file (required for a file).")] = "",
    no_sfx: Annotated[bool, typer.Option("--no-sfx", help="Disable generated transition whooshes.")] = False,
    provider: Annotated[str, typer.Option(help="auto | groq | cohere | ollama")] = "auto",
    no_research: Annotated[bool, typer.Option("--no-research", help="Skip web search (topic mode).")] = False,
    offline: Annotated[bool, typer.Option("--offline", help="Do not open any source URLs.")] = False,
    handle: Annotated[str, typer.Option(help="Handle shown on the video, e.g. @you")] = "",
    max_pause: Annotated[
        float | None, typer.Option(help="Voice-over: shorten pauses longer than this many seconds (off by default).")
    ] = None,
    denoise: Annotated[bool, typer.Option("--denoise", help="Voice-over: light FFT noise reduction.")] = False,
    no_trim: Annotated[bool, typer.Option("--no-trim", help="Voice-over: keep leading/trailing silence.")] = False,
    no_normalize: Annotated[
        bool, typer.Option("--no-normalize", help="Voice-over: skip loudness normalisation.")
    ] = False,
    caption_source: Annotated[str, typer.Option(help="auto | script | transcript")] = "auto",
    no_preview_gate: Annotated[
        bool, typer.Option("--no-preview-gate", help="Render the final video without stopping at the preview.")
    ] = False,
    pace: Annotated[float, typer.Option(min=1.8, max=6.0, help="Target seconds between visual changes.")] = 3.2,
) -> None:
    """Create a job from a topic (LLM + research) or a script file (works offline)."""
    if bool(topic) == bool(script_file):
        _abort(ValueError("give exactly one of --topic or --script-file"))
    s = load_settings()
    if voice == "file" and narration:
        from reelforge.voice.voiceover import check_voiceover

        chk = check_voiceover(narration)
        _print_vo_check(chk)
        if not chk.ok:
            raise typer.Exit(1)
    cfg = JobConfig(
        voice_mode=voice,  # type: ignore[arg-type]  # validated by pydantic
        voice_profile=s.voice_profile,
        stock_voice=stock_voice or s.tts_stock_voice,
        narration_file=str(narration.resolve()) if narration else None,
        takes=1 if voice == "file" else (takes or s.takes),
        speaking_rate=rate,
        music=music,
        music_licence=music_licence,
        sfx=not no_sfx,
        llm_provider=provider,
        research=not no_research and not offline,
        fetch_sources=not offline,
        handle=handle or s.handle,
        render_concurrency=s.render_concurrency,
        vo_max_pause=max_pause,
        vo_denoise=denoise,
        vo_trim=not no_trim,
        vo_normalize=not no_normalize,
        caption_source=caption_source,  # type: ignore[arg-type]  # validated by pydantic
        preview_gate=not no_preview_gate,
        edit_pace_s=pace,
    )
    p = _pipeline()
    try:
        job = (
            p.create_from_script(script_file, cfg, sources_file)
            if script_file
            else p.create_from_topic(topic or "", cfg, sources_file)
        )
    except (PipelineError, ValueError) as e:
        _abort(e)
    if job.state == JobState.FAILED:
        console.print(f"[red]Job {job.id} failed:[/] {job.last_error}")
        console.print(f"Fix the cause (e.g. add an API key to .env) and run: [bold]reelforge resume {job.id}[/]")
        raise typer.Exit(1)
    show_version(p.load_version(job), job.id)
    console.print(f"\nApprove:  [bold]uv run python -m reelforge.main approve-script {job.id}[/]")
    console.print(
        f'Revise:   [bold]uv run python -m reelforge.main revise {job.id} --feedback "..."[/]  '
        f"or  --file edited_script.txt"
    )


@app.command("show-script")
def show_script(
    job_id: str, version: Annotated[int | None, typer.Option(help="Version (default latest).")] = None
) -> None:
    """Show a script version with claims and sources."""
    p = _pipeline()
    job = _job(p, job_id)
    show_version(p.load_version(job, version), job.id)


@app.command()
def revise(
    job_id: str,
    feedback: Annotated[str | None, typer.Option(help="Ask the LLM to revise with this feedback.")] = None,
    file: Annotated[Path | None, typer.Option(exists=True, dir_okay=False, help="Your edited script file.")] = None,
) -> None:
    """Create a new script version (approved versions are never modified)."""
    p = _pipeline()
    _job(p, job_id)
    try:
        sv = p.revise(job_id, feedback=feedback, script_file=file)
    except Exception as e:
        _abort(e)
    show_version(sv, job_id)


@app.command("approve-script")
def approve_script(
    job_id: str,
    version: Annotated[int | None, typer.Option(help="Version to approve (default latest).")] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt.")] = False,
    no_run: Annotated[bool, typer.Option("--no-run", help="Approve only; run later with `resume`.")] = False,
) -> None:
    """Approve a script version (frozen by hash) and continue the pipeline."""
    p = _pipeline()
    job = _job(p, job_id)
    sv = p.load_version(job, version)
    if not yes:
        show_version(sv, job.id)
        typer.confirm(f"Approve script v{sv.version} exactly as shown?", abort=True)
    try:
        p.approve_script(job_id, sv.version)
    except PipelineError as e:
        _abort(e)
    console.print(f"[green]Approved v{sv.version}.[/]")
    if not no_run:
        _report(p, p.run(job_id))


@app.command()
def resume(
    job_id: str,
    from_stage: Annotated[
        str | None, typer.Option(help="Failed jobs only: restart from an earlier stage, e.g. generating_voice.")
    ] = None,
) -> None:
    """Continue a job from its current or last failed stage, reusing finished work."""
    p = _pipeline()
    _job(p, job_id)
    try:
        job = p.resume(job_id, JobState(from_stage) if from_stage else None)
    except (PipelineError, ValueError) as e:
        _abort(e)
    if job.state == JobState.AWAITING_SCRIPT_APPROVAL:
        show_version(p.load_version(job), job.id)
    _report(p, job)


def _report(p: Pipeline, job) -> None:
    out = job.output_dir
    if job.state == JobState.FAILED:
        console.print(f"[red]Failed at {job.failed_stage}:[/] {job.last_error}")
        console.print(f"Resume after fixing: [bold]uv run python -m reelforge.main resume {job.id}[/]")
        raise typer.Exit(1)
    if job.state == JobState.AWAITING_PREVIEW_APPROVAL:
        rep = json.loads((out / "preview_report.json").read_text())
        v, ct = rep["summary"], rep.get("caption_timing", {})
        console.print(
            Panel.fit(
                f"[bold cyan]Preview:[/] {out / 'preview.mp4'}  ({v.get('width')}x{v.get('height')}, {v.get('duration')}s, "
                f"rendered in {rep.get('render_seconds')}s)\n"
                f"Contact sheet: {out / 'preview_contact_sheet.jpg'}\n"
                f"Frames {rep['render_completion']['frames']}/{rep['render_completion']['expected']} · "
                f"first caption vs narration onset {ct.get('first_word_offset_s')}s · "
                f"checks {'OK' if rep['ok'] else 'FAILED'} ({len(rep['warnings'])} warnings)",
                title="Check the preview before the full render",
            )
        )
        for w in rep["warnings"]:
            console.print(f"[yellow]warning:[/] {w}")
        console.print(f"Watch:   [bold]xdg-open {out / 'preview.mp4'}[/]")
        console.print(f"Approve: [bold]python -m reelforge.main approve-preview {job.id}[/]  (full 1080x1920 render)")
        console.print(
            f"Rework:  python -m reelforge.main rework {job.id} --stage planning_scenes   "
            f"or a new voice-over: python -m reelforge.main voiceover {job.id} --file new.wav"
        )
        return
    if job.state == JobState.AWAITING_VIDEO_APPROVAL:
        rep = json.loads((out / "validation_report.json").read_text())
        v = rep["video"]["summary"]
        console.print(
            Panel.fit(
                f"[bold green]Rendered:[/] {out / 'final_reel.mp4'}\n"
                f"{v.get('width')}x{v.get('height')} @ {v.get('fps')} fps · {v.get('video_codec')}/{v.get('audio_codec')} · "
                f"{v.get('duration')}s\nCover: {out / 'cover.png'}\nContact sheet: {out / 'contact_sheet.jpg'}\n"
                f"Validation: {'OK' if rep['video']['ok'] else 'FAILED'} ({len(rep['video']['warnings'])} warnings) → "
                f"{out / 'validation_report.json'}",
                title="Awaiting your final review",
            )
        )
        for w in rep["video"]["warnings"] + rep.get("captions", {}).get("warnings", []):
            console.print(f"[yellow]warning:[/] {w}")
        console.print(f"Watch:  [bold]xdg-open {out / 'final_reel.mp4'}[/]   (or mpv/vlc/ffplay)")
        console.print(f"Takes:  uv run python -m reelforge.main takes {job.id}")
        console.print(
            f"Approve: [bold]uv run python -m reelforge.main approve-video {job.id}[/]   "
            f"Rework: uv run python -m reelforge.main rework {job.id} --stage rendering"
        )
    else:
        console.print(f"Job {job.id} is now [bold]{job.state}[/].")


@app.command()
def status(job_id: str) -> None:
    """Show a job's state, stage history and outputs."""
    p = _pipeline()
    job = _job(p, job_id)
    console.print(
        Panel.fit(
            f"[bold]{job.title}[/]\nstate: [bold]{job.state}[/]"
            + (f"  (failed at {job.failed_stage}: {job.last_error})" if job.state == JobState.FAILED else "")
            + f"\nscript approved: {'v' + str(job.approved_version) if job.approved_version else 'no'}"
            + f" · selected take: {job.selected_take or '-'}\noutput: {job.output_dir}",
            title=job.id,
        )
    )
    t = Table("stage", "status", "seconds", "started", "error")
    for r in p.db.stage_runs(job.id):
        t.add_row(r["stage"], r["status"], str(r["seconds"] or ""), r["started_at"], (r["error"] or "")[:80])
    console.print(t)
    check = pkg.check_package(job.output_dir)
    console.print(f"package: {'complete' if check['complete'] else 'missing ' + ', '.join(check['missing'])}")


@app.command("list")
def list_jobs() -> None:
    """List jobs."""
    p = _pipeline()
    t = Table("job id", "title", "state", "updated")
    for j in p.db.list_jobs():
        t.add_row(j.id, j.title[:40], j.state.value, j.updated_at)
    console.print(t)


@app.command()
def takes(job_id: str) -> None:
    """List narration takes with transcript checks and scores."""
    p = _pipeline()
    job = _job(p, job_id)
    reports = p.take_reports(job)
    if not reports:
        _abort(PipelineError("no takes yet"))
    t = Table("take", "score", "WER", "duration", "issues", "file")
    for r in reports:
        sel = " ✓" if r.index == job.selected_take else ""
        t.add_row(
            f"{r.index}{sel}", f"{r.score:.1f}", f"{r.wer:.1%}", f"{r.duration:.1f}s", "; ".join(r.issues)[:90], r.path
        )
    console.print(t)
    console.print(f"Listen: ffplay -autoexit -nodisp <file>   ·   Choose: reelforge select-take {job.id} N")


@app.command("select-take")
def select_take(job_id: str, index: int) -> None:
    """Use a different narration take; captions, scenes and render are redone."""
    p = _pipeline()
    _job(p, job_id)
    try:
        p.select_take(job_id, index)
    except PipelineError as e:
        _abort(e)
    _report(p, p.run(job_id))


@app.command("render-preview")
def render_preview(
    job_id: str,
    scale: Annotated[float, typer.Option(min=0.2, max=1.0, help="Resolution scale (0.5 = 540x960).")] = 0.5,
    frames: Annotated[str | None, typer.Option(help="Frame range, e.g. 0-299 (silent if set).")] = None,
) -> None:
    """Fast low-resolution render of the current scene_manifest.json (no state change)."""
    p = _pipeline()
    job = _job(p, job_id)
    try:
        p.load_manifest(job)
    except PipelineError as e:
        _abort(e)
    work = p.work_dir(job)
    silent = work / "preview_silent.mp4"
    t0 = time.time()
    from reelforge.rendering import ffmpeg as ff
    from reelforge.rendering.remotion import render_video

    render_video(
        p.settings.renderer_dir,
        props=job.output_dir / "scene_manifest.json",
        public_dir=work / "public",
        output=silent,
        scale=scale,
        concurrency=p.config(job).render_concurrency,
        frames=frames,
        log=lambda m: console.print(m, markup=False),
    )
    out = work / "preview.mp4"
    if frames:
        shutil.copyfile(silent, out)
    else:
        m = p.load_manifest(job)
        ff.run(
            ff.build_mux_command(
                video=silent, audio=job.output_dir / "narration.wav", output=out, duration=m.duration_frames / m.fps
            )
        )
    console.print(f"[green]Preview ready in {time.time() - t0:.0f}s:[/] {out}")


@app.command("approve-video")
def approve_video(job_id: str, yes: Annotated[bool, typer.Option("--yes", "-y")] = False) -> None:
    """Mark the final video approved after you have watched it. Does NOT publish anything."""
    p = _pipeline()
    job = _job(p, job_id)
    if not yes:
        typer.confirm(
            f"Have you watched {job.output_dir / 'final_reel.mp4'} and approve it for publication?", abort=True
        )
    try:
        job = p.approve_video(job_id)
    except PipelineError as e:
        _abort(e)
    console.print(f"[green]Completed.[/] Package: {job.output_dir}  (upload manually; ReelForge never posts)")


@app.command()
def rework(
    job_id: str,
    stage: Annotated[
        str, typer.Option(help="generating_voice | aligning_captions | planning_scenes | rendering")
    ] = "rendering",
    note: Annotated[str, typer.Option(help="Why the video was sent back.")] = "",
) -> None:
    """Send a rendered video back to an earlier stage (e.g. after editing scene_manifest.json)."""
    p = _pipeline()
    _job(p, job_id)
    try:
        p.request_rework(job_id, JobState(stage), note)
    except (PipelineError, ValueError) as e:
        _abort(e)
    _report(p, p.run(job_id))


@app.command()
def export(
    job_id: str,
    dest: Annotated[Path | None, typer.Option(help="Copy the package to DEST/JOB_ID (never overwrites).")] = None,
    draft: Annotated[bool, typer.Option("--draft", help="Allow exporting a not-yet-approved video.")] = False,
) -> None:
    """Verify the output package and optionally copy it elsewhere."""
    p = _pipeline()
    job = _job(p, job_id)
    if job.state != JobState.COMPLETED and not draft:
        _abort(PipelineError(f"job is '{job.state}'; approve the video first or pass --draft"))
    check = pkg.check_package(job.output_dir)
    t = Table("file", "bytes")
    for name in pkg.PACKAGE_FILES:
        info = check["files"].get(name)
        t.add_row(name, str(info["bytes"]) if info else "[red]missing[/]")
    console.print(t)
    pkg.write_json(job.output_dir / "package_manifest.json", check)
    if dest:
        try:
            target = pkg.export_copy(job.output_dir, dest)
        except FileExistsError as e:
            _abort(e)
        console.print(f"[green]Copied to[/] {target}")
    console.print("[green]Package complete.[/]" if check["complete"] else f"[red]Incomplete:[/] {check['missing']}")


@app.command()
def claims(
    job_id: str,
    claim_id: Annotated[str | None, typer.Argument(help="Claim id to update, e.g. C2")] = None,
    status_: Annotated[
        str | None, typer.Option("--status", help="human_verified | human_rejected | conflicting")
    ] = None,
    note: Annotated[str, typer.Option(help="Your reasoning / what you checked.")] = "",
) -> None:
    """Review claims. Updating one creates a new (unapproved) script version."""
    p = _pipeline()
    job = _job(p, job_id)
    sv = p.load_version(job)
    if not claim_id:
        show_version(sv, job.id)
        return
    if status_ not in ("human_verified", "human_rejected", "conflicting"):
        _abort(ValueError("--status must be human_verified, human_rejected or conflicting"))
    if job.state != JobState.AWAITING_SCRIPT_APPROVAL:
        _abort(PipelineError("claims can be reviewed while the script awaits approval"))
    new_claims = []
    found = False
    for c in sv.research.claims:
        if c.id == claim_id:
            found = True
            c = c.model_copy(
                update={"status": ClaimStatus(str(status_)), "check_details": f"Human review: {note}".strip()}
            )
        new_claims.append(c)
    if not found:
        _abort(ValueError(f"no claim {claim_id}"))
    research = sv.research.model_copy(update={"claims": new_claims})
    p.db.update_job(job.id, approved_version=None, approved_hash=None)
    new = p.save_version(job, sv.script, research, "claim-review", f"{claim_id} -> {status_}")
    console.print(f"Saved v{new.version} with {claim_id} = {status_}.")


@app.command("approve-preview")
def approve_preview(job_id: str, yes: Annotated[bool, typer.Option("--yes", "-y")] = False) -> None:
    """Approve the low-resolution preview and start the full 1080x1920 render."""
    p = _pipeline()
    job = _job(p, job_id)
    if not yes:
        typer.confirm(f"Have you watched {job.output_dir / 'preview.mp4'}? Start the full render?", abort=True)
    try:
        p.approve_preview(job_id)
    except PipelineError as e:
        _abort(e)
    _report(p, p.run(job_id))


# --------------------------------------------------------------------------- voice-over


def _print_vo_check(chk) -> None:
    t = Table("check", "value", title=f"Voice-over: {Path(chk.path).name}")
    t.add_row("duration", f"{chk.duration:.1f}s ({chk.speech_seconds:.0f}s of speech)")
    t.add_row("format", f"{chk.codec}, {chk.sample_rate} Hz, {chk.channels} ch")
    t.add_row("peak / loudness", f"{chk.peak_dbfs} dBFS / {chk.integrated_lufs} LUFS")
    t.add_row("noise (SNR est.)", f"{chk.snr_estimate_db:.0f} dB")
    t.add_row("clipping", f"{chk.clipping_ratio:.3%}")
    t.add_row("silence start/end", f"{chk.leading_silence:.2f}s / {chk.trailing_silence:.2f}s")
    t.add_row("longest pause", f"{chk.longest_pause:.2f}s ({chk.pauses_over_1s} over 1 s)")
    console.print(t)
    for w in chk.warnings:
        console.print(f"[yellow]warning:[/] {w}")
    for e in chk.errors:
        console.print(f"[red]error:[/] {e}")
    console.print("[green]Usable.[/]" if chk.ok else "[red]Not usable - see errors above.[/]")


@app.command("voiceover-check")
def voiceover_check(file: Annotated[Path, typer.Argument(help="Audio file to check.")]) -> None:
    """Validate a voice-over recording (format, level, noise, clipping, silence, pauses)."""
    from reelforge.voice.voiceover import check_voiceover

    chk = check_voiceover(file)
    _print_vo_check(chk)
    if not chk.ok:
        raise typer.Exit(1)


@app.command("voiceover-record")
def voiceover_record(
    out: Annotated[Path | None, typer.Option(help="Output WAV (default voice_data/recordings/<time>.wav).")] = None,
    job: Annotated[str | None, typer.Option(help="Show this job's script to read, and attach the take.")] = None,
    script_file: Annotated[
        Path | None, typer.Option(exists=True, dir_okay=False, help="Show this script file's narration to read.")
    ] = None,
    device: Annotated[
        str, typer.Option(help="PulseAudio/PipeWire source (see `pactl list short sources`).")
    ] = "default",
    max_seconds: Annotated[int, typer.Option(min=10, max=300)] = 120,
) -> None:
    """Record a voice-over from the microphone (press Enter to stop), then check it."""
    import datetime as dt

    from reelforge.voice.voiceover import VoiceoverError, check_voiceover, record

    s = load_settings()
    p = _pipeline() if job else None
    if job and p:
        j = _job(p, job)
        sv = p.load_version(j, j.approved_version)
        console.print(
            Panel("\n\n".join(sec.text for sec in sv.script.sections), title=f"Read this ({sv.script.title})")
        )
    if script_file and not job:
        from reelforge.scripting.manual import parse_script_file

        sc, _, _ = parse_script_file(script_file)
        console.print(Panel("\n\n".join(sec.text for sec in sc.sections), title=f"Read this ({sc.title})"))
    target = out or s.voice_dir / "recordings" / f"{dt.datetime.now():%Y%m%d-%H%M%S}.wav"
    console.print("Tips: quiet room, 15-20 cm from the mic, read naturally; pauses are fine.")
    input("Press Enter to START recording...")
    for n in (3, 2, 1):
        console.print(f"  {n}...")
        time.sleep(0.7)
    console.print(f"[bold red]● Recording[/] (max {max_seconds}s) - press Enter to STOP")
    try:
        record(target, device=device, max_seconds=max_seconds)
    except VoiceoverError as e:
        _abort(e)
    console.print(f"Saved {target}")
    chk = check_voiceover(target)
    _print_vo_check(chk)
    console.print(f"Listen: ffplay -autoexit -nodisp {target}")
    if job and p and chk.ok and typer.confirm("Attach this take to the job and continue?", default=True):
        p.attach_voiceover(job, target)
        _report(p, p.run(job) if p.db.get_job(job).state != JobState.AWAITING_SCRIPT_APPROVAL else p.db.get_job(job))


@app.command()
def voiceover(
    job_id: str,
    file: Annotated[Path, typer.Option(help="Your recorded voice-over (wav/flac/m4a/mp3/ogg).")],
    max_pause: Annotated[float | None, typer.Option(help="Shorten pauses longer than this (s).")] = None,
    denoise: Annotated[bool, typer.Option("--denoise")] = False,
    no_trim: Annotated[bool, typer.Option("--no-trim")] = False,
    no_normalize: Annotated[bool, typer.Option("--no-normalize")] = False,
    caption_source: Annotated[str, typer.Option(help="auto | script | transcript")] = "auto",
    no_run: Annotated[bool, typer.Option("--no-run", help="Attach only; continue later with `resume`.")] = False,
) -> None:
    """Attach a recorded voice-over to a job. It becomes the timing source for captions, avatar,
    scene cuts and SFX; voice, captions, scenes and preview are redone."""
    p = _pipeline()
    _job(p, job_id)
    try:
        job = p.attach_voiceover(
            job_id,
            file,
            vo_max_pause=max_pause,
            vo_denoise=denoise,
            vo_trim=not no_trim,
            vo_normalize=not no_normalize,
            caption_source=caption_source,
        )
    except (PipelineError, ValueError) as e:
        _abort(e)
    console.print(f"[green]Voice-over attached[/] to {job.id} (state: {job.state}).")
    if job.state == JobState.AWAITING_SCRIPT_APPROVAL:
        console.print(f"Approve the script to continue: python -m reelforge.main approve-script {job.id}")
    elif not no_run:
        _report(p, p.run(job_id))


# --------------------------------------------------------------------------- voice


@app.command("voice-guide")
def voice_guide() -> None:
    """How to record reference audio for cloning your own voice."""
    from reelforge.voice.enrollment import CONSENT_STATEMENT, RECORDING_GUIDE

    console.print(RECORDING_GUIDE)
    console.print(f"Consent you will confirm:\n  {CONSENT_STATEMENT}")


@app.command("voice-enroll")
def voice_enroll(
    file: Annotated[
        list[Path], typer.Option(exists=True, dir_okay=False, help="Recording(s) of YOUR voice; repeatable.")
    ],
    profile: Annotated[str, typer.Option(help="Profile name.")] = "default",
    replace: Annotated[bool, typer.Option("--replace", help="Replace an existing profile.")] = False,
    i_consent: Annotated[
        bool, typer.Option("--i-consent", help="Confirm the consent statement non-interactively.")
    ] = False,
) -> None:
    """Check and store your voice recordings locally (git-ignored, never uploaded)."""
    from reelforge.voice.enrollment import CONSENT_STATEMENT, EnrollmentError, enroll

    if not i_consent:
        console.print(CONSENT_STATEMENT)
        i_consent = typer.confirm("Do you confirm?")
    s = load_settings()
    s.ensure_dirs()
    try:
        data = enroll(s.voice_dir, profile, file, consent=i_consent, replace=replace)
    except EnrollmentError as e:
        _abort(e)
    t = Table("clip", "seconds", "SNR dB", "peak dBFS", "clipping", "issues")
    for c in data["clips"]:
        q = c["quality"]
        t.add_row(
            c["original_name"],
            f"{c['trimmed_seconds']:.1f}",
            f"{q['snr_estimate_db']:.0f}",
            f"{q['peak_dbfs']:.1f}",
            f"{q['clipping_ratio']:.2%}",
            "; ".join(q["issues"]) or "ok",
        )
    console.print(t)
    ref = s.voice_dir / profile / "reference.wav"
    console.print(f"Reference clip ({data['reference_seconds']}s): {ref}")
    for prob in data["problems"]:
        console.print(f"[yellow]warning:[/] {prob}")
    console.print(f"Listen: [bold]ffplay -autoexit -nodisp {ref}[/]")
    console.print(f"Then approve it: [bold]uv run python -m reelforge.main voice-approve --profile {profile}[/]")


@app.command("voice-approve")
def voice_approve(profile: Annotated[str, typer.Option()] = "default") -> None:
    """Approve the reference recording after listening to it."""
    from reelforge.voice.enrollment import EnrollmentError, approve

    try:
        approve(load_settings().voice_dir, profile)
    except EnrollmentError as e:
        _abort(e)
    console.print(f"[green]Profile {profile!r} approved.[/] Test it: uv run python -m reelforge.main voice-test")


@app.command("voice-status")
def voice_status() -> None:
    """List enrolled voice profiles (cloning access is checked when `voice-test` or a clone job runs)."""
    from reelforge.voice.enrollment import list_profiles

    s = load_settings()
    profiles = list_profiles(s.voice_dir)
    if not profiles:
        console.print("No voice profiles enrolled. See `voice-guide`.")
    for d in profiles:
        console.print(
            f"{d['profile']}: {d['status']} · reference {d['reference_seconds']}s · "
            f"consent {d['consent']['confirmed_at']}"
        )


@app.command("voice-delete")
def voice_delete(
    profile: Annotated[str, typer.Option()] = "default", yes: Annotated[bool, typer.Option("--yes", "-y")] = False
) -> None:
    """Permanently delete a locally stored voice profile and its recordings."""
    from reelforge.voice.enrollment import delete

    s = load_settings()
    if not yes:
        typer.confirm(f"Delete {s.voice_dir / profile} and all its recordings?", abort=True)
    console.print("Deleted." if delete(s.voice_dir, profile) else "No such profile.")


@app.command("voice-test")
def voice_test(
    text: Annotated[str, typer.Option()] = "This is a quick test of my cloned voice for ReelForge.",
    profile: Annotated[str, typer.Option()] = "default",
    stock: Annotated[str | None, typer.Option(help="Test a stock voice instead of your clone.")] = None,
) -> None:
    """Synthesize a short sample with your cloned voice (or a stock voice)."""
    from reelforge.schemas import Script, ScriptSection
    from reelforge.voice.base import VoiceUnavailable
    from reelforge.voice.cloning import clone_engine
    from reelforge.voice.local_tts import stock_engine

    s = load_settings()
    try:
        engine = stock_engine(stock) if stock else clone_engine(s.voice_dir, profile)
    except VoiceUnavailable as e:
        _abort(e)
    out = s.data_dir / f"voice_test_{stock or profile}.wav"
    engine.synthesize(Script(title="t", sections=[ScriptSection(role="hook", text=text)]), out, 1, {})
    console.print(f"[green]Wrote[/] {out}  ({engine.voice_label})\nListen: ffplay -autoexit -nodisp {out}")


# --------------------------------------------------------------------------- environment


@app.command()
def doctor() -> None:
    """Check tools, models, renderer and credentials (never prints secret values)."""
    import importlib.util
    import platform

    s = load_settings()
    t = Table("check", "result")
    t.add_row("python", platform.python_version())
    from reelforge.rendering.remotion import node_bin_dir

    node_dir = node_bin_dir()
    for tool in ("ffmpeg", "ffprobe", "node", "npx"):
        path = shutil.which(tool) or (str(node_dir / tool) if node_dir and tool in ("node", "npx") else None)
        ver = ""
        if path and tool in ("ffmpeg", "node"):
            arg = "-version" if tool == "ffmpeg" else "--version"
            ver = subprocess.run([path, arg], capture_output=True, text=True).stdout.splitlines()[0][:50]
        t.add_row(tool, f"[green]{ver or path}[/]" if path else "[red]missing[/]")
    from reelforge.rendering.remotion import remotion_version

    rv = remotion_version(s.renderer_dir)
    t.add_row(
        "remotion", f"[green]{rv}[/]" if rv != "unknown" else "[red]not installed (cd renderer && npm install)[/]"
    )
    shell = list(
        (s.renderer_dir / "node_modules" / ".remotion").glob("chrome-headless-shell/*/*/chrome-headless-shell")
    )
    t.add_row("chrome headless shell", "[green]installed[/]" if shell else "[yellow]will download on first render[/]")
    for mod, extra in (("faster_whisper", "transcribe"), ("pocket_tts", "voice")):
        ok = importlib.util.find_spec(mod) is not None
        t.add_row(mod, "[green]installed[/]" if ok else f"[red]missing (uv sync --extra {extra})[/]")
    hub = Path.home() / ".cache" / "huggingface" / "hub"
    wm = hub / f"models--Systran--faster-whisper-{s.whisper_model}"
    t.add_row(
        f"whisper model {s.whisper_model}", "[green]cached[/]" if wm.exists() else "[yellow]downloads on first use[/]"
    )
    for k, v in s.public_dict().items():
        if k.endswith("_api_key"):
            t.add_row(k.upper(), "[green]set[/]" if v == "set" else "[dim]missing[/]")
    t.add_row("ollama model", s.ollama_model or "[dim]not configured (optional)[/]")
    t.add_row(
        "REELFORGE_CONTACT",
        "[green]set[/]" if s.research_contact else "[yellow]missing: Wikipedia API may answer 403 (robot policy)[/]",
    )
    from reelforge.voice.enrollment import list_profiles

    profs = list_profiles(s.voice_dir)
    t.add_row("voice profiles", ", ".join(f"{d['profile']} ({d['status']})" for d in profs) or "[dim]none[/]")
    free = shutil.disk_usage(s.output_dir if s.output_dir.exists() else s.project_root).free / 1e9
    t.add_row("free disk", f"{free:.1f} GB")
    console.print(t)


@app.command()
def benchmark(
    seconds: Annotated[int, typer.Option(min=2, max=12, help="Sample length (the sample is 12 s).")] = 6,
    scale: Annotated[float, typer.Option(min=0.2, max=1.0)] = 1.0,
) -> None:
    """Render the built-in sample composition to measure render speed on this machine."""
    from reelforge.rendering.remotion import check_renderer

    s = load_settings()
    check_renderer(s.renderer_dir)
    s.ensure_dirs()
    out = s.data_dir / "benchmark.mp4"
    frames = seconds * 30
    cmd = [
        "npx",
        "remotion",
        "render",
        "src/index.ts",
        "Reel",
        str(out),
        "--muted",
        f"--frames=0-{frames - 1}",
        f"--concurrency={s.render_concurrency}",
        f"--scale={scale}",
        "--log=error",
    ]
    from reelforge.rendering.remotion import node_env

    t0 = time.time()
    subprocess.run(cmd, cwd=s.renderer_dir, check=True, env=node_env())
    el = time.time() - t0
    console.print(
        f"{frames} frames at scale {scale} in {el:.1f}s → {frames / el:.1f} fps (incl. bundling). "
        f"A 55 s reel ≈ {1650 / (frames / el) / 60:.1f} min."
    )


def main() -> None:  # console-script entry point
    app()


if __name__ == "__main__":
    app()
