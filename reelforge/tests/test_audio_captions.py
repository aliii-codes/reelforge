from pathlib import Path

from reelforge.captions.alignment import CaptionTrack, CaptionWord, build_caption_track, group_words
from reelforge.captions.validation import validate_captions
from reelforge.schemas import Script, ScriptSection, Segment, Transcript, Word
from reelforge.tests.conftest import write_tone
from reelforge.voice.base import apply_pronunciations
from reelforge.voice.quality import analyze_audio, compare_transcript, normalize_words, number_to_words, score_take

SCRIPT = Script(
    title="t",
    sections=[
        ScriptSection(role="hook", text="Seven billion weights need fourteen gigabytes."),
        ScriptSection(role="cta", text="Send this to a friend who uses a GPT."),
    ],
)


def transcript_from(
    words: list[tuple[str, float, float]], duration: float = 6.0, word_level: bool = True
) -> Transcript:
    ws = [Word(text=t, start=s, end=e) for t, s, e in words]
    return Transcript(
        text=" ".join(t for t, _, _ in words),
        words=ws if word_level else [],
        segments=[Segment(text=" ".join(t for t, _, _ in words), start=words[0][1], end=words[-1][2])],
        model="test",
        word_level=word_level,
        duration=duration,
    )


def full_heard():
    words = "Seven billion weights need 14 gigabytes. Send this to a friend who uses a G P T.".split()
    return [(w, 0.3 + i * 0.35, 0.3 + i * 0.35 + 0.3) for i, w in enumerate(words)]


def test_normalize_words_numbers_and_letters():
    assert normalize_words("14 GB") == ["fourteen", "gb"]
    assert normalize_words("G P T and a GPT") == ["gpt", "and", "a", "gpt"]
    assert normalize_words("3.5%") == ["three", "point", "five", "percent"]
    assert number_to_words(7_000_000_000) == "seven billion"
    assert normalize_words("seven-billion-parameter") == ["seven", "billion", "parameter"]


def test_compare_transcript_flags_missing_and_extra():
    d = compare_transcript("the quick brown fox", "the quick fox jumps")
    assert d.missing == ["brown"] and d.extra == ["jumps"] and d.wer == 0.5
    assert compare_transcript("Send it to GPT", "send it to G P T").wer == 0


def test_pronunciations_only_whole_words():
    assert apply_pronunciations("GPT and GPTs", {"GPT": "G P T"}) == "G P T and GPTs"


def test_alignment_uses_script_spelling_and_real_timing():
    track = build_caption_track(SCRIPT, transcript_from(full_heard()))
    assert [w.text for w in track.words][:5] == ["Seven", "billion", "weights", "need", "fourteen"]
    assert track.words[4].start == full_heard()[4][1]  # "fourteen" timed from the heard "14"
    assert track.approximate_words == 0
    assert track.words[-1].text == "GPT." and track.words[-1].end == full_heard()[-1][2]
    rep = validate_captions(track, 7.0, expected_words=15)
    assert rep.ok, rep.errors


def test_alignment_interpolates_missing_words_and_flags_them():
    heard = [w for w in full_heard() if w[0] != "friend"]
    track = build_caption_track(SCRIPT, transcript_from(heard))
    friend = next(w for w in track.words if w.text == "friend")
    assert friend.approximate
    assert track.approximate_words == 1


def test_segment_level_fallback_is_marked_approximate():
    track = build_caption_track(SCRIPT, transcript_from(full_heard(), word_level=False))
    assert not track.word_level and all(w.approximate for w in track.words)
    assert any("approximate" in n for n in track.notes)
    assert not validate_captions(track, 6.0).ok  # >25% interpolated -> flagged as error


def test_grouping_limits():
    words = [
        CaptionWord(text=w, start=i * 0.3, end=i * 0.3 + 0.25, section_index=0)
        for i, w in enumerate("one two three four five six seven, eight".split())
    ]
    groups = group_words(words, max_words=3)
    assert all(len(g.word_indices) <= 3 for g in groups)
    assert groups[2].text.endswith("seven,")  # break after punctuation
    for a, b in zip(groups, groups[1:], strict=False):
        assert a.end <= b.start


def test_caption_validation_detects_problems():
    good = build_caption_track(SCRIPT, transcript_from(full_heard()))
    w = good.words
    bad = CaptionTrack(
        words=[w[0], w[0], w[2].model_copy(update={"start": 0.1}), w[3].model_copy(update={"end": 99})],
        groups=good.groups[:1],
        timing_source="t",
        word_level=True,
    )
    rep = validate_captions(bad, 6.0)
    text = " ".join(rep.errors)
    assert "duplicates" in text and "out of order" in text and "outside the audio" in text
    assert "not in any caption group" in text


def test_audio_quality_checks(tmp_path: Path):
    good = analyze_audio(write_tone(tmp_path / "good.wav", 6))
    assert 5.9 < good.duration < 6.1 and good.clipping_ratio == 0
    clipped = analyze_audio(write_tone(tmp_path / "clip.wav", 6, amp=3.0))
    assert any("clipping" in i for i in clipped.issues)
    short = analyze_audio(write_tone(tmp_path / "short.wav", 2), min_seconds=5)
    assert any("only" in i for i in short.issues)
    noisy = analyze_audio(write_tone(tmp_path / "noisy.wav", 6, noise=0.08))
    assert any("noisy" in i for i in noisy.issues)


def test_score_take_prefers_complete_transcripts(tmp_path: Path):
    audio = analyze_audio(write_tone(tmp_path / "a.wav", 50))
    perfect, _ = score_take(compare_transcript("small models run locally", "small models run locally"), audio, 45, 60)
    missing, issues = score_take(compare_transcript("small models run locally", "small models locally"), audio, 45, 60)
    assert perfect > missing and any("not heard" in i for i in issues)


def test_number_and_homophone_folding():
    assert normalize_words("three and a half gigabytes") == normalize_words("3.5 gigabytes")
    assert compare_transcript("Squeeze too hard to two bits", "squeeze two hard to 2 bits").wer == 0
    # a repeated word is a real defect and must be reported as extra
    d = compare_transcript("clever compression. Send this", "clever compression. compression. Send this")
    assert d.extra == ["compression"]


def test_generated_sound_handles_any_duration(tmp_path):
    from reelforge.rendering import sound

    for dur in (0.3, 4.05, 52.1):  # last chord segment shorter than the release time
        sound.write_bed(tmp_path / "bed.wav", dur)
        sound.write_sfx_track(tmp_path / "sfx.wav", dur, [0.1, dur - 0.05])
