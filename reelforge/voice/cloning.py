"""Clone the user's own enrolled voice with Pocket TTS (reference-audio prompting).

Requirements (checked here, never silently bypassed):
1. An enrolled AND approved voice profile (see enrollment.py).
2. Access to the gated `kyutai/pocket-tts` weights: accept the conditions at
   https://huggingface.co/kyutai/pocket-tts while logged in, with a Hugging Face token on this
   machine (`uv run hf auth login`). Without that, Pocket TTS loads the no-cloning weights and
   this engine refuses to run rather than falling back to a stock voice.
"""

from __future__ import annotations

from pathlib import Path

from reelforge.voice.base import VoiceUnavailable
from reelforge.voice.enrollment import EnrollmentError, load_profile, profile_dir
from reelforge.voice.local_tts import PocketTTSEngine, load_pocket_model

GATE_HELP = (
    "Voice cloning weights are gated. Log in at https://huggingface.co/kyutai/pocket-tts, accept the "
    "conditions (they prohibit cloning voices without consent), make sure a token is configured "
    "(`uv run hf auth login`), then delete ~/.cache/pocket_tts if needed and retry."
)


def cloning_available() -> bool:  # pragma: no cover - needs the model
    return bool(getattr(load_pocket_model(), "has_voice_cloning", False))


class ClonedVoiceEngine(PocketTTSEngine):
    def _voice_state(self):  # pragma: no cover - needs the model
        if self._state is None:
            from pocket_tts import export_model_state

            model = load_pocket_model()
            cache = Path(str(self.conditioning)).with_name("voice_state.safetensors")
            if cache.exists():
                self._state = model.get_state_for_audio_prompt(cache)
            else:
                self._state = model.get_state_for_audio_prompt(Path(self.conditioning))
                export_model_state(self._state, cache)
        return self._state


def clone_engine(voice_dir: Path, profile: str, check_gate: bool = True) -> ClonedVoiceEngine:
    try:
        data = load_profile(voice_dir, profile)
    except EnrollmentError as e:
        raise VoiceUnavailable(str(e)) from e
    if data.get("status") != "approved":
        raise VoiceUnavailable(
            f"voice profile {profile!r} is not approved yet. Listen to "
            f"{profile_dir(voice_dir, profile) / 'reference.wav'} and run `voice-approve`."
        )
    if check_gate and not cloning_available():
        raise VoiceUnavailable(GATE_HELP)
    ref = profile_dir(voice_dir, profile) / data["reference"]
    return ClonedVoiceEngine(
        conditioning=ref,
        voice_label=f"your cloned voice (profile '{profile}')",
        provenance=f"Pocket TTS clone of the user's own enrolled voice (profile '{profile}', consent recorded "
        f"{data['consent']['confirmed_at']})",
        licence_note="Pocket TTS weights CC-BY-4.0 (Kyutai); reference audio: the user's own recordings",
    )
