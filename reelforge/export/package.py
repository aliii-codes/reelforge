"""Output package: caption, hashtags, script.md, sources/claims, metadata and completeness check."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

from reelforge.schemas import ClaimStatus, ResearchBundle, Script, ScriptVersion

PACKAGE_FILES = [
    "final_reel.mp4",
    "cover.png",
    "caption.txt",
    "hashtags.txt",
    "script.md",
    "sources.json",
    "claims.json",
    "narration.wav",
    "transcript.json",
    "captions.json",
    "scene_manifest.json",
    "render_metadata.json",
    "validation_report.json",
    "contact_sheet.jpg",
    "project_config.json",
]

GENERIC_TAGS = ["#AI", "#TechExplained", "#MachineLearning", "#LearnAI", "#TechTips"]
STOP = {
    "how",
    "why",
    "what",
    "the",
    "a",
    "an",
    "your",
    "you",
    "can",
    "is",
    "are",
    "on",
    "in",
    "of",
    "to",
    "and",
    "with",
    "for",
    "really",
    "actually",
    "does",
    "do",
    "it",
    "this",
    "that",
    "run",
    "runs",
    "works",
}


class UnsafeOutputPath(RuntimeError):
    pass


def safe_child(root: Path, name: str) -> Path:
    """Resolve `root/name`, refusing anything that escapes `root`."""
    p = (root / name).resolve()
    if root.resolve() != p and root.resolve() not in p.parents:
        raise UnsafeOutputPath(f"{name!r} escapes {root}")
    return p


def make_hashtags(script: Script, n: int = 5) -> list[str]:
    tags: list[str] = []
    for t in script.hashtags:
        t = "#" + re.sub(r"[^A-Za-z0-9_]", "", t.lstrip("#"))
        if len(t) > 1 and t.lower() not in {x.lower() for x in tags}:
            tags.append(t)
    if len(tags) < n:
        words = [w for w in re.findall(r"[A-Za-z0-9]+", script.title) if w.lower() not in STOP and len(w) > 2]
        if len(words) >= 2:
            tags.append("#" + "".join(w[:1].upper() + w[1:] for w in words[:3]))
        for g in GENERIC_TAGS:
            if len(tags) >= n:
                break
            if g.lower() not in {x.lower() for x in tags}:
                tags.append(g)
    return tags[:n]


def make_caption(script: Script, research: ResearchBundle, hashtags: list[str]) -> str:
    if script.caption:
        body = script.caption.strip()
    else:
        hook = re.split(r"(?<=[.!?])\s+", script.sections[0].text)[0]
        payoff = next((s.text for s in script.sections if s.role == "payoff"), "")
        body = f"{hook} {payoff}".strip()
    lines = [body]
    cited = []
    by_id = {s.id: s for s in research.sources}
    for c in research.claims:
        for sid in c.source_ids:
            if sid in by_id and by_id[sid].url not in cited:
                cited.append(by_id[sid].url)
    if cited:
        lines += ["", "Sources:"] + [f"- {u}" for u in cited[:6]]
    unverified = [c for c in research.claims if c.status in (ClaimStatus.UNVERIFIED, ClaimStatus.NOT_FOUND_IN_SOURCE)]
    if unverified or not research.claims:
        lines += ["", "[REVIEW BEFORE POSTING: some claims are unverified - see claims.json]"]
    lines += ["", " ".join(hashtags)]
    return "\n".join(lines) + "\n"


def script_markdown(sv: ScriptVersion, approved_hash: str | None) -> str:
    s = sv.script
    out = [f"# {s.title}", "", f"- Version: v{sv.version} ({sv.origin}), created {sv.created_at}"]
    if approved_hash:
        out.append(f"- Approved content hash: `{approved_hash}`")
    out += [f"- Words: {s.word_count} (estimate {s.estimated_seconds}s at 2.6 words/s)", ""]
    if s.hooks:
        out.append("## Hook candidates")
        for i, h in enumerate(s.hooks):
            mark = " (selected)" if i == s.selected_hook else ""
            out.append(f"{i + 1}. {h.text} — score {h.score}{mark}")
        out.append("")
    out.append("## Script")
    for sec in s.sections:
        out += [f"**[{sec.role}]** {sec.text}", ""]
    out.append("## Claims")
    if not sv.research.claims:
        out.append("_No claims recorded — treat this video as unverified._")
    for c in sv.research.claims:
        out.append(f"- **{c.id}** ({c.status.value}) {c.text} — sources: {', '.join(c.source_ids) or 'none'}")
        if c.check_details:
            out.append(f"  - check: {c.check_details}")
        if c.uncertainty:
            out.append(f"  - uncertainty: {c.uncertainty}")
    return "\n".join(out) + "\n"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_package(job_dir: Path) -> dict:
    present, missing, files = [], [], {}
    for name in PACKAGE_FILES:
        p = job_dir / name
        if p.exists() and p.stat().st_size > 0:
            present.append(name)
            files[name] = {"bytes": p.stat().st_size, "sha256": sha256_file(p)}
        else:
            missing.append(name)
    hashtags_ok = False
    if (job_dir / "hashtags.txt").exists():
        tags = (job_dir / "hashtags.txt").read_text().split()
        hashtags_ok = len(tags) == 5 and all(t.startswith("#") for t in tags)
    return {"complete": not missing and hashtags_ok, "missing": missing, "hashtags_ok": hashtags_ok, "files": files}


def export_copy(job_dir: Path, dest: Path) -> Path:
    """Copy the package to `dest/<job_id>`; never overwrites an existing directory."""
    target = dest / job_dir.name
    if target.exists():
        raise FileExistsError(f"{target} already exists; choose another destination")
    target.mkdir(parents=True)
    for name in PACKAGE_FILES + ["package_manifest.json"]:
        src = job_dir / name
        if src.exists():
            shutil.copy2(src, target / name)
    return target


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
