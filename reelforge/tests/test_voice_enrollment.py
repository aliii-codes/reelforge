import builtins
import sys
from pathlib import Path

import pytest

from reelforge.tests.conftest import write_tone
from reelforge.voice.base import VoiceUnavailable
from reelforge.voice.cloning import clone_engine
from reelforge.voice.enrollment import EnrollmentError, approve, delete, enroll, list_profiles, profile_dir
from reelforge.voice.local_tts import stock_engine


def test_enrollment_requires_consent(tmp_path: Path):
    clip = write_tone(tmp_path / "me.wav", 12)
    with pytest.raises(EnrollmentError):
        enroll(tmp_path / "voices", "default", [clip], consent=False)


def test_enroll_approve_delete(tmp_path: Path):
    voices = tmp_path / "voices"
    clips = [write_tone(tmp_path / "a.wav", 12, sr=48000), write_tone(tmp_path / "b.wav", 3, sr=48000)]
    data = enroll(voices, "default", clips, consent=True)
    assert data["status"] == "pending_review"
    assert (voices / "default" / "reference.wav").exists()
    assert any("only" in p for p in data["problems"])  # 3 s clip is too short
    assert data["consent"]["statement"].startswith("I confirm")
    with pytest.raises(EnrollmentError):
        enroll(voices, "default", clips, consent=True)  # no silent overwrite
    with pytest.raises(VoiceUnavailable):
        clone_engine(voices, "default", check_gate=False)  # not approved yet
    approve(voices, "default")
    eng = clone_engine(voices, "default", check_gate=False)
    assert "your cloned voice" in eng.voice_label and "consent" in eng.provenance
    assert [p["profile"] for p in list_profiles(voices)] == ["default"]
    assert delete(voices, "default") and not (voices / "default").exists()


def test_profile_path_safety(tmp_path: Path):
    with pytest.raises(EnrollmentError):
        profile_dir(tmp_path, "../../etc")


def test_stock_voice_is_labelled_and_vetted():
    eng = stock_engine("marius")
    assert "NOT" in eng.voice_label and "NOT a clone" in eng.provenance
    with pytest.raises(VoiceUnavailable):
        stock_engine("cosette")  # Expresso-derived (non-commercial) voice is not offered


def test_missing_optional_dependency_messages(monkeypatch):
    from reelforge.voice import transcription

    transcription._load_model.cache_clear()
    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "faster_whisper":
            raise ImportError("not installed")
        return real_import(name, *a, **kw)

    monkeypatch.delitem(sys.modules, "faster_whisper", raising=False)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(transcription.TranscriptionUnavailable, match="uv sync --extra transcribe"):
        transcription._load_model("base.en", 1)
    transcription._load_model.cache_clear()
