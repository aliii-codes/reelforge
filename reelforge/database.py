"""SQLite persistence for jobs, stage runs, script versions and events.

Media lives on disk under the job's output directory; the database stores only paths,
states, hashes and small JSON documents.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from reelforge.jobs.state import JobState, check_transition
from reelforge.schemas import ScriptVersion, utcnow

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    topic TEXT NOT NULL DEFAULT '',
    source_kind TEXT NOT NULL,              -- 'topic' | 'script'
    state TEXT NOT NULL,
    failed_stage TEXT,
    last_error TEXT,
    output_dir TEXT NOT NULL,
    config_json TEXT NOT NULL,
    approved_version INTEGER,
    approved_hash TEXT,
    selected_take INTEGER,
    video_approved_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS script_versions (
    job_id TEXT NOT NULL REFERENCES jobs(id),
    version INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    origin TEXT NOT NULL,
    path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    approved_at TEXT,
    PRIMARY KEY (job_id, version)
);
CREATE TABLE IF NOT EXISTS stage_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(id),
    stage TEXT NOT NULL,
    status TEXT NOT NULL,                   -- 'running' | 'succeeded' | 'failed'
    started_at TEXT NOT NULL,
    finished_at TEXT,
    seconds REAL,
    error TEXT,
    details_json TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    at TEXT NOT NULL,
    kind TEXT NOT NULL,
    message TEXT NOT NULL
);
"""


@dataclass
class JobRecord:
    id: str
    title: str
    topic: str
    source_kind: str
    state: JobState
    failed_stage: JobState | None
    last_error: str | None
    output_dir: Path
    config: dict
    approved_version: int | None
    approved_hash: str | None
    selected_take: int | None
    video_approved_at: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> JobRecord:
        return cls(
            id=row["id"],
            title=row["title"],
            topic=row["topic"],
            source_kind=row["source_kind"],
            state=JobState(row["state"]),
            failed_stage=JobState(row["failed_stage"]) if row["failed_stage"] else None,
            last_error=row["last_error"],
            output_dir=Path(row["output_dir"]),
            config=json.loads(row["config_json"]),
            approved_version=row["approved_version"],
            approved_hash=row["approved_hash"],
            selected_take=row["selected_take"],
            video_approved_at=row["video_approved_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class JobNotFound(KeyError):
    pass


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        try:
            yield con
            con.commit()
        finally:
            con.close()

    # ----------------------------------------------------------------- jobs

    def create_job(
        self, job_id: str, title: str, topic: str, source_kind: str, output_dir: Path, config: dict
    ) -> JobRecord:
        now = utcnow()
        with self.connect() as con:
            con.execute(
                "INSERT INTO jobs (id, title, topic, source_kind, state, output_dir, config_json, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    job_id,
                    title,
                    topic,
                    source_kind,
                    JobState.CREATED.value,
                    str(output_dir),
                    json.dumps(config),
                    now,
                    now,
                ),
            )
        self.log(job_id, "created", f"job created from {source_kind}")
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> JobRecord:
        with self.connect() as con:
            row = con.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise JobNotFound(job_id)
        return JobRecord.from_row(row)

    def list_jobs(self) -> list[JobRecord]:
        with self.connect() as con:
            rows = con.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
        return [JobRecord.from_row(r) for r in rows]

    def set_state(
        self, job_id: str, target: JobState, *, error: str | None = None, failed_stage: JobState | None = None
    ) -> JobRecord:
        job = self.get_job(job_id)
        check_transition(job.state, target)
        with self.connect() as con:
            con.execute(
                "UPDATE jobs SET state = ?, failed_stage = ?, last_error = ?, updated_at = ? WHERE id = ?",
                (
                    target.value,
                    failed_stage.value if failed_stage else None,
                    error if target == JobState.FAILED else None,
                    utcnow(),
                    job_id,
                ),
            )
        self.log(job_id, "state", f"{job.state} -> {target}" + (f" ({error})" if error else ""))
        return self.get_job(job_id)

    def update_job(self, job_id: str, **fields: object) -> JobRecord:
        allowed = {"title", "config_json", "approved_version", "approved_hash", "selected_take", "video_approved_at"}
        bad = set(fields) - allowed
        if bad:
            raise ValueError(f"cannot update fields {bad}")
        if not fields:
            return self.get_job(job_id)
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self.connect() as con:
            con.execute(f"UPDATE jobs SET {cols}, updated_at = ? WHERE id = ?", (*fields.values(), utcnow(), job_id))
        return self.get_job(job_id)

    # ----------------------------------------------------------------- script versions

    def add_script_version(self, job_id: str, sv: ScriptVersion, path: Path) -> None:
        with self.connect() as con:
            con.execute(
                "INSERT INTO script_versions (job_id, version, sha256, origin, path, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (job_id, sv.version, sv.content_hash(), sv.origin, str(path), sv.created_at),
            )

    def script_versions(self, job_id: str) -> list[sqlite3.Row]:
        with self.connect() as con:
            return con.execute("SELECT * FROM script_versions WHERE job_id = ? ORDER BY version", (job_id,)).fetchall()

    def mark_version_approved(self, job_id: str, version: int, sha256: str) -> None:
        now = utcnow()
        with self.connect() as con:
            con.execute(
                "UPDATE script_versions SET approved_at = ? WHERE job_id = ? AND version = ?", (now, job_id, version)
            )
            con.execute(
                "UPDATE jobs SET approved_version = ?, approved_hash = ?, updated_at = ? WHERE id = ?",
                (version, sha256, now, job_id),
            )

    # ----------------------------------------------------------------- stage runs / events

    def start_stage(self, job_id: str, stage: JobState) -> int:
        with self.connect() as con:
            cur = con.execute(
                "INSERT INTO stage_runs (job_id, stage, status, started_at) VALUES (?, ?, 'running', ?)",
                (job_id, stage.value, utcnow()),
            )
            return int(cur.lastrowid or 0)

    def finish_stage(
        self, run_id: int, ok: bool, seconds: float, error: str | None = None, details: dict | None = None
    ) -> None:
        with self.connect() as con:
            con.execute(
                "UPDATE stage_runs SET status = ?, finished_at = ?, seconds = ?, error = ?, details_json = ? WHERE id = ?",
                (
                    "succeeded" if ok else "failed",
                    utcnow(),
                    round(seconds, 2),
                    error,
                    json.dumps(details or {}),
                    run_id,
                ),
            )

    def stage_runs(self, job_id: str) -> list[sqlite3.Row]:
        with self.connect() as con:
            return con.execute("SELECT * FROM stage_runs WHERE job_id = ? ORDER BY id", (job_id,)).fetchall()

    def log(self, job_id: str, kind: str, message: str) -> None:
        with self.connect() as con:
            con.execute(
                "INSERT INTO events (job_id, at, kind, message) VALUES (?, ?, ?, ?)", (job_id, utcnow(), kind, message)
            )

    def events(self, job_id: str) -> list[sqlite3.Row]:
        with self.connect() as con:
            return con.execute("SELECT * FROM events WHERE job_id = ? ORDER BY id", (job_id,)).fetchall()
