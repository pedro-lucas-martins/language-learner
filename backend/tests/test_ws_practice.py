"""Listen and repeat over the WebSocket: speak_word, pron_retry, and cards from feedback."""

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from starlette.testclient import WebSocketTestSession

from app.main import app
from app.models import Flashcard, UsageEvent
from app.services import feedback as feedback_mod
from app.services.llm import FakeLlm
from app.services.tts.chain import TtsChain
from tests.conftest import ORIGIN, add_user, make_settings, wait_sessions_closed
from tests.fakes_tts import FakeTts, MemoryCache


@pytest.fixture
def practice_client(
    sync_engine: Engine, fake_llm: FakeLlm, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setattr(feedback_mod, "RETRY_DELAY_S", 0)
    original = app.state.settings
    app.state.settings = make_settings(gemini_stt_model="stt", gemini_feedback_model="fb-model")
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


def _frames_until(ws: WebSocketTestSession, last: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    while True:
        frame = ws.receive()
        if frame.get("bytes") is not None:
            out.append({"type": "<binary>", "data": frame["bytes"]})
            continue
        event = json.loads(frame["text"])
        out.append(event)
        if event["type"] == last or (
            event["type"] == "audio_meta" and last == "final" and event["final"]
        ):
            if last == "final":
                frame = ws.receive()
                out.append({"type": "<binary>", "data": frame["bytes"]})
            return out


def test_speak_word_uses_the_cache_the_second_time(
    practice_client: TestClient, sync_engine: Engine, fake_tts: TtsChain
) -> None:
    token = add_user(sync_engine)
    with practice_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        for _ in range(2):
            ws.send_json({"type": "speak_word", "word": "szczęście"})
            frames = _frames_until(ws, "final")
            meta = next(f for f in frames if f["type"] == "audio_meta")
            assert meta["message_id"] == "word:szczęście" and meta["sentence"] == 0
            assert b"".join(f["data"] for f in frames if f["type"] == "<binary>").endswith(
                "szczęście".encode()
            )
    active = fake_tts.active
    assert isinstance(active, FakeTts) and len(active.calls) == 1
    with Session(sync_engine) as db:
        rows = db.scalars(select(UsageEvent).where(UsageEvent.kind == "tts_chars")).all()
    assert len(rows) == 1


def test_speak_word_falls_back_to_the_browser(
    practice_client: TestClient, sync_engine: Engine
) -> None:
    app.state.tts = TtsChain(
        FakeTts("google", fail=["unavailable"] * 4),
        FakeTts("edge", fail=["unavailable"] * 4),
        cache=MemoryCache(),
        retry_delay_s=0,
    )
    token = add_user(sync_engine)
    with practice_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        ws.send_json({"type": "speak_word", "word": "pão"})
        fallback = _frames_until(ws, "tts_fallback")[-1]
    assert fallback == {
        "type": "tts_fallback",
        "message_id": "word:pão",
        "sentence": 0,
        "text": "pão",
        "lang": "pl-PL",
    }


def test_pron_retry_returns_a_verdict_and_records_usage(
    practice_client: TestClient, sync_engine: Engine, fake_llm: FakeLlm
) -> None:
    fake_llm.analysis = '{"better": true, "tip": "Muito melhor! O ł saiu como w."}'
    token = add_user(sync_engine)
    with practice_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        ws.send_json(
            {
                "type": "start_of_speech",
                "mime": "audio/webm",
                "purpose": "pron_retry",
                "target_word": "łóżko",
                "message_id": "m1",
            }
        )
        ws.send_bytes(b"o" * 3000)
        ws.send_json({"type": "end_of_speech"})
        result = _frames_until(ws, "pron_result")[-1]
    assert result == {
        "type": "pron_result",
        "message_id": "m1",
        "word": "łóżko",
        "better": True,
        "tip": "Muito melhor! O ł saiu como w.",
    }
    call = fake_llm.analyze_calls[-1]
    assert call["audio"] is not None and '"łóżko"' in str(call["system"])
    assert "written in Brazilian Portuguese" in str(call["system"])
    assert fake_llm.transcribe_calls == []  # judged directly from audio, no STT step
    with Session(sync_engine) as db:
        kinds = {(u.kind, u.role) for u in db.scalars(select(UsageEvent))}
    assert {("llm_in", "feedback"), ("stt_audio_s", "feedback")} <= kinds


def test_pron_retry_with_bad_model_output_reports_stt_failed(
    practice_client: TestClient, sync_engine: Engine, fake_llm: FakeLlm
) -> None:
    fake_llm.analysis = "nope"
    token = add_user(sync_engine)
    with practice_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        ws.send_json(
            {
                "type": "start_of_speech",
                "mime": "audio/webm",
                "purpose": "pron_retry",
                "target_word": "kot",
                "message_id": "m1",
            }
        )
        ws.send_bytes(b"o" * 3000)
        ws.send_json({"type": "end_of_speech"})
        assert _frames_until(ws, "error")[-1]["code"] == "stt_failed"


def test_feedback_with_mistakes_creates_flashcards(
    practice_client: TestClient, sync_engine: Engine, fake_llm: FakeLlm
) -> None:
    fake_llm.analysis = json.dumps(
        {
            "ok": False,
            "errs": [{"e": "dwa kot", "c": "dwa koty", "r": "plural", "p": ""}],
            "pron": [],
        }
    )
    token = add_user(sync_engine)
    with practice_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        ws.send_json({"type": "user_text", "text": "Ja mam dwa kot w domu."})
        seen: set[str] = set()
        while not {"feedback", "usage"} <= seen:  # they may arrive in either order
            frame = ws.receive()
            if frame.get("text"):
                seen.add(json.loads(frame["text"])["type"])
    with Session(sync_engine) as db:
        stored = db.scalars(select(Flashcard)).all()
    assert [(c.kind, c.front, c.lang) for c in stored] == [
        ("grammar", "Ja mam «dwa kot» w domu.", "pl-PL")
    ]
