"""Real screenshots of cited sources, with the cited sentence located on the page.

Runs `renderer/scripts/capture-evidence.mjs` (Remotion's Chrome Headless Shell over the DevTools
protocol). Results are cached per (url, quote) in the job folder. Needs network access; when a
capture fails the planner falls back to a plain quote card that does not pretend to be a
screenshot.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from reelforge.rendering.remotion import node_env


def capture_evidence(url: str, quote: str, public_dir: Path, renderer_dir: Path, timeout: float = 90) -> dict:
    key = hashlib.sha256(f"{url}\n{quote}".encode()).hexdigest()[:12]
    assets = public_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    png = assets / f"evidence_{key}.png"
    meta_path = assets / f"evidence_{key}.json"
    if png.exists() and meta_path.exists():
        return json.loads(meta_path.read_text())
    try:
        proc = subprocess.run(
            ["node", "scripts/capture-evidence.mjs", url, quote, str(png)],
            cwd=renderer_dir,
            env=node_env(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        result = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else {"ok": False}
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
        result = {"ok": False, "error": type(e).__name__}
    if result.get("ok"):
        result["asset"] = f"assets/{png.name}"
        meta_path.write_text(json.dumps(result, indent=1))
    return result
