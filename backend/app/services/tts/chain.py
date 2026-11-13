"""TTS fallback chain (SPEC §6): active provider → backup provider → edge-tts → browser.

The chain switches provider only before the first audio byte. If every provider fails
it raises `TtsUnavailable` and the caller sends `tts_fallback` so the browser speaks.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

from app.config import LangCode, Settings
from app.services.tts.base import TtsError, TtsProvider, pick_voice
from app.services.tts.cache import TtsCacheStore, cache_key

log = logging.getLogger(__name__)

RETRY_DELAY_S = 0.5

# (provider name, model, characters) — writes one `usage_events` row.
RecordTts = Callable[[str, str, int], Awaitable[None]]


@dataclass(frozen=True)
class TtsChunk:
    data: bytes
    mime: str
    provider: str


class TtsUnavailable(Exception):
    """Every server-side provider failed; the browser must speak the text."""


class TtsChain:
    def __init__(
        self,
        active: TtsProvider | None,
        fallback: TtsProvider,
        *,
        backup: TtsProvider | None = None,
        cache: TtsCacheStore | None = None,
        retry_delay_s: float = RETRY_DELAY_S,
    ) -> None:
        self.active = active
        self.fallback = fallback
        self.backup = backup
        self._cache = cache
        self._retry_delay_s = retry_delay_s

    def _plan(
        self, lang: LangCode, voice_id: str | None, use_active: bool, use_backup: bool = True
    ) -> list[tuple[TtsProvider, str]]:
        """Providers to try with the voice each one should use.

        Every later provider uses the voice at the same position as the active provider's
        voice, so the gender is kept when the lists are ordered alike.
        """
        plan: list[tuple[TtsProvider, str]] = []
        index = 0
        if self.active is not None:
            try:
                voices = self.active.voices(lang)
                chosen = pick_voice(voices, voice_id)
                index = [v.id for v in voices].index(chosen)
                if use_active:
                    plan.append((self.active, chosen))
            except TtsError as exc:
                log.warning("TTS %s skipped: %s", self.active.name, exc)
        if self.backup is not None and use_backup:
            backup_voices = self.backup.voices(lang)
            if backup_voices:
                plan.append((self.backup, backup_voices[min(index, len(backup_voices) - 1)].id))
        fallback_voices = self.fallback.voices(lang)
        if fallback_voices:
            # Same position in the list, so the fallback keeps the voice's gender when the
            # lists are ordered alike.
            plan.append((self.fallback, fallback_voices[min(index, len(fallback_voices) - 1)].id))
        return plan

    async def stream(
        self,
        text: str,
        lang: LangCode,
        voice_id: str | None,
        speaking_rate: float = 1.0,
        *,
        record: RecordTts,
        over_allowance: bool = False,
        backup_over_allowance: bool = False,
    ) -> AsyncIterator[TtsChunk]:
        plan = self._plan(
            lang, voice_id, use_active=not over_allowance, use_backup=not backup_over_allowance
        )
        for provider, voice in plan:
            key = cache_key(provider.name, voice, provider.model, speaking_rate, text)
            if self._cache is not None:
                hit = await self._cache.get(key)
                if hit is not None:
                    yield TtsChunk(hit.audio, hit.mime, provider.name)
                    return
            for attempt in range(2):
                parts: list[bytes] = []
                try:
                    async for data in provider.synthesize_stream(text, lang, voice, speaking_rate):
                        if not parts:
                            # Billed once the provider starts sending audio.
                            await record(provider.name, provider.model, len(text))
                        parts.append(data)
                        yield TtsChunk(data, provider.mime, provider.name)
                except TtsError as exc:
                    if parts:
                        log.warning("TTS %s failed mid-stream: %s", provider.name, exc)
                        return  # part of the sentence was already sent; do not repeat it
                    log.warning("TTS %s attempt %d failed: %s", provider.name, attempt + 1, exc)
                    if exc.retryable and attempt == 0:
                        await asyncio.sleep(self._retry_delay_s)
                        continue
                    break
                if self._cache is not None and parts:
                    await self._cache.put(
                        key,
                        provider=provider.name,
                        voice_id=voice,
                        model=provider.model,
                        mime=provider.mime,
                        audio=b"".join(parts),
                    )
                return
        raise TtsUnavailable(text)


def build_active_provider(settings: Settings) -> TtsProvider | None:
    """The provider selected by TTS_PROVIDER, or None when it has no credentials."""
    if not settings.tts_provider_configured(settings.tts_provider):
        return None
    if settings.tts_provider == "google":
        from app.services.tts.google import GoogleTts

        return GoogleTts(settings)
    from app.services.tts.elevenlabs import ElevenLabsTts

    return ElevenLabsTts(settings)


def _build(settings: Settings, name: str) -> TtsProvider:
    if name == "google":
        from app.services.tts.google import GoogleTts

        return GoogleTts(settings)
    from app.services.tts.elevenlabs import ElevenLabsTts

    return ElevenLabsTts(settings)


def build_backup_provider(settings: Settings) -> TtsProvider | None:
    """TTS_FALLBACK_PROVIDER, when set, different from the active one and configured."""
    name = settings.tts_fallback_provider
    if not name or name == settings.tts_provider or not settings.tts_provider_configured(name):
        return None
    return _build(settings, name)
