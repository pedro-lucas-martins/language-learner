"""Application settings, read from environment variables (see .env.example).

Model names, voice IDs, prices and limits live here and nowhere else.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The .env file sits at the repository root (one level above backend/).
_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"

TtsProviderName = Literal["google", "elevenlabs"]
LangCode = Literal["pl-PL", "pt-BR"]


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
    # Development only: extra exact origins, e.g. the HTTPS LAN address used to test on a phone.
    dev_extra_origins: str = ""

    # --- Database ---
    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/app"

    # --- Gemini ---
    gemini_api_key: str = ""
    gemini_chat_model: str = ""
    gemini_utility_model: str = ""
    gemini_stt_model: str = ""
    # Optional thinking level for the STT model only (e.g. LOW). Empty = GEMINI_THINKING_LEVEL.
    gemini_stt_thinking_level: str = ""
    # Track 2: grammar + pronunciation feedback and pron_retry judgments (SPEC §5).
    gemini_feedback_model: str = ""
    # Optional: MINIMAL | LOW | MEDIUM | HIGH. Empty = model default. Lower = faster replies.
    gemini_thinking_level: str = ""

    # --- TTS (active provider) ---
    tts_provider: TtsProviderName = "google"
    # Allowance of the active provider (free tier or plan); fallback kicks in at 95%.
    tts_monthly_chars: int = Field(default=1_000_000, ge=0)

    # --- Google Cloud Text-to-Speech (Chirp 3 HD) ---
    # Path to a service-account JSON file (standard Google ADC variable).
    google_application_credentials: str = ""
    google_tts_voices_pl: str = ""
    google_tts_voices_pt: str = ""

    # --- ElevenLabs ---
    elevenlabs_api_key: str = ""
    elevenlabs_model: str = ""
    elevenlabs_voices_pl: str = ""
    elevenlabs_voices_pt: str = ""

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
    price_stt_output_per_m: float = Field(default=0.0, ge=0)
    price_feedback_input_per_m: float = Field(default=0.0, ge=0)
    price_feedback_output_per_m: float = Field(default=0.0, ge=0)
    price_tts_per_1k_chars: float = Field(default=0.0, ge=0)
    daily_llm_calls_per_user: int = Field(default=400, ge=0)
    daily_stt_seconds_per_user: int = Field(default=3600, ge=0)
    daily_tts_chars_per_user: int = Field(default=8000, ge=0)
    tts_cache_max_mb: int = Field(default=200, ge=0)

    # --- Conversation memory ---
    window_turns: int = Field(default=3, ge=1)
    summary_batch_turns: int = Field(default=3, ge=1)

    @field_validator(
        "google_tts_voices_pl",
        "google_tts_voices_pt",
        "elevenlabs_voices_pl",
        "elevenlabs_voices_pt",
    )
    @classmethod
    def _validate_voices(cls, value: str) -> str:
        _parse_voice_pairs(value)  # raises on malformed entries
        return value

    def tts_voices(self, provider: TtsProviderName, lang: LangCode) -> list[Voice]:
        """Curated voices for a TTS provider and the language the AI speaks."""
        suffix = "pl" if lang == "pl-PL" else "pt"
        prefix = "google_tts" if provider == "google" else provider
        return _parse_voice_pairs(getattr(self, f"{prefix}_voices_{suffix}"))

    def tts_provider_configured(self, provider: TtsProviderName) -> bool:
        """True when the provider has credentials (used by the app and by tts_bench.py)."""
        credentials = {
            "google": self.google_application_credentials,
            "elevenlabs": self.elevenlabs_api_key,
        }
        return bool(credentials[provider])

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
            origins += [o.rstrip("/") for o in _parse_csv(self.dev_extra_origins)]
        return sorted(set(origins))


@lru_cache
def get_settings() -> Settings:
    return Settings()
