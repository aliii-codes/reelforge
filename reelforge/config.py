"""Runtime settings, loaded from environment variables and an optional `.env` file.

Secrets (API keys) live only in the environment / `.env`. `Settings.public_dict()` is the only
representation that should ever be written to disk or logs; it replaces secrets with
"set"/"missing".
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SECRET_FIELDS = {"groq_api_key", "cohere_api_key", "tavily_api_key"}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    return int(raw) if raw else default


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    return float(raw) if raw else default


def _resolve(raw: str, default: Path) -> Path:
    if not raw:
        return default
    p = Path(raw).expanduser()
    return p if p.is_absolute() else PROJECT_ROOT / p


@dataclass
class Settings:
    project_root: Path = PROJECT_ROOT
    data_dir: Path = PROJECT_ROOT / "data"
    output_dir: Path = PROJECT_ROOT / "output"
    voice_dir: Path = PROJECT_ROOT / "voice_data"
    renderer_dir: Path = PROJECT_ROOT / "renderer"

    # LLM providers ("auto" = Groq, then Cohere, then local Ollama if configured).
    llm_provider: str = "auto"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    cohere_api_key: str = ""
    cohere_model: str = "command-a-03-2025"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = ""
    llm_timeout_s: float = 60.0

    # Research
    tavily_api_key: str = ""
    research_contact: str = ""  # included in the Wikipedia User-Agent, per Wikimedia etiquette

    # Voice / transcription
    whisper_model: str = "base.en"
    whisper_threads: int = 4
    tts_stock_voice: str = "marius"  # CC0 voice-donation voice shipped with Pocket TTS
    voice_profile: str = "default"
    takes: int = 3

    # Rendering
    render_concurrency: int = 4
    preview_scale: float = 0.5
    handle: str = ""

    extra: dict[str, str] = field(default_factory=dict)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "reelforge.db"

    def public_dict(self) -> dict[str, object]:
        out: dict[str, object] = {}
        for f in fields(self):
            if f.name == "extra":
                continue
            value = getattr(self, f.name)
            if f.name in SECRET_FIELDS:
                out[f.name] = "set" if value else "missing"
            elif isinstance(value, Path):
                out[f.name] = str(value)
            else:
                out[f.name] = value
        return out

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.output_dir, self.voice_dir):
            d.mkdir(parents=True, exist_ok=True)


def load_settings(env_file: Path | None = None) -> Settings:
    """Build settings from `.env` (if present) and the process environment.

    Existing environment variables win over `.env` values.
    """
    load_dotenv(env_file or PROJECT_ROOT / ".env", override=False)
    return Settings(
        data_dir=_resolve(_env("REELFORGE_DATA_DIR"), PROJECT_ROOT / "data"),
        output_dir=_resolve(_env("REELFORGE_OUTPUT_DIR"), PROJECT_ROOT / "output"),
        voice_dir=_resolve(_env("REELFORGE_VOICE_DIR"), PROJECT_ROOT / "voice_data"),
        renderer_dir=_resolve(_env("REELFORGE_RENDERER_DIR"), PROJECT_ROOT / "renderer"),
        llm_provider=_env("REELFORGE_LLM_PROVIDER", "auto").lower(),
        groq_api_key=_env("GROQ_API_KEY"),
        groq_model=_env("GROQ_MODEL", "openai/gpt-oss-120b"),
        cohere_api_key=_env("COHERE_API_KEY") or _env("CO_API_KEY"),
        cohere_model=_env("COHERE_MODEL", "command-a-03-2025"),
        ollama_url=_env("OLLAMA_URL", "http://127.0.0.1:11434"),
        ollama_model=_env("OLLAMA_MODEL"),
        llm_timeout_s=_env_float("REELFORGE_LLM_TIMEOUT", 60.0),
        tavily_api_key=_env("TAVILY_API_KEY"),
        research_contact=_env("REELFORGE_CONTACT"),
        whisper_model=_env("REELFORGE_WHISPER_MODEL", "base.en"),
        whisper_threads=_env_int("REELFORGE_WHISPER_THREADS", 4),
        tts_stock_voice=_env("REELFORGE_STOCK_VOICE", "marius"),
        voice_profile=_env("REELFORGE_VOICE_PROFILE", "default"),
        takes=_env_int("REELFORGE_TAKES", 3),
        render_concurrency=_env_int("REELFORGE_RENDER_CONCURRENCY", 4),
        preview_scale=_env_float("REELFORGE_PREVIEW_SCALE", 0.5),
        handle=_env("REELFORGE_HANDLE"),
    )
