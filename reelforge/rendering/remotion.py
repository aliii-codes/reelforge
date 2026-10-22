"""Run the Remotion project in `renderer/` from Python.

Contract: Python writes a validated SceneManifest JSON; Remotion receives it via `--props` and
the job's `work/public` folder via `--public-dir`. Video is rendered muted; FFmpeg adds the
mixed audio afterwards.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


class RendererUnavailable(RuntimeError):
    pass


@dataclass
class RenderResult:
    output: Path
    seconds: float
    command: list[str]


def _version_key(p: Path) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", p.name)) or (0,)


def node_bin_dir() -> Path | None:
    """Directory containing node/npx: PATH first, then the newest nvm install (nvm only
    adds itself to PATH in interactive shells, so scripts and cron jobs often miss it)."""
    found = shutil.which("npx")
    if found:
        return Path(found).parent
    nvm = Path(os.environ.get("NVM_DIR", Path.home() / ".nvm")) / "versions" / "node"
    for d in sorted(nvm.glob("v*"), key=_version_key, reverse=True):
        if (d / "bin" / "npx").exists() and (d / "bin" / "node").exists():
            return d / "bin"
    return None


def node_env() -> dict[str, str]:
    env = dict(os.environ)
    bin_dir = node_bin_dir()
    if bin_dir is not None and str(bin_dir) not in env.get("PATH", "").split(os.pathsep):
        env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    return env


def check_renderer(renderer_dir: Path) -> None:
    if node_bin_dir() is None:
        raise RendererUnavailable("Node.js/npx not found on PATH or in ~/.nvm. Install Node.js 18+ (e.g. via nvm).")
    if not (renderer_dir / "node_modules" / "remotion").exists():
        raise RendererUnavailable(f"Remotion is not installed. Run: cd {renderer_dir} && npm install")


def remotion_version(renderer_dir: Path) -> str:
    try:
        return json.loads((renderer_dir / "node_modules" / "remotion" / "package.json").read_text())["version"]
    except (OSError, KeyError, json.JSONDecodeError):
        return "unknown"


def build_render_command(
    *,
    props: Path,
    public_dir: Path,
    output: Path,
    scale: float = 1.0,
    concurrency: int = 4,
    frames: str | None = None,
    composition: str = "Reel",
    crf: int = 18,
) -> list[str]:
    cmd = [
        "npx",
        "remotion",
        "render",
        "src/index.ts",
        composition,
        str(output),
        f"--props={props}",
        f"--public-dir={public_dir}",
        "--codec=h264",
        f"--crf={crf}",
        "--pixel-format=yuv420p",
        "--muted",
        f"--concurrency={concurrency}",
        "--log=info",
    ]
    if scale != 1.0:
        cmd.append(f"--scale={scale}")
    if frames:
        if not re.fullmatch(r"\d+(-\d+)?", frames):
            raise ValueError("frames must look like '0-299' or '120'")
        cmd.append(f"--frames={frames}")
    return cmd


def build_still_command(*, props: Path, public_dir: Path, output: Path, composition: str = "Cover") -> list[str]:
    return [
        "npx",
        "remotion",
        "still",
        "src/index.ts",
        composition,
        str(output),
        f"--props={props}",
        f"--public-dir={public_dir}",
        "--frame=0",
        "--image-format=png",
        "--log=error",
    ]


_PROGRESS = re.compile(r"Rendered (\d+)/(\d+)")


def _run(cmd: list[str], cwd: Path, log: Callable[[str], None], log_file: Path | None) -> None:
    proc = subprocess.Popen(
        cmd, cwd=cwd, env=node_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
    )
    tail: list[str] = []
    last_pct = -10
    fh = log_file.open("w") if log_file else None
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if fh:
                fh.write(line)
            tail = (tail + [line.rstrip()])[-25:]
            m = _PROGRESS.search(line)
            if m:
                pct = int(100 * int(m.group(1)) / max(int(m.group(2)), 1))
                if pct >= last_pct + 10:
                    last_pct = pct
                    log(f"  rendered {m.group(1)}/{m.group(2)} frames ({pct}%)")
        rc = proc.wait()
    finally:
        if fh:
            fh.close()
    if rc != 0:
        joined = "\n".join(tail)
        raise RuntimeError(f"Remotion failed (exit {rc}):\n{joined}")


def render_video(
    renderer_dir: Path,
    *,
    props: Path,
    public_dir: Path,
    output: Path,
    scale: float = 1.0,
    concurrency: int = 4,
    frames: str | None = None,
    log: Callable[[str], None] = print,
    log_file: Path | None = None,
) -> RenderResult:
    check_renderer(renderer_dir)
    cmd = build_render_command(
        props=props.resolve(),
        public_dir=public_dir.resolve(),
        output=output.resolve(),
        scale=scale,
        concurrency=concurrency,
        frames=frames,
    )
    t0 = time.time()
    _run(cmd, renderer_dir, log, log_file)
    return RenderResult(output=output, seconds=round(time.time() - t0, 1), command=cmd)


def render_still(
    renderer_dir: Path, *, props: Path, public_dir: Path, output: Path, log: Callable[[str], None] = print
) -> RenderResult:
    check_renderer(renderer_dir)
    cmd = build_still_command(props=props.resolve(), public_dir=public_dir.resolve(), output=output.resolve())
    t0 = time.time()
    _run(cmd, renderer_dir, log, None)
    return RenderResult(output=output, seconds=round(time.time() - t0, 1), command=cmd)
