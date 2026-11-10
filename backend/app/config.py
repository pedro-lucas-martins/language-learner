"""Application settings, read from environment variables (see .env.example).

Model names, voice IDs, prices and limits live here and nowhere else.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The .env file sits at the repository root (one level above backend/).
_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


class Voice(tuple):
    """An (id, label) pair parsed from 'id:label'."""

    @property
    def id(self) -> str:
        return self[0]

    @property
    def label(self) -> str:
        return self[1]


def _parse_voice_pairs(raw: str) -> list[Voice]:
    voices: list[Voice] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        voice_id, _, label = item.partition(":")
        voice_id = voice_id.strip()
        if not voice_id:
            raise ValueError(f"Invalid voice entry {item!r}: expected 'id:label'")
        voices.append(Voice((voice_id, label.strip() or voice_id)))
    return voices


def _parse_csv(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ROOT_ENV,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    app_env: str = "development"
    frontend_url: str = "http://localhost:5173"
    vercel_preview_regex: str = ""

    # --- Database ---
    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/app"

    # --- Gemini ---
    gemini_api_key: str = ""
    gemini_chat_model: str = ""
    gemini_utility_model: str = ""
    gemini_stt_model: str = ""

    # --- ElevenLabs ---
    elevenlabs_api_key: str = ""
    elevenlabs_model: str = ""
    elevenlabs_voices_pl: str = ""
    elevenlabs_voices_pt: str = ""
    elevenlabs_monthly_chars: int = Field(default=100_000, ge=0)

    # --- edge-tts fallback ---
    edge_voices_pl: str = "pl-PL-ZofiaNeural,pl-PL-MarekNeural"
    edge_voices_pt: str = "pt-BR-FranciscaNeural,pt-BR-AntonioNeural"

    # --- Budget & caps ---
    monthly_budget_usd: float = Field(default=15.0, ge=0)
    price_chat_input_per_m: float = Field(default=0.0, ge=0)
    price_chat_output_per_m: float = Field(default=0.0, ge=0)
    price_utility_input_per_m: float = Field(default=0.0, ge=0)
    price_utility_output_per_m: float = Field(default=0.0, ge=0)
    price_stt_audio_input_per_m: float = Field(default=0.0, ge=0)
    price_tts_per_1k_chars: float = Field(default=0.0, ge=0)
    daily_llm_calls_per_user: int = Field(default=400, ge=0)
    daily_stt_seconds_per_user: int = Field(default=3600, ge=0)
    daily_tts_chars_per_user: int = Field(default=8000, ge=0)
    tts_cache_max_mb: int = Field(default=200, ge=0)

    # --- Conversation memory ---
    window_turns: int = Field(default=3, ge=1)
    summary_batch_turns: int = Field(default=3, ge=1)

    @field_validator("elevenlabs_voices_pl", "elevenlabs_voices_pt")
    @classmethod
    def _validate_voices(cls, value: str) -> str:
        _parse_voice_pairs(value)  # raises on malformed entries
        return value

    @property
    def voices_pl(self) -> list[Voice]:
        return _parse_voice_pairs(self.elevenlabs_voices_pl)

    @property
    def voices_pt(self) -> list[Voice]:
        return _parse_voice_pairs(self.elevenlabs_voices_pt)

    @property
    def edge_voices(self) -> dict[str, list[str]]:
        return {
            "pl-PL": _parse_csv(self.edge_voices_pl),
            "pt-BR": _parse_csv(self.edge_voices_pt),
        }

    @property
    def allowed_origins(self) -> list[str]:
        origins = [self.frontend_url.rstrip("/")]
        if self.app_env == "development":
            origins.append("http://localhost:5173")
        return sorted(set(origins))


@lru_cache
def get_settings() -> Settings:
    return Settings()
