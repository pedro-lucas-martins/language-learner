"""Fallback chain rules (SPEC §6): active → edge → browser; usage; cache; timeouts."""

import asyncio
from collections.abc import AsyncIterator

import pytest

from app.config import Voice
from app.services.tts.base import TtsError, pick_voice, with_timeouts
from app.services.tts.chain import TtsChain, TtsChunk, TtsUnavailable
from tests.fakes_tts import FakeTts, MemoryCache


class Recorder:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, int]] = []

    async def __call__(self, provider: str, model: str, chars: int) -> None:
        self.rows.append((provider, model, chars))


async def collect(stream: AsyncIterator[TtsChunk]) -> list[TtsChunk]:
    return [chunk async for chunk in stream]


def make_chain(active: FakeTts | None, fallback: FakeTts, cache: MemoryCache | None = None):
    record = Recorder()
    chain = TtsChain(active, fallback, record=record, cache=cache, retry_delay_s=0)
    return chain, record


async def test_active_provider_streams_and_records_usage() -> None:
    active, edge = FakeTts("google"), FakeTts("edge")
    chain, record = make_chain(active, edge)
    chunks = await collect(chain.stream("Cześć!", "pl-PL", None))
    assert b"".join(c.data for c in chunks) == b"google:Cze\xc5\x9b\xc4\x87!"
    assert {c.provider for c in chunks} == {"google"}
    assert record.rows == [("google", "google-model", 6)]
    assert edge.calls == []


async def test_stored_voice_is_used_when_offered() -> None:
    active = FakeTts("google")
    chain, _ = make_chain(active, FakeTts("edge"))
    await collect(chain.stream("Olá", "pt-BR", "google-M"))
    assert active.calls[0][2] == "google-M"


async def test_unknown_voice_uses_first_voice() -> None:
    active = FakeTts("google")
    chain, _ = make_chain(active, FakeTts("edge"))
    await collect(chain.stream("Olá", "pt-BR", "someone-else"))
    assert active.calls[0][2] == "google-F"


async def test_transient_error_is_retried_once() -> None:
    active = FakeTts("google", fail=["unavailable"])
    chain, record = make_chain(active, FakeTts("edge"))
    chunks = await collect(chain.stream("Hej", "pl-PL", None))
    assert len(active.calls) == 2
    assert chunks[0].provider == "google"
    assert record.rows == [("google", "google-model", 3)]


async def test_persistent_failure_falls_back_to_edge_with_same_voice_position() -> None:
    active = FakeTts("google", fail=["quota", "quota"])
    edge = FakeTts("edge")
    chain, record = make_chain(active, edge)
    chunks = await collect(chain.stream("Hej", "pl-PL", "google-M"))
    assert {c.provider for c in chunks} == {"edge"}
    assert edge.calls[0][2] == "edge-M"  # second voice → second fallback voice
    assert record.rows == [("edge", "edge-model", 3)]


async def test_bad_request_is_not_retried() -> None:
    active = FakeTts("google", fail=["bad_request"])
    chain, _ = make_chain(active, FakeTts("edge"))
    chunks = await collect(chain.stream("Hej", "pl-PL", None))
    assert len(active.calls) == 1
    assert chunks[0].provider == "edge"


async def test_over_allowance_skips_the_active_provider() -> None:
    active, edge = FakeTts("google"), FakeTts("edge")
    chain, _ = make_chain(active, edge)
    chunks = await collect(chain.stream("Hej", "pl-PL", None, over_allowance=True))
    assert active.calls == []
    assert chunks[0].provider == "edge"


async def test_missing_active_provider_uses_edge() -> None:
    edge = FakeTts("edge")
    chain, _ = make_chain(None, edge)
    chunks = await collect(chain.stream("Hej", "pl-PL", None))
    assert chunks[0].provider == "edge"


async def test_everything_failing_raises_tts_unavailable() -> None:
    active = FakeTts("google", fail=["unavailable", "unavailable"])
    edge = FakeTts("edge", fail=["unavailable", "unavailable"])
    chain, record = make_chain(active, edge)
    with pytest.raises(TtsUnavailable):
        await collect(chain.stream("Hej", "pl-PL", None))
    assert record.rows == []


async def test_mid_stream_failure_stops_without_switching_provider() -> None:
    active, edge = FakeTts("google", fail_mid_stream=True), FakeTts("edge")
    chain, record = make_chain(active, edge)
    chunks = await collect(chain.stream("Hej", "pl-PL", None))
    assert [c.data for c in chunks] == [b"google:"]
    assert edge.calls == []
    assert record.rows == [("google", "google-model", 3)]


async def test_cache_hit_skips_synthesis_and_usage() -> None:
    cache = MemoryCache()
    active = FakeTts("google")
    chain, record = make_chain(active, FakeTts("edge"), cache)
    first = await collect(chain.stream("Hej", "pl-PL", None))
    second = await collect(chain.stream("Hej", "pl-PL", None))
    assert len(active.calls) == 1
    assert b"".join(c.data for c in first) == second[0].data
    assert len(record.rows) == 1


async def test_cache_key_depends_on_speaking_rate() -> None:
    cache = MemoryCache()
    active = FakeTts("google")
    chain, _ = make_chain(active, FakeTts("edge"), cache)
    await collect(chain.stream("Hej", "pl-PL", None, 1.0))
    await collect(chain.stream("Hej", "pl-PL", None, 0.8))
    assert len(active.calls) == 2


async def test_first_byte_timeout_becomes_unavailable() -> None:
    async def slow() -> AsyncIterator[bytes]:
        await asyncio.sleep(1)
        yield b"late"

    with pytest.raises(TtsError) as exc_info:
        async for _ in with_timeouts(slow(), first_byte_s=0.01, total_s=5):
            pass
    assert exc_info.value.code == "unavailable"


async def test_slow_provider_falls_back_via_timeout() -> None:
    class Slow(FakeTts):
        def synthesize_stream(self, text, lang, voice_id, speaking_rate=1.0):  # type: ignore[no-untyped-def]
            return with_timeouts(
                super().synthesize_stream(text, lang, voice_id, speaking_rate),
                first_byte_s=0.01,
                total_s=5,
            )

    active = Slow("google", delay_s=0.5)
    chain, _ = make_chain(active, FakeTts("edge"))
    chunks = await collect(chain.stream("Hej", "pl-PL", None))
    assert chunks[0].provider == "edge"


def test_pick_voice_without_voices_is_not_configured() -> None:
    with pytest.raises(TtsError) as exc_info:
        pick_voice([], "x")
    assert exc_info.value.code == "not_configured"
    assert pick_voice([Voice(("a", "A"))], None) == "a"
