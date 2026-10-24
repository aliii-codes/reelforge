"""ReelForge web UI — a local web app in place of the old desktop GUI.

Layout: a sidebar of reels; for the selected reel a title, a 4-step tracker
(Script → Voice → Preview → Final), one "next step" card, and the script / frames / checks
behind tabs. Videos play in the page; voice is recorded in the browser.

Every action runs the existing CLI (`python -m reelforge.main ...`) as a subprocess, so the web
UI shares the CLI's behaviour, SQLite state, resumability and logs. One step runs at a time.

Standard library only. Binds to 127.0.0.1; mutating requests need an `X-ReelForge` header,
which other sites can't send without a CORS preflight this server never approves.

    python -m reelforge.web            (or: reelforge-web)
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import asdict
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from reelforge.config import PROJECT_ROOT, Settings, load_settings
from reelforge.database import Database, JobRecord
from reelforge.jobs.state import JobState

STATIC = Path(__file__).parent / "static"
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"


def cli_python() -> str:
    """The project's venv Python when there is one, so steps get the pipeline's dependencies even if
    the server itself was started with the system Python (the server needs only the standard library)."""
    return str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable


ALLOWED_COMMANDS = {
    "create",
    "pick",
    "voice",
    "voiceover",
    "approve-script",
    "approve-preview",
    "approve-video",
    "resume",
}
AUDIO_EXTS = {".wav", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".webm"}
STEPS = ["Script", "Voice", "Preview", "Final"]
STEP_OF_STATE = {
    JobState.CREATED: 0,
    JobState.RESEARCHING: 0,
    JobState.AWAITING_SCRIPT_APPROVAL: 0,
    JobState.GENERATING_VOICE: 1,
    JobState.ALIGNING_CAPTIONS: 1,
    JobState.PLANNING_SCENES: 1,
    JobState.PREVIEWING: 2,
    JobState.AWAITING_PREVIEW_APPROVAL: 2,
    JobState.RENDERING: 3,
    JobState.AWAITING_VIDEO_APPROVAL: 3,
    JobState.COMPLETED: 4,
}
WORKING_TEXT = {
    JobState.RESEARCHING: "Researching and writing the script",
    JobState.GENERATING_VOICE: "Processing your voice and transcribing it",
    JobState.ALIGNING_CAPTIONS: "Timing the captions to your voice",
    JobState.PLANNING_SCENES: "Planning scenes on the beats of your voice",
    JobState.PREVIEWING: "Rendering a quick preview",
    JobState.RENDERING: "Rendering the full-quality video",
}


def needs_recording(j: JobRecord) -> bool:
    return j.config.get("voice_mode") == "file" and not j.config.get("narration_file")


def needs_voice(j: JobRecord) -> bool:
    return j.config.get("voice_mode") == "ask" or needs_recording(j)


def needs_pick(j: JobRecord, n_versions: int) -> bool:
    return j.state == JobState.AWAITING_SCRIPT_APPROVAL and n_versions > 1 and j.config.get("picked_version") is None


def status_of(j: JobRecord) -> tuple[str, str]:
    """Short human status and its tone (red / green / orange / blue)."""
    st = j.state
    if st == JobState.FAILED:
        return "Needs attention", "red"
    if st == JobState.COMPLETED:
        return "Ready to post", "green"
    if st == JobState.AWAITING_SCRIPT_APPROVAL:
        if j.config.get("picked_version") is None and j.source_kind == "topic":
            return "Pick a script", "orange"
        return ("Choose the voice" if needs_voice(j) else "Review the script"), "orange"
    if st == JobState.AWAITING_PREVIEW_APPROVAL:
        return "Preview ready", "orange"
    if st == JobState.AWAITING_VIDEO_APPROVAL:
        return "Final video ready", "orange"
    return "Working…", "blue"


def nice_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%-d %b, %H:%M")
    except ValueError:
        return iso[:16]


def clean_title(j: JobRecord) -> str:
    return j.title.replace(" (voice-over demo)", "")


# --------------------------------------------------------------------------- CLI runner


class Runner:
    """Runs one CLI command at a time and keeps its output and render progress."""

    _PCT = re.compile(r"rendered (\d+)/(\d+) frames \((\d+)%\)")

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.proc: subprocess.Popen[str] | None = None
        self.log: collections.deque[str] = collections.deque(maxlen=4000)
        self.seq = 0  # total lines ever appended, so clients can ask for "lines after n"
        self.heading = ""
        self.percent: int | None = None
        self.progress_text = ""
        self.last_exit: int | None = None

    @property
    def busy(self) -> bool:
        return self.proc is not None

    def _append(self, line: str) -> None:
        self.log.append(line)
        self.seq += 1

    def start(self, args: list[str]) -> None:
        with self.lock:
            if self.proc is not None:
                raise RuntimeError("Please wait for the current step to finish.")
            self._append(f"$ reelforge {' '.join(args)}")
            self.heading, self.percent, self.progress_text, self.last_exit = "", None, "", None
            env = {**os.environ, "COLUMNS": "110", "PYTHONUNBUFFERED": "1"}
            self.proc = subprocess.Popen(
                [cli_python(), "-m", "reelforge.main", *args],
                cwd=PROJECT_ROOT,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
            )
        threading.Thread(target=self._pump, args=(self.proc,), daemon=True).start()

    def _pump(self, proc: subprocess.Popen[str]) -> None:
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.rstrip()
            if not line.strip():
                continue
            self._append(line)
            m = self._PCT.search(line)
            if m:
                self.percent = int(m.group(3))
                self.progress_text = f"{m.group(3)}% — frame {m.group(1)} of {m.group(2)}"
            elif line.startswith("== "):
                self.percent = None
                stage = line.strip("= ").strip()
                with contextlib.suppress(ValueError):
                    self.heading = WORKING_TEXT.get(JobState(stage), "Working")
        code = proc.wait()
        self._append("✓ done" if code == 0 else f"✕ exited with code {code}")
        with self.lock:
            self.proc, self.last_exit = None, code

    def stop(self) -> None:
        proc = self.proc
        if proc is None:
            return
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
        self._append("Stopped. Use Continue to pick up from the last finished step.")

    def snapshot(self, since: int) -> dict:
        lines = list(self.log)
        first = self.seq - len(lines)
        return {
            "busy": self.busy,
            "heading": self.heading,
            "percent": self.percent,
            "progress_text": self.progress_text,
            "last_exit": self.last_exit,
            "seq": self.seq,
            "lines": lines[max(0, since - first) :],
        }


# --------------------------------------------------------------------------- views


def script_view(db: Database, j: JobRecord) -> dict:
    rows = db.script_versions(j.id)
    if not rows:
        return {"kind": "empty"}
    if needs_pick(j, len(rows)):
        drafts = []
        for r in rows:
            data = json.loads(Path(r["path"]).read_text())
            note = data.get("note", "")
            claims = data.get("research", {}).get("claims", [])
            sources = data.get("research", {}).get("sources", [])
            body = " ".join(sec["text"] for sec in data["script"]["sections"])
            drafts.append(
                {
                    "version": data["version"],
                    "angle": note.split(" · ")[1] if note.count(" · ") >= 1 else "",
                    "title": data["script"]["title"],
                    "body": body,
                    "words": len(body.split()),
                    "claims_ok": sum(1 for c in claims if c["status"] in ("auto_supported", "human_verified")),
                    "claims": len(claims),
                    "no_sources": not any(src.get("fetched") for src in sources),
                }
            )
        return {"kind": "drafts", "drafts": drafts}
    picked = j.approved_version or j.config.get("picked_version")
    row = next((r for r in rows if r["version"] == picked), rows[-1])
    data = json.loads(Path(row["path"]).read_text())
    claims = data.get("research", {}).get("claims", [])
    return {
        "kind": "script",
        "sections": [{"role": s["role"], "text": s["text"]} for s in data["script"]["sections"]],
        "claims_ok": sum(1 for c in claims if c["status"] in ("auto_supported", "human_verified")),
        "claims": len(claims),
    }


def checks_view(j: JobRecord) -> list[dict]:
    """Groups of {ok: True/False/None, text} items from the validation and takes reports."""
    out = j.output_dir
    groups: list[dict] = []
    for name, title in (("validation_report.json", "Final video"), ("preview_report.json", "Preview")):
        p = out / name
        if not p.exists():
            continue
        rep = json.loads(p.read_text())
        video = rep.get("video", rep)
        s = video.get("summary", {})
        items = []
        sound = "with sound" if s.get("audio_codec") else "no sound"
        items.append(
            {
                "ok": video.get("ok"),
                "text": f"{s.get('width')}×{s.get('height')}, {s.get('fps')} fps, {s.get('duration')} s, {sound}",
            }
        )
        rc = video.get("render_completion") or {}
        if rc:
            items.append(
                {
                    "ok": rc.get("frames") == rc.get("expected"),
                    "text": f"All frames rendered ({rc.get('frames')}/{rc.get('expected')})",
                }
            )
        ct = video.get("caption_timing") or {}
        if ct.get("first_word_offset_s") is not None:
            off = abs(ct["first_word_offset_s"])
            items.append(
                {"ok": off <= 0.3, "text": f"Captions in sync with your voice (first word off by {off:.2f} s)"}
            )
        items += [{"ok": False, "text": e} for e in video.get("errors", [])]
        items += [{"ok": None, "text": w} for w in video.get("warnings", [])]
        groups.append({"title": title, "items": items})
    takes = out / "work" / "takes" / "takes_report.json"
    if takes.exists():
        items = []
        for t in json.loads(takes.read_text()):
            items.append(
                {
                    "ok": t["wer"] < 0.05,
                    "text": f"Take {t['index']}: {t['duration']:.0f} s, {100 - t['wer'] * 100:.0f}% of the script heard",
                }
            )
            items += [{"ok": None, "text": i} for i in t["issues"][:3]]
        groups.append({"title": "Voice", "items": items})
    return groups


def media_of(j: JobRecord) -> dict:
    out = j.output_dir
    sheets = [p for p in (out / "contact_sheet.jpg", out / "preview_contact_sheet.jpg") if p.exists()]
    newest = max(sheets, key=lambda p: p.stat().st_mtime) if sheets else None

    def url(p: Path | None) -> str | None:
        return f"/files/{j.id}/{p.name}?t={int(p.stat().st_mtime)}" if p is not None and p.exists() else None

    return {
        "frames": url(newest),
        "preview": url(out / "preview.mp4"),
        "final": url(out / "final_reel.mp4"),
    }


def action(label: str, kind: str, primary: bool = False, **extra: object) -> dict:
    return {"label": label, "kind": kind, "primary": primary, **extra}


def next_step(db: Database, j: JobRecord, runner: Runner) -> dict:
    """The one card that says what to do next, with only the buttons that make sense now."""
    jid, st = j.id, j.state
    if runner.busy:
        return {
            "heading": (runner.heading or WORKING_TEXT.get(st, "Working")) + "…",
            "body": runner.progress_text or "You can keep using your computer. This page updates by itself.",
            "working": True,
            "percent": runner.percent,
            "actions": [action("Stop", "stop")],
        }
    rows = db.script_versions(jid)
    if needs_pick(j, len(rows)):
        return {
            "heading": "Pick your script",
            "body": f"{len(rows)} drafts with different angles - read them below, then choose one.",
            "actions": [
                action(
                    f"Use Draft {r['version']}", "run", True, args=["pick", jid, str(r["version"]), "--no-interactive"]
                )
                for r in rows
            ],
        }
    if st == JobState.AWAITING_SCRIPT_APPROVAL and needs_voice(j):
        return {
            "heading": "How should it be narrated?",
            "body": "Your own voice sounds most natural. The AI voice is a synthetic stock voice and is "
            "labelled as not you.",
            "actions": [
                action("Record Voice", "record", True),
                action("Use an audio file…", "upload"),
                action(
                    "Use AI voice",
                    "run",
                    args=["voice", jid, "--ai", "--yes"],
                    confirm="The reel will be narrated by a synthetic stock voice, not yours. It is labelled as "
                    "an AI voice in the reel's metadata.\n\nUse the AI voice?",
                ),
            ],
        }
    if st == JobState.AWAITING_SCRIPT_APPROVAL:
        acts = [action("Approve Script", "run", True, args=["approve-script", jid, "--yes"])]
        if j.config.get("voice_mode") == "file":
            acts.append(action("Re-record voice", "record"))
        return {
            "heading": "Approve the script",
            "body": "Read it below. Approving starts the voice, captions and a quick preview.",
            "actions": acts,
        }
    if st == JobState.AWAITING_PREVIEW_APPROVAL:
        return {
            "heading": "Check the preview",
            "body": "Watch the quick, low-resolution preview. If it looks right, render the full-quality "
            "video (about 5–10 minutes).",
            "actions": [
                action("Render Full Video", "run", True, args=["approve-preview", jid, "--yes"]),
                action("Play Preview", "play", video="preview"),
                action("Re-record voice", "record"),
            ],
        }
    if st == JobState.AWAITING_VIDEO_APPROVAL:
        return {
            "heading": "Review the final video",
            "body": "Watch it once more, then approve it for posting. Nothing is posted automatically.",
            "actions": [
                action("Approve", "run", True, args=["approve-video", jid, "--yes"]),
                action("Play Video", "play", video="final"),
            ],
        }
    if st == JobState.COMPLETED:
        return {
            "heading": "Ready to post",
            "body": "Your reel, cover, caption and hashtags are in the folder. Upload them yourself.",
            "actions": [action("Show in Folder", "folder", True), action("Play Video", "play", video="final")],
        }
    if st == JobState.FAILED:
        msg = (j.last_error or "").split(":", 1)[-1].strip()
        return {
            "heading": "Something went wrong",
            "body": (msg[:220] + "…") if len(msg) > 220 else msg,
            "actions": [action("Try Again", "run", True, args=["resume", jid]), action("Show details", "log")],
        }
    return {  # interrupted while working
        "heading": "Paused",
        "body": "This step was interrupted. Continue from where it stopped.",
        "actions": [action("Continue", "run", True, args=["resume", jid])],
    }


def job_summary(j: JobRecord) -> dict:
    text, tone = status_of(j)
    return {"id": j.id, "title": clean_title(j), "status": text, "tone": tone, "created": nice_time(j.created_at)}


def job_detail(db: Database, j: JobRecord, runner: Runner) -> dict:
    n_versions = len(db.script_versions(j.id))
    step = STEP_OF_STATE.get(j.state, STEP_OF_STATE.get(j.failed_stage or JobState.CREATED, 0))
    if j.state == JobState.AWAITING_SCRIPT_APPROVAL and not needs_pick(j, n_versions) and needs_voice(j):
        step = 1
    return {
        **job_summary(j),
        "state": j.state.value,
        "step": step,
        "failed": j.state == JobState.FAILED,
        "output_dir": str(j.output_dir),
        "next": next_step(db, j, runner),
        "script": script_view(db, j),
        "checks": checks_view(j),
        "media": media_of(j),
        "show_frames": j.state
        in (JobState.AWAITING_PREVIEW_APPROVAL, JobState.AWAITING_VIDEO_APPROVAL, JobState.COMPLETED),
    }


def create_args(body: dict) -> list[str]:
    """CLI arguments for the New Reel form. Raises ValueError with a user-facing message."""
    if body.get("source") == "script":
        path = Path(str(body.get("script_file", "")).strip()).expanduser()
        if not path.is_file():
            raise ValueError("Choose an existing script file.")
        a = ["create", "--script-file", str(path)]
    else:
        topic = str(body.get("topic", "")).strip()
        if len(topic) < 4:
            raise ValueError("Type the topic of the reel.")
        a = ["create", "--topic", topic]
    a += ["--voice", "ask", "--no-interactive"]
    handle = str(body.get("handle", "")).strip()
    if handle:
        a += ["--handle", handle]
    if not body.get("preview_gate", True):
        a.append("--no-preview-gate")
    return a


def voice_args(j: JobRecord, path: Path) -> list[str]:
    if j.state == JobState.AWAITING_SCRIPT_APPROVAL:
        # sets the voice, approves the chosen script and runs through to the preview
        return ["voice", j.id, "--file", str(path)]
    return ["voiceover", j.id, "--file", str(path)]


def save_recording(settings: Settings, data: bytes, ext: str) -> tuple[Path, dict]:
    """Store an uploaded recording as WAV under voice_data/recordings and check it."""
    from reelforge.voice.voiceover import SR, check_voiceover

    folder = settings.voice_dir / "recordings"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    raw = folder / f"{stamp}-upload{ext}"
    raw.write_bytes(data)
    wav = folder / f"{stamp}.wav"
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-ac", "2", "-ar", str(SR), "-c:a", "pcm_s16le", str(wav)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise ValueError("Couldn't read that audio: " + (proc.stderr.strip()[:200] or "ffmpeg failed"))
    raw.unlink(missing_ok=True)
    chk = check_voiceover(wav)
    return wav, {
        "ok": chk.ok,
        "duration": chk.duration,
        "quiet": chk.snr_estimate_db >= 25,
        "errors": chk.errors,
        "warnings": chk.warnings,
        "detail": asdict(chk),
    }


def open_folder(path: Path) -> None:
    opener = shutil.which("xdg-open") or shutil.which("open")
    if opener:
        subprocess.Popen([opener, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# --------------------------------------------------------------------------- HTTP


class App:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        settings.ensure_dirs()
        self.db = Database(settings.db_path)
        self.runner = Runner()

    def job(self, job_id: str) -> JobRecord:
        return self.db.get_job(job_id)


class Handler(BaseHTTPRequestHandler):
    app: App  # set on the subclass made by make_server
    server_version = "ReelForge"

    def log_message(self, fmt: str, *args: object) -> None:  # quiet: the page polls every second
        pass

    # ------------------------------------------------------------ helpers

    def _json(self, obj: object, status: int = 200) -> None:
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, message: str, status: int = 400) -> None:
        self._json({"error": message}, status)

    def _body(self) -> bytes:
        return self.rfile.read(int(self.headers.get("Content-Length") or 0))

    def _send_file(self, path: Path) -> None:
        size = path.stat().st_size
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        start, end = 0, size - 1
        rng = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if rng and (rng.group(1) or rng.group(2)):
            if rng.group(1):
                start = int(rng.group(1))
                end = min(int(rng.group(2)), size - 1) if rng.group(2) else size - 1
            else:
                start = max(0, size - int(rng.group(2)))
            if start > end:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            self.send_response(HTTPStatus.PARTIAL_CONTENT)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        with path.open("rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(1 << 16, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                left -= len(chunk)

    # ------------------------------------------------------------ GET

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        url = urlparse(self.path)
        parts = [unquote(p) for p in url.path.split("/") if p]
        app = self.app
        try:
            if not parts:
                return self._send_file(STATIC / "index.html")
            if parts == ["api", "state"]:
                since = int(dict(q.split("=", 1) for q in url.query.split("&") if "=" in q).get("since", 0))
                jobs = app.db.list_jobs()
                return self._json(
                    {
                        "jobs": [job_summary(j) for j in jobs],
                        "runner": app.runner.snapshot(since),
                        "defaults": {
                            "handle": app.settings.handle,
                            "script_file": str(PROJECT_ROOT / "examples" / "draft3_script.txt"),
                        },
                    }
                )
            if len(parts) == 3 and parts[:2] == ["api", "jobs"]:
                return self._json(job_detail(app.db, app.job(parts[2]), app.runner))
            if len(parts) == 3 and parts[0] == "files":
                root = app.job(parts[1]).output_dir.resolve()
                path = (root / parts[2]).resolve()
                if path.parent != root or not path.is_file():
                    return self._error("Not found", 404)
                return self._send_file(path)
            if len(parts) == 2 and parts[0] == "static" and (STATIC / parts[1]).is_file():
                return self._send_file(STATIC / parts[1])
            self._error("Not found", 404)
        except KeyError:
            self._error("No such reel", 404)

    # ------------------------------------------------------------ POST

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        if self.headers.get("X-ReelForge") != "1":
            return self._error("Forbidden", 403)
        parts = [unquote(p) for p in urlparse(self.path).path.split("/") if p]
        app = self.app
        try:
            if parts == ["api", "create"]:
                app.runner.start(create_args(json.loads(self._body() or b"{}")))
                return self._json({"ok": True})
            if parts == ["api", "run"]:
                args = json.loads(self._body() or b"{}").get("args") or []
                if not args or args[0] not in ALLOWED_COMMANDS or not all(isinstance(a, str) for a in args):
                    return self._error("That command isn't available here.")
                app.runner.start(args)
                return self._json({"ok": True})
            if parts == ["api", "stop"]:
                app.runner.stop()
                return self._json({"ok": True})
            if len(parts) == 3 and parts[:2] == ["api", "recording"]:
                ext = "." + parts[2].lower().lstrip(".")
                if ext not in AUDIO_EXTS:
                    return self._error("Use a WAV, FLAC, M4A, MP3, OGG, Opus or WebM audio file.")
                path, check = save_recording(app.settings, self._body(), ext)
                return self._json({"path": str(path), "name": path.name, "check": check})
            if len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] == "voice":
                j = app.job(parts[2])
                name = json.loads(self._body() or b"{}").get("name", "")
                path = app.settings.voice_dir / "recordings" / Path(name).name
                if not name or not path.is_file():
                    return self._error("That recording is gone - record it again.")
                app.runner.start(voice_args(j, path))
                return self._json({"ok": True})
            if len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] == "folder":
                open_folder(app.job(parts[2]).output_dir)
                return self._json({"ok": True})
            self._error("Not found", 404)
        except KeyError:
            self._error("No such reel", 404)
        except (ValueError, RuntimeError) as e:
            self._error(str(e), 409 if isinstance(e, RuntimeError) else 400)


def make_server(settings: Settings, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    handler = type("ReelForgeHandler", (Handler,), {"app": App(settings)})
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="ReelForge web UI")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1", help="keep 127.0.0.1 unless you know why not")
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    a = parser.parse_args()
    server = make_server(load_settings(), a.host, a.port)
    url = f"http://{a.host}:{server.server_address[1]}/"
    print(f"ReelForge is running at {url}  (Ctrl+C to quit)")
    if not a.no_browser:
        threading.Timer(0.5, webbrowser.open, (url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping…")
    finally:
        server.app.runner.stop()  # type: ignore[attr-defined]
        server.server_close()


if __name__ == "__main__":
    main()
