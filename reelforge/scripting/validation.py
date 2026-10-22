"""Script checks run before approval. Errors block approval; warnings are shown to the user."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from reelforge.schemas import ClaimStatus, ResearchBundle, Script


@dataclass
class ScriptCheck:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_script(
    script: Script, research: ResearchBundle, min_words: int = 110, max_words: int = 175
) -> ScriptCheck:
    chk = ScriptCheck()
    wc = script.word_count
    if wc < 40:
        chk.errors.append(f"script is only {wc} words; too short for a 45-60 s reel")
    elif wc < min_words:
        chk.warnings.append(f"{wc} words is short for 45-60 s (aim for 120-160)")
    if wc > 260:
        chk.errors.append(f"script is {wc} words; far too long for 60 s")
    elif wc > max_words:
        chk.warnings.append(f"{wc} words may run past 60 s (aim for 120-160)")

    roles = [s.role for s in script.sections]
    if roles[0] != "hook":
        chk.warnings.append("first section is not a hook")
    if "cta" not in roles:
        chk.warnings.append("no call-to-action section")
    if "twist" not in roles:
        chk.warnings.append("no twist/complication section")
    first_sentence = re.split(r"(?<=[.!?])\s+", script.sections[0].text)[0]
    if len(first_sentence.split()) > 18:
        chk.warnings.append("hook's first sentence is long (> 18 words); it may not land in 3 seconds")

    if len(script.hashtags) not in (0, 5):
        chk.warnings.append(f"{len(script.hashtags)} hashtags given; 5 are expected")

    unchecked = [c for c in research.claims if c.status in (ClaimStatus.UNVERIFIED, ClaimStatus.NOT_FOUND_IN_SOURCE)]
    if unchecked:
        chk.warnings.append(
            f"{len(unchecked)} claim(s) are unverified or not found in their sources: "
            + ", ".join(c.id for c in unchecked)
        )
    if any(c.status == ClaimStatus.HUMAN_REJECTED for c in research.claims):
        chk.errors.append("a claim was rejected during review; revise the script before approving")
    if not research.claims:
        chk.warnings.append("no factual claims recorded; the job will be labelled unverified")
    return chk
