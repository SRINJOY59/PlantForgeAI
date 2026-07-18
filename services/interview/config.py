"""Interview-only settings. The shared Settings class ignores unknown env
keys (extra="ignore"), so the voice-stack keys live here instead of touching
plantmind_core.config. The same root .env feeds both."""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from plantmind_core.config import get_settings


def _env_file_values() -> dict:
    """Walk up from CWD to the nearest .env, same as core config does."""
    for parent in (Path.cwd(), *Path.cwd().parents):
        candidate = parent / ".env"
        if candidate.exists():
            values = {}
            for line in candidate.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                # the repo's .env carries inline comments; drop them
                value = value.split("#", 1)[0]
                values[key.strip()] = value.strip().strip('"').strip("'")
            return values
    return {}


@dataclass(frozen=True)
class InterviewConfig:
    deepgram_api_key: str
    tts_provider: str            # deepgram | cartesia | elevenlabs
    cartesia_api_key: str
    elevenlabs_api_key: str
    llm_model: str               # realtime interviewer model (OpenRouter id)
    port: int
    data_dir: Path
    text_mode: bool              # enables /debug/text (no mic, no Deepgram)

    @property
    def voice_ready(self) -> bool:
        return bool(self.deepgram_api_key)

    @property
    def sessions_dir(self) -> Path:
        return self.data_dir / "sessions"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"


@lru_cache
def get_config() -> InterviewConfig:
    values = _env_file_values()

    def env(key, default=""):
        return os.environ.get(key, values.get(key, default))

    cfg = InterviewConfig(
        deepgram_api_key=env("DEEPGRAM_API_KEY"),
        tts_provider=env("INTERVIEW_TTS_PROVIDER", "deepgram").lower(),
        cartesia_api_key=env("CARTESIA_API_KEY"),
        elevenlabs_api_key=env("ELEVENLABS_API_KEY"),
        llm_model=env("INTERVIEW_LLM_MODEL") or get_settings().llm_mid,
        port=int(env("INTERVIEW_PORT", "8002")),
        data_dir=Path(env("INTERVIEW_DATA_DIR", "data/interviews")),
        text_mode=env("INTERVIEW_TEXT_MODE", "0").lower() in ("1", "true", "yes"),
    )
    cfg.sessions_dir.mkdir(parents=True, exist_ok=True)
    cfg.exports_dir.mkdir(parents=True, exist_ok=True)
    return cfg
