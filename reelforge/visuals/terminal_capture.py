"""Record real terminal sessions for use as footage.

`capture(commands)` actually runs each command on this machine (bash, with a timeout), and stores
the command, its real output and timing in a small JSON "cast". The renderer replays a cast as
terminal footage. Nothing is fabricated: if a command fails, its real error is what gets shown.

Safety: commands are only ever run by the explicit `capture-terminal` CLI command. The scene
planner never executes anything - scripts can only *reference* an existing cast file.
"""

from __future__ import annotations

import getpass
import json
import os
import platform
import re
import subprocess
import time
from pathlib import Path

from pydantic import BaseModel, Field

from reelforge.schemas import utcnow

MAX_OUTPUT_LINES = 12
MAX_LINE = 46


class CastStep(BaseModel):
    command: str
    output: list[str]
    exit_code: int
    seconds: float


class TerminalCast(BaseModel):
    kind: str = "reelforge-terminal-cast"
    version: int = 1
    recorded_at: str
    host: str  # e.g. "Linux x86_64, Python 3.12" - no hostname or username
    cwd: str
    steps: list[CastStep] = Field(min_length=1)


def _sanitize(text: str) -> str:
    """Hide the home directory and username so footage can be published."""
    home = str(Path.home())
    text = text.replace(home, "~")
    user = getpass.getuser()
    if user and len(user) > 2:
        text = re.sub(rf"\b{re.escape(user)}\b", "user", text)
    return text


def _clip(line: str) -> str:
    line = line.rstrip().expandtabs(4)
    return line if len(line) <= MAX_LINE else line[: MAX_LINE - 1] + "…"


def capture(commands: list[str], cwd: Path, timeout: float = 60.0, env: dict[str, str] | None = None) -> TerminalCast:
    steps = []
    for cmd in commands:
        t0 = time.time()
        proc = subprocess.run(
            ["bash", "-c", cmd],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, **(env or {}), "COLUMNS": str(MAX_LINE), "NO_COLOR": "1"},
            check=False,
        )
        out = (proc.stdout + proc.stderr).splitlines()
        lines = [_clip(_sanitize(x)) for x in out if x.strip()][:MAX_OUTPUT_LINES]
        steps.append(
            CastStep(
                command=_sanitize(cmd), output=lines, exit_code=proc.returncode, seconds=round(time.time() - t0, 2)
            )
        )
    host = f"{platform.system()} {platform.machine()}, Python {platform.python_version()}"
    return TerminalCast(recorded_at=utcnow(), host=host, cwd=cwd.name, steps=steps)  # folder name only


def load_cast(path: Path) -> TerminalCast:
    data = json.loads(path.read_text())
    cast = TerminalCast.model_validate(data)
    if cast.kind != "reelforge-terminal-cast":
        raise ValueError(f"{path} is not a ReelForge terminal cast")
    return cast
