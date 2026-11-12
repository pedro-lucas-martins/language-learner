"""edge-tts: the free fallback voice (SPEC §6). Not a paid service."""

from collections.abc import AsyncIterator

from app.config import LangCode, Settings, Voice
from app.services.tts.base import TtsError, with_timeouts


class EdgeTts:
    name = "edge"
    model = "edge"
    mime = "audio/mpeg"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def voices(self, lang: LangCode) -> list[Voice]:
        return [Voice((v, v)) for v in self._settings.edge_voices[lang]]

    async def _raw_stream(
        self, text: str, lang: LangCode, voice_id: str, speaking_rate: float
    ) -> AsyncIterator[bytes]:
        import edge_tts  # imported lazily: unused in tests

        rate = f"{round((speaking_rate - 1) * 100):+d}%"
        try:
            async for item in edge_tts.Communicate(text, voice_id, rate=rate).stream():
                if item.get("type") == "audio" and item.get("data"):
                    yield item["data"]
        except Exception as exc:  # noqa: BLE001 — any failure means "try the next fallback"
            raise TtsError("unavailable", type(exc).__name__) from exc

    def synthesize_stream(
        self, text: str, lang: LangCode, voice_id: str, speaking_rate: float = 1.0
    ) -> AsyncIterator[bytes]:
        return with_timeouts(self._raw_stream(text, lang, voice_id, speaking_rate))
