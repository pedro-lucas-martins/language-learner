"""TTS provider interface, typed errors and the first-byte timeout helper (SPEC §6)."""

import asyncio
from collections.abc import AsyncIterator
from typing import Literal, Protocol

from app.config import LangCode, Voice

TtsErrorCode = Literal["quota", "unavailable", "bad_request", "not_configured"]

FIRST_BYTE_TIMEOUT_S = 3.0
TOTAL_TIMEOUT_S = 20.0


class TtsError(Exception):
    def __init__(self, code: TtsErrorCode, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail

    @property
    def retryable(self) -> bool:
        return self.code in ("quota", "unavailable")


class TtsProvider(Protocol):
    name: str
    """Provider name; also the `role` of its `usage_events` rows."""
    model: str
    """Model label, part of the cache key."""
    mime: str
    """MIME type of the audio this provider returns."""

    def voices(self, lang: LangCode) -> list[Voice]: ...

    def synthesize_stream(
        self, text: str, lang: LangCode, voice_id: str, speaking_rate: float = 1.0
    ) -> AsyncIterator[bytes]:
        """Yield audio chunks as they arrive. Raise TtsError on failure."""
        ...


async def with_timeouts(
    chunks: AsyncIterator[bytes],
    *,
    first_byte_s: float = FIRST_BYTE_TIMEOUT_S,
    total_s: float = TOTAL_TIMEOUT_S,
) -> AsyncIterator[bytes]:
    """Enforce a time-to-first-byte and a total timeout on a chunk stream."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + total_s
    first = True
    iterator = aiter(chunks)
    try:
        while True:
            budget = min(first_byte_s, deadline - loop.time()) if first else deadline - loop.time()
            if budget <= 0:
                raise TtsError("unavailable", "timeout")
            try:
                chunk = await asyncio.wait_for(anext(iterator), budget)
            except StopAsyncIteration:
                return
            except TimeoutError as exc:
                raise TtsError("unavailable", "timeout") from exc
            if chunk:
                first = False
                yield chunk
    finally:
        aclose = getattr(iterator, "aclose", None)
        if aclose is not None:
            await aclose()


def pick_voice(voices: list[Voice], voice_id: str | None) -> str:
    """The stored voice if the provider offers it for this language, else the first one."""
    ids = [v.id for v in voices]
    if voice_id and voice_id in ids:
        return voice_id
    if not ids:
        raise TtsError("not_configured", "no voices configured for this language")
    return ids[0]
