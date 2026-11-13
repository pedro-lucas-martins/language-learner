"""ElevenLabs streaming text-to-speech over HTTP (SPEC §6)."""

import logging
from collections.abc import AsyncIterator

import httpx

from app.config import LangCode, Settings, Voice
from app.services.tts.base import FIRST_BYTE_TIMEOUT_S, TtsError, with_timeouts

log = logging.getLogger(__name__)

API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
OUTPUT_FORMAT = "mp3_44100_64"
# ElevenLabs accepts speeds in this range.
MIN_SPEED, MAX_SPEED = 0.7, 1.2


class ElevenLabsTts:
    name = "elevenlabs"
    mime = "audio/mpeg"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.model = settings.elevenlabs_model
        self._client: httpx.AsyncClient | None = None

    def voices(self, lang: LangCode) -> list[Voice]:
        return self._settings.tts_voices("elevenlabs", lang)

    def _get_client(self) -> httpx.AsyncClient:
        if not self._settings.elevenlabs_api_key:
            raise TtsError("not_configured", "ELEVENLABS_API_KEY is empty")
        if not self.model:
            raise TtsError("not_configured", "ELEVENLABS_MODEL is empty")
        if self._client is None:
            # One client per process: connection reuse keeps time-to-first-byte low.
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, connect=FIRST_BYTE_TIMEOUT_S),
                headers={"xi-api-key": self._settings.elevenlabs_api_key},
            )
        return self._client

    async def warm(self) -> None:
        """Open the HTTPS connection with a free call (model list)."""
        await self._get_client().get("https://api.elevenlabs.io/v1/models")

    async def _raw_stream(
        self, text: str, lang: LangCode, voice_id: str, speaking_rate: float
    ) -> AsyncIterator[bytes]:
        client = self._get_client()
        body = {
            "text": text,
            "model_id": self.model,
            "language_code": lang.split("-")[0],
            "voice_settings": {"speed": max(MIN_SPEED, min(MAX_SPEED, speaking_rate))},
        }
        try:
            async with client.stream(
                "POST",
                API_URL.format(voice_id=voice_id),
                params={"output_format": OUTPUT_FORMAT},
                json=body,
            ) as response:
                if response.status_code != 200:
                    detail = (await response.aread())[:300].decode(errors="replace")
                    if response.status_code == 429:
                        raise TtsError("quota", detail)
                    if response.status_code >= 500:
                        raise TtsError("unavailable", detail)
                    raise TtsError("bad_request", f"{response.status_code}: {detail}")
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
        except TtsError:
            raise
        except httpx.HTTPError as exc:
            raise TtsError("unavailable", type(exc).__name__) from exc

    def synthesize_stream(
        self, text: str, lang: LangCode, voice_id: str, speaking_rate: float = 1.0
    ) -> AsyncIterator[bytes]:
        return with_timeouts(self._raw_stream(text, lang, voice_id, speaking_rate))
