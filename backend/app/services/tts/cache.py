"""TTS audio cache in Postgres with LRU eviction (SPEC §6).

Key = sha256(provider + voice + model + rate + text), so the same text is never
synthesized twice by the same voice.
"""

import hashlib
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import session_factory
from app.models import TtsCache, utcnow


def cache_key(provider: str, voice_id: str, model: str, speaking_rate: float, text: str) -> str:
    raw = "\x1f".join([provider, voice_id, model, f"{speaking_rate:.2f}", text])
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class CachedAudio:
    mime: str
    audio: bytes


class TtsCacheStore(Protocol):
    async def get(self, key: str) -> CachedAudio | None: ...

    async def put(
        self, key: str, *, provider: str, voice_id: str, model: str, mime: str, audio: bytes
    ) -> None: ...


async def evict_lru(db: AsyncSession, max_bytes: int) -> int:
    """Delete least-recently-used entries until the cache fits in `max_bytes`.

    Returns the number of rows deleted.
    """
    total = int(await db.scalar(select(func.coalesce(func.sum(TtsCache.bytes), 0))) or 0)
    if total <= max_bytes:
        return 0
    rows = await db.execute(select(TtsCache.hash, TtsCache.bytes).order_by(TtsCache.last_used_at))
    doomed: list[str] = []
    for key, size in rows:
        if total <= max_bytes:
            break
        doomed.append(key)
        total -= size
    for entry in await db.scalars(select(TtsCache).where(TtsCache.hash.in_(doomed))):
        await db.delete(entry)
    await db.commit()
    return len(doomed)


class DbTtsCache:
    """Cache backed by the `tts_cache` table."""

    def __init__(self, max_mb: int) -> None:
        self._max_bytes = max_mb * 1024 * 1024

    async def get(self, key: str) -> CachedAudio | None:
        async with session_factory()() as db:
            row = await db.get(TtsCache, key)
            if row is None:
                return None
            await db.execute(
                update(TtsCache).where(TtsCache.hash == key).values(last_used_at=utcnow())
            )
            await db.commit()
            return CachedAudio(mime=row.mime, audio=row.audio)

    async def put(
        self, key: str, *, provider: str, voice_id: str, model: str, mime: str, audio: bytes
    ) -> None:
        if self._max_bytes <= 0 or len(audio) > self._max_bytes:
            return
        async with session_factory()() as db:
            await db.merge(
                TtsCache(
                    hash=key,
                    provider=provider,
                    voice_id=voice_id,
                    model=model,
                    mime=mime,
                    audio=audio,
                    bytes=len(audio),
                    last_used_at=utcnow(),
                )
            )
            await db.commit()
            await evict_lru(db, self._max_bytes)
