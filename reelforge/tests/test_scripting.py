import pytest
from pydantic import ValidationError

from reelforge.research.verification import assess_claim, extract_candidate_claims
from reelforge.schemas import Claim, ClaimStatus, ResearchBundle, Script, ScriptSection, Source
from reelforge.scripting.hooks import heuristic_score, rank_hooks
from reelforge.scripting.manual import ScriptParseError, parse_script_text
from reelforge.scripting.validation import validate_script
from reelforge.tests.conftest import SCRIPT_TEXT


def test_parse_marked_up_script():
    script, research, say = parse_script_text(SCRIPT_TEXT)
    assert script.title == "Test reel about tiny models"
    assert [s.role for s in script.sections] == ["hook", "explain", "number", "analogy", "twist", "cta"]
    assert script.sections[0].visual.headline == "A 7B model on a laptop"
    assert script.sections[0].visual.subtext == "No data center"
    assert script.sections[1].visual.items == ["Weights", "Memory", "Math"]
    assert script.sections[2].visual.stat_value == 14
    assert len(script.hashtags) == 5
    assert say == {"CPU": "C P U"}
    assert len(research.sources) == 1 and research.claims[0].source_ids == ["M1"]
    assert research.claims[0].section_index == 2  # best word overlap: the "two bytes" section


def test_parse_plain_text_infers_roles():
    raw = (
        "Your phone can run AI.\n\nHere's how it works, simply.\n\nIt uses 4 bits per weight.\n\n"
        "But here's the catch, quality drops.\n\nSend this to a friend."
    )
    script, _, _ = parse_script_text(raw)
    assert [s.role for s in script.sections] == ["hook", "explain", "number", "twist", "cta"]


def test_parse_rejects_unknown_tag_and_bad_hint():
    with pytest.raises(ScriptParseError):
        parse_script_text("[intro-ish]\nhello")
    with pytest.raises(ScriptParseError):
        parse_script_text("[hook]\nhello there\n> colour: red")


def test_script_schema_validation():
    with pytest.raises(ValidationError):
        Script(title="x", sections=[])
    with pytest.raises(ValidationError):
        ScriptSection(role="hook", text="   ")
    with pytest.raises(ValidationError):
        ScriptSection.model_validate({"role": "intro", "text": "hi"})


def test_source_and_claim_validation():
    with pytest.raises(ValidationError):
        Source(id="S1", url="not a url")
    s = Source(id="S1", url="https://www.example.org/a")
    assert s.domain == "example.org"
    with pytest.raises(ValidationError):
        ResearchBundle(sources=[s], claims=[Claim(id="C1", text="x", source_ids=["S9"])])
    with pytest.raises(ValidationError):
        ResearchBundle(sources=[s, s])


def test_claim_assessment_is_honest():
    opened = Source(
        id="S1", url="https://e.org", fetched=True, excerpt="Half precision occupies 16 bits, two bytes in memory."
    )
    closed = Source(id="S2", url="https://f.org", fetched=False)
    c = Claim(id="C1", text="Half precision uses 16 bits of memory", source_ids=["S1"])
    assert assess_claim(c, [opened]).status == ClaimStatus.AUTO_SUPPORTED
    c2 = Claim(id="C2", text="Half precision uses 32 bits of memory", source_ids=["S1"])
    r2 = assess_claim(c2, [opened])
    assert r2.status != ClaimStatus.AUTO_SUPPORTED and "32" in r2.check_details
    c3 = Claim(id="C3", text="Anything", source_ids=["S2"])
    assert assess_claim(c3, [closed]).status == ClaimStatus.UNVERIFIED
    assert assess_claim(Claim(id="C4", text="No source"), []).status == ClaimStatus.UNVERIFIED
    human = Claim(id="C5", text="x", source_ids=["S1"], status=ClaimStatus.HUMAN_VERIFIED)
    assert assess_claim(human, [opened]).status == ClaimStatus.HUMAN_VERIFIED


def test_candidate_claims_extracted_from_manual_script():
    script, _, _ = parse_script_text(SCRIPT_TEXT)
    claims = extract_candidate_claims(script)
    assert any("fourteen gigabytes" in c.text for c in claims)
    assert all(c.status == ClaimStatus.UNVERIFIED for c in claims)


def test_validate_script_warnings_and_errors():
    script, research, _ = parse_script_text(SCRIPT_TEXT)
    chk = validate_script(script, research)
    assert chk.ok
    assert any("short" in w for w in chk.warnings)
    tiny = Script(title="t", sections=[ScriptSection(role="explain", text="Too short.")])
    assert not validate_script(tiny, ResearchBundle()).ok


def test_hook_ranking_does_not_just_take_first():
    from reelforge.schemas import Hook

    hooks = [
        Hook(
            text="You won't believe this insane secret they hide about artificial intelligence models today",
            llm_score=7,
        ),
        Hook(text="Your laptop can run a 7 billion parameter AI model.", llm_score=7),
        Hook(text="Your laptop can run a 7 billion parameter AI model.", llm_score=6),
    ]
    ranked = rank_hooks(hooks)
    assert ranked[0].text.startswith("Your laptop")
    assert len(ranked) == 2  # duplicate removed
    assert heuristic_score("This is shocking")[0] < heuristic_score("Only 4 bits per weight?")[0]
