"""Test doubles for TTS. Never touch the network."""

import asyncio
from collections.abc import AsyncIterator

from app.config import LangCode, Voice
from app.services.tts.base import TtsError, TtsErrorCode
from app.services.tts.cache import CachedAudio


class FakeTts:
    def __init__(
        self,
        name: str = "fake",
        *,
        voices: list[str] | None = None,
        fail: list[TtsErrorCode] | None = None,
        fail_mid_stream: bool = False,
        delay_s: float = 0.0,
        mime: str = "audio/mpeg",
    ) -> None:
        self.name = name
        self.model = f"{name}-model"
        self.mime = mime
        self._voices = voices if voices is not None else [f"{name}-F", f"{name}-M"]
        self.fail = list(fail or [])  # one error per call, consumed in order
        self.fail_mid_stream = fail_mid_stream
        self.delay_s = delay_s
        self.calls: list[tuple[str, str, str, float]] = []

    def voices(self, lang: LangCode) -> list[Voice]:
        return [Voice((v, v)) for v in self._voices]

    async def synthesize_stream(
        self, text: str, lang: LangCode, voice_id: str, speaking_rate: float = 1.0
    ) -> AsyncIterator[bytes]:
        self.calls.append((text, lang, voice_id, speaking_rate))
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if self.fail:
            raise TtsError(self.fail.pop(0), "fake failure")
        yield f"{self.name}:".encode()
        if self.fail_mid_stream:
            raise TtsError("unavailable", "dropped")
        yield text.encode()


class MemoryCache:
    def __init__(self) -> None:
        self.entries: dict[str, CachedAudio] = {}

    async def get(self, key: str) -> CachedAudio | None:
        return self.entries.get(key)

    async def put(
        self, key: str, *, provider: str, voice_id: str, model: str, mime: str, audio: bytes
    ) -> None:
        self.entries[key] = CachedAudio(mime=mime, audio=audio)
