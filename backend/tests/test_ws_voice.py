"""Voice over the WebSocket (SPEC §6, §7): STT → LLM → TTS per sentence, fallback, barge-in."""

import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from starlette.testclient import WebSocketTestSession

from app.main import app
from app.models import Message, UsageEvent
from app.services import stt_service
from app.services.llm import FakeLlm
from app.services.tts.chain import TtsChain
from tests.conftest import ORIGIN, add_user, make_settings, wait_sessions_closed
from tests.fakes_tts import FakeTts, MemoryCache

REPLY = "Cześć Pedro, miło cię poznać! Co dzisiaj robisz po pracy?"
AUDIO = b"\x1a\x45\xdf\xa3" + b"o" * 3000  # opaque bytes; FakeLlm never decodes them


@pytest.fixture
def voice_client(
    sync_engine: Engine, fake_llm: FakeLlm, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setattr(stt_service, "RETRY_DELAY_S", 0)
    fake_llm.reply = REPLY
    original = app.state.settings
    app.state.settings = make_settings(gemini_stt_model="stt-model")
    app.state.llm = fake_llm
    with TestClient(app) as client:
        yield client
        wait_sessions_closed(sync_engine)
    app.state.settings = original
    app.state.llm = None


def _login(ws: WebSocketTestSession, token: str) -> None:
    ws.send_json({"type": "auth", "token": token})
    assert ws.receive_json()["type"] == "ready"
    assert ws.receive_json()["type"] == "usage"


def _events_until(ws: WebSocketTestSession, *last: str) -> list[dict[str, Any]]:
    """Collect frames; binary frames become {"type": "<binary>", "data": ...}."""
    events: list[dict[str, Any]] = []
    while True:
        frame = ws.receive()
        if frame.get("bytes") is not None:
            events.append({"type": "<binary>", "data": frame["bytes"]})
            continue
        event = json.loads(frame["text"])
        events.append(event)
        if event["type"] in last:
            return events


def _speak(ws: WebSocketTestSession, audio: bytes = AUDIO) -> None:
    ws.send_json({"type": "start_of_speech", "mime": "audio/webm;codecs=opus"})
    ws.send_bytes(audio)
    ws.send_json({"type": "end_of_speech"})


def _audio_by_sentence(events: list[dict[str, Any]]) -> dict[int, bytes]:
    """Check that every binary frame follows one audio_meta, and join chunks per sentence."""
    out: dict[int, bytes] = {}
    for i, event in enumerate(events):
        if event["type"] == "<binary>":
            meta = events[i - 1]
            assert meta["type"] == "audio_meta"
            out[meta["sentence"]] = out.get(meta["sentence"], b"") + event["data"]
    return out


def _install_tts(active: FakeTts | None, edge: FakeTts) -> None:
    app.state.tts = TtsChain(active, edge, cache=MemoryCache(), retry_delay_s=0)


def test_voice_turn_end_to_end(
    voice_client: TestClient, sync_engine: Engine, fake_llm: FakeLlm
) -> None:
    token = add_user(sync_engine)
    with voice_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        _speak(ws)
        events = _events_until(ws, "usage", "error")

    types = [e["type"] for e in events]
    assert types[0] == "transcript" and events[0]["text"] == fake_llm.transcript
    assert fake_llm.transcribe_calls[0]["mime"] == "audio/webm"
    assert fake_llm.stream_calls[-1]["history"] == [("user", fake_llm.transcript)]

    # Two sentences, each spoken by the active provider, each ending with final=true.
    audio = _audio_by_sentence(events)
    assert set(audio) == {0, 1}
    assert audio[0] == "google:Cześć Pedro, miło cię poznać!".encode()
    assert audio[1] == b"google:Co dzisiaj robisz po pracy?"
    metas = [e for e in events if e["type"] == "audio_meta"]
    for sentence in (0, 1):
        last = [m for m in metas if m["sentence"] == sentence][-1]
        assert last["final"] is True and last["mime"] == "audio/mpeg"
    assert [m["seq"] for m in metas] == list(range(len(metas)))

    metrics = next(e for e in events if e["type"] == "metrics")
    assert metrics["stt_ms"] is not None
    assert metrics["llm_first_token_ms"] is not None and metrics["first_audio_ms"] is not None
    assert metrics["total_ms"] >= metrics["first_audio_ms"]
    assert types[-1] == "usage" and events[-1]["tts_provider_active"] == "google"

    with Session(sync_engine) as db:
        kinds = {(u.kind, u.role) for u in db.scalars(select(UsageEvent))}
    assert {("llm_in", "stt"), ("stt_audio_s", "stt"), ("tts_chars", "google")} <= kinds


def test_typed_turn_is_spoken_too(voice_client: TestClient, sync_engine: Engine) -> None:
    token = add_user(sync_engine)
    with voice_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        ws.send_json({"type": "user_text", "text": "Cześć"})
        events = _events_until(ws, "usage", "error")
    assert set(_audio_by_sentence(events)) == {0, 1}
    metrics = next(e for e in events if e["type"] == "metrics")
    assert metrics["stt_ms"] is None


def test_active_provider_failure_falls_back_to_edge(
    voice_client: TestClient, sync_engine: Engine
) -> None:
    _install_tts(FakeTts("google", fail=["unavailable"] * 10), FakeTts("edge"))
    token = add_user(sync_engine)
    with voice_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        _speak(ws)
        events = _events_until(ws, "usage", "error")
    audio = _audio_by_sentence(events)
    assert audio and all(chunk.startswith(b"edge:") for chunk in audio.values())
    assert not any(e["type"] == "tts_fallback" for e in events)


def test_everything_failing_asks_the_browser_to_speak(
    voice_client: TestClient, sync_engine: Engine
) -> None:
    _install_tts(
        FakeTts("google", fail=["unavailable"] * 10), FakeTts("edge", fail=["unavailable"] * 10)
    )
    token = add_user(sync_engine, native="pl-PL")
    with voice_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        ws.send_json({"type": "user_text", "text": "Oi"})
        events = _events_until(ws, "usage", "error")
    fallbacks = [e for e in events if e["type"] == "tts_fallback"]
    assert [f["sentence"] for f in fallbacks] == [0, 1]
    assert {f["lang"] for f in fallbacks} == {"pt-BR"}  # the AI speaks the learner's target
    assert not _audio_by_sentence(events)


def test_over_allowance_uses_the_free_fallback(
    voice_client: TestClient, sync_engine: Engine
) -> None:
    app.state.settings = make_settings(gemini_stt_model="stt-model", daily_tts_chars_per_user=1)
    token = add_user(sync_engine)
    with voice_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        ws.send_json({"type": "user_text", "text": "Hej"})
        first = _events_until(ws, "usage", "error")  # spends paid characters
        ws.send_json({"type": "user_text", "text": "Hej znowu"})
        second = _events_until(ws, "usage", "error")
    assert all(c.startswith(b"google:") for c in _audio_by_sentence(first).values())
    assert all(c.startswith(b"edge:") for c in _audio_by_sentence(second).values())
    assert second[-1]["tts_provider_active"] == "edge"


def test_barge_in_cancels_the_turn_and_keeps_partial_text(
    voice_client: TestClient, sync_engine: Engine, fake_llm: FakeLlm
) -> None:
    fake_llm.stream_delay_s = 0.05
    token = add_user(sync_engine)
    with voice_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        ws.send_json({"type": "user_text", "text": "Opowiedz mi coś"})
        started = _events_until(ws, "ai_text_delta")
        ws.send_json({"type": "user_started_speaking"})
        rest = _events_until(ws, "interrupted")
        ai_id = started[-1]["message_id"]
        assert rest[-1] == {"type": "interrupted", "message_id": ai_id}
        assert not any(e["type"] == "ai_text_done" for e in rest)
        # The socket is still usable after the interruption.
        fake_llm.stream_delay_s = 0
        ws.send_json({"type": "user_text", "text": "Dobrze"})
        assert _events_until(ws, "usage", "error")[-1]["type"] == "usage"

    with Session(sync_engine) as db:
        partial = db.get(Message, uuid.UUID(ai_id))
        assert partial is not None and partial.role == "ai"
        assert 0 < len(partial.text) < len(REPLY)


def test_stt_failure_is_reported(
    voice_client: TestClient, sync_engine: Engine, fake_llm: FakeLlm
) -> None:
    fake_llm.transcribe_failures = ["unavailable", "unavailable"]
    token = add_user(sync_engine)
    with voice_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        _speak(ws)
        events = _events_until(ws, "usage", "error")
    assert events == [
        {
            "type": "error",
            "code": "stt_failed",
            "message": "Não consegui entender o áudio. Tente de novo.",
        }
    ]
    assert fake_llm.stream_calls == []


def test_daily_stt_cap_blocks_before_calling_the_api(
    voice_client: TestClient, sync_engine: Engine, fake_llm: FakeLlm
) -> None:
    app.state.settings = make_settings(gemini_stt_model="stt-model", daily_stt_seconds_per_user=1)
    token = add_user(sync_engine)
    with voice_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        _speak(ws, b"x" * 40_000)  # ~10 s of Opus
        events = _events_until(ws, "usage", "error")
    assert events[-1]["code"] == "quota_exceeded"
    assert fake_llm.transcribe_calls == []


@pytest.mark.parametrize(
    "frames",
    [
        [b"audio-without-start"],
        [{"type": "end_of_speech"}],
        [{"type": "start_of_speech", "mime": "audio/webm"}, {"type": "end_of_speech"}],
        [{"type": "start_of_speech", "mime": "audio/webm", "purpose": "pron_retry"}],
    ],
)
def test_malformed_voice_sequences_return_bad_request(
    voice_client: TestClient, sync_engine: Engine, frames: list[Any]
) -> None:
    token = add_user(sync_engine)
    with voice_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        for frame in frames:
            if isinstance(frame, bytes):
                ws.send_bytes(frame)
            else:
                ws.send_json(frame)
        assert ws.receive_json()["code"] == "bad_request"


def test_oversized_utterance_is_rejected(voice_client: TestClient, sync_engine: Engine) -> None:
    from app.routers import ws_chat

    token = add_user(sync_engine)
    with voice_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        ws.send_json({"type": "start_of_speech", "mime": "audio/webm"})
        ws.send_bytes(b"x" * (ws_chat.MAX_UTTERANCE_BYTES + 1))
        assert ws.receive_json()["code"] == "bad_request"


def test_stt_gets_the_last_ai_reply_as_context(
    voice_client: TestClient, sync_engine: Engine, fake_llm: FakeLlm
) -> None:
    token = add_user(sync_engine)
    with voice_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        _speak(ws)
        _events_until(ws, "usage", "error")
        _speak(ws)
        _events_until(ws, "usage", "error")
    first, second = fake_llm.transcribe_calls[:2]
    assert "Context" not in str(first["system"])  # nothing said yet
    assert f"«{REPLY}»" in str(second["system"])
