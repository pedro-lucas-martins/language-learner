"""TTS cache: key, round trip and LRU eviction against the real table (SQLite)."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.database import session_factory
from app.models import TtsCache, utcnow
from app.services.tts.cache import DbTtsCache, cache_key, evict_lru


def test_cache_key_changes_with_every_part() -> None:
    base = cache_key("google", "v1", "m", 1.0, "Cześć")
    assert base == cache_key("google", "v1", "m", 1.0, "Cześć")
    assert len(base) == 64
    variants = [
        cache_key("edge", "v1", "m", 1.0, "Cześć"),
        cache_key("google", "v2", "m", 1.0, "Cześć"),
        cache_key("google", "v1", "m2", 1.0, "Cześć"),
        cache_key("google", "v1", "m", 0.8, "Cześć"),
        cache_key("google", "v1", "m", 1.0, "Cześć!"),
    ]
    assert base not in variants and len(set(variants)) == len(variants)


async def test_round_trip(sync_engine: Engine) -> None:
    cache = DbTtsCache(max_mb=1)
    assert await cache.get("k") is None
    await cache.put("k", provider="google", voice_id="v", model="m", mime="audio/ogg", audio=b"abc")
    hit = await cache.get("k")
    assert hit is not None and hit.audio == b"abc" and hit.mime == "audio/ogg"


async def test_lru_eviction_removes_least_recently_used(sync_engine: Engine) -> None:
    now = utcnow()
    with Session(sync_engine) as db:
        for i, age in enumerate([30, 20, 10]):  # k0 oldest
            db.add(
                TtsCache(
                    hash=f"k{i}",
                    provider="p",
                    voice_id="v",
                    model="m",
                    mime="x",
                    audio=b"x" * 100,
                    bytes=100,
                    last_used_at=now - timedelta(minutes=age),
                )
            )
        db.commit()
    async with session_factory()() as db:
        deleted = await evict_lru(db, max_bytes=150)
    assert deleted == 2
    with Session(sync_engine) as db:
        assert list(db.scalars(select(TtsCache.hash))) == ["k2"]


async def test_get_refreshes_last_used(sync_engine: Engine) -> None:
    old = utcnow() - timedelta(days=1)
    with Session(sync_engine) as db:
        db.add(
            TtsCache(
                hash="k",
                provider="p",
                voice_id="v",
                model="m",
                mime="x",
                audio=b"x",
                bytes=1,
                last_used_at=old,
            )
        )
        db.commit()
    await DbTtsCache(max_mb=1).get("k")
    with Session(sync_engine) as db:
        refreshed = db.get(TtsCache, "k")
        assert refreshed is not None
        assert refreshed.last_used_at.replace(tzinfo=None) > old.replace(tzinfo=None)


async def test_oversized_audio_is_not_stored(sync_engine: Engine) -> None:
    cache = DbTtsCache(max_mb=0)
    await cache.put("k", provider="p", voice_id="v", model="m", mime="x", audio=b"abc")
    assert await cache.get("k") is None
