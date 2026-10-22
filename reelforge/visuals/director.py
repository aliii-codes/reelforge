"""The editing grammar: how ReelForge cuts, moves the camera, stages the avatar and places sound.

Rules (deliberately few, so the video reads as one edit with a consistent motion language):

- Cuts: a hard cut inside a section (the idea continues); a whip or zoom only when a new section
  (a new idea) starts; a white flash only on impacts (big numbers, the twist). Never the same
  non-cut transition twice in a row.
- Camera: slow push on typography and numbers, drift on explainers, track-to-target on footage
  (terminal line, highlighted evidence), a quick punch on meme beats; diagrams and charts stay
  still so they can be read.
- Background: one palette, a few modes - grid (explaining), glow (statements), terminal, paper
  (evidence) and accent (the twist).
- Avatar: on screen only where a face adds something - the hook, reactions, short explainers
  and the CTA. Hidden on footage, evidence, charts and kinetic type.
- Captions: hidden while kinetic typography is already showing the spoken words.
- Sound follows picture: whoosh only on whip/zoom, impact on flash cuts and number slams, a riser
  into the twist with the music dropping out, key clicks while terminal commands type, a shutter
  when a screenshot lands, a soft pop on kinetic emphasis words (rate-limited).
"""

from __future__ import annotations

FPS = 30

ROLE_PACE = {"hook": 1.8, "twist": 2.2, "payoff": 2.4, "cta": 3.0}
DEFAULT_PACE = 3.4

BACKGROUND = {
    "hook": "glow", "kinetic": "glow", "stat": "glow", "reveal": "glow", "cta": "glow", "meme": "glow",
    "explain": "grid", "diagram": "grid", "bars": "grid", "comparison": "grid", "analogy": "grid",
    "photo": "grid", "demo": "terminal", "terminal": "terminal", "evidence": "paper", "twist": "accent",
}  # fmt: skip
CAMERA = {
    "hook": "push", "kinetic": "push", "stat": "push", "reveal": "push", "twist": "push", "cta": "drift",
    "explain": "drift", "photo": "drift", "terminal": "track", "evidence": "track", "meme": "punch",
    "diagram": "none", "bars": "none", "comparison": "none", "analogy": "none", "demo": "none",
}  # fmt: skip
AVATAR = {
    "hook": "center", "cta": "center", "meme": "reaction", "explain": "corner", "twist": "center",
}  # everything else: hidden  # fmt: skip
IMPACT_TYPES = {"stat", "twist", "meme"}


def pace_for(role: str) -> float:
    return ROLE_PACE.get(role, DEFAULT_PACE)


def direct(scenes: list[dict], roles: dict[int, str]) -> None:
    """Fill transition/camera/background/avatar/hide_captions on planned scene dicts in place."""
    last_fx = ""
    for i, d in enumerate(scenes):
        t = d["type"]
        new_section = i == 0 or d["section_index"] != scenes[i - 1]["section_index"]
        if i == 0:
            fx = "cut"
        elif new_section and t in IMPACT_TYPES:
            fx = "flash"
        elif new_section:
            fx = "zoom" if last_fx == "whip" else "whip"
        else:
            fx = "cut"
        d["transition"] = fx
        if fx != "cut":
            last_fx = fx
        d["camera"] = CAMERA.get(t, "drift")
        d["background"] = BACKGROUND.get(t, "grid")
        d["avatar"] = AVATAR.get(t, "hidden")
        if t == "hook" and i > 0:
            d["avatar"] = "hidden"
        d["hide_captions"] = t in ("kinetic", "meme")  # the words are already on screen


def sound_cues(scenes: list[dict]) -> tuple[list[dict], list[dict]]:
    """SFX and music automation derived from the visual events."""
    sfx: list[dict] = []
    music: list[dict] = []
    last_pop = -10_000
    for i, d in enumerate(scenes):
        start = d["start_frame"]
        fx = d["transition"]
        if fx in ("whip", "zoom"):
            sfx.append({"frame": start, "kind": "whoosh"})
        elif fx == "flash":
            sfx.append({"frame": start, "kind": "impact"})
        if d["type"] == "twist" and i > 0:
            sfx.append({"frame": max(0, start - 30), "kind": "riser", "duration_frames": 30})
            music.append({"frame": max(0, start - 2), "kind": "drop"})
            music.append({"frame": min(d["end_frame"], start + 40), "kind": "return"})
        for c in d.get("cues", []):
            kind = c.kind if hasattr(c, "kind") else c["kind"]
            frame = c.frame if hasattr(c, "frame") else c["frame"]
            if kind == "count" and fx != "flash":
                sfx.append({"frame": frame, "kind": "impact"})
            elif kind == "highlight":
                sfx.append({"frame": frame, "kind": "pop"})
            elif kind == "emphasis" and d["type"] == "kinetic" and frame - last_pop >= 24:
                sfx.append({"frame": frame, "kind": "pop"})
                last_pop = frame
        if d["type"] == "evidence" and d.get("asset"):
            sfx.append({"frame": start + 3, "kind": "shutter"})
        for step in d.get("meta", {}).get("timing", []):
            sfx.append(
                {"frame": step["type_start"], "kind": "keys", "duration_frames": step["type_end"] - step["type_start"]}
            )
    sfx.sort(key=lambda c: c["frame"])
    return sfx, music


def terminal_timing(cast: dict, start: int, end: int) -> list[dict]:
    """When each command is typed and its (real) output appears, fitted into the scene."""
    steps = cast["steps"]
    budget = max(30, end - start - 18)
    typing = [min(30, max(8, round(len(s["command"]) / 2.2))) for s in steps]
    out_lines = [len(s["output"]) for s in steps]
    reading = [10 + 6 * n for n in out_lines]
    need = sum(typing) + sum(reading)
    if need > budget:  # speed up typing first, then shorten reading time
        scale = max(0.35, (budget - sum(reading)) / max(sum(typing), 1))
        typing = [max(5, round(t * scale)) for t in typing]
        need = sum(typing) + sum(reading)
        if need > budget:
            r = max(0.3, (budget - sum(typing)) / max(sum(reading), 1))
            reading = [max(6, round(x * r)) for x in reading]
    spare = max(0, budget - sum(typing) - sum(reading))
    t = start + 6
    out = []
    for k, _s in enumerate(steps):
        type_start = t
        type_end = t + typing[k]
        out_at = type_end + 3
        out.append({"type_start": type_start, "type_end": type_end, "out_at": out_at})
        t = out_at + reading[k] + spare // max(len(steps), 1)
    return out
