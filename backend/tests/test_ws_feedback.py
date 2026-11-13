"""Track 2 over the WebSocket: feedback events, recast, set_recast and regrade."""

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
from app.models import Message, UsageEvent, User
from app.services import feedback as feedback_mod
from app.services import stt_service
from app.services.llm import FakeLlm
from tests.conftest import ORIGIN, add_user, make_settings, wait_sessions_closed

ANALYSIS = json.dumps(
    {
        "ok": False,
        "errs": [{"e": "dwa kot", "c": "dwa koty", "r": "Depois de 2–4 usa-se o plural.", "p": ""}],
        "pron": [{"w": "kot", "heard": "kotchi", "tip": "Sem vogal no fim.", "sev": "major"}],
    },
    ensure_ascii=False,
)


@pytest.fixture
def fb_client(
    sync_engine: Engine, fake_llm: FakeLlm, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setattr(stt_service, "RETRY_DELAY_S", 0)
    monkeypatch.setattr(feedback_mod, "RETRY_DELAY_S", 0)
    fake_llm.transcript = "Ja mam dwa kot w domu."
    fake_llm.analysis = ANALYSIS
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


def _until(ws: WebSocketTestSession, *types: str) -> list[dict[str, Any]]:
    """Collect JSON events (binary audio skipped) until every given type was seen."""
    seen: list[dict[str, Any]] = []
    wanted = set(types)
    while wanted:
        frame = ws.receive()
        if frame.get("bytes") is not None:
            continue
        event = json.loads(frame["text"])
        seen.append(event)
        wanted.discard(event["type"])
    return seen


def _speak(ws: WebSocketTestSession) -> None:
    ws.send_json({"type": "start_of_speech", "mime": "audio/webm;codecs=opus"})
    ws.send_bytes(b"o" * 3000)
    ws.send_json({"type": "end_of_speech"})


def test_voice_turn_gets_grammar_and_pronunciation(
    fb_client: TestClient, sync_engine: Engine, fake_llm: FakeLlm
) -> None:
    token = add_user(sync_engine)
    with fb_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        _speak(ws)
        events = _until(ws, "feedback", "usage")
    transcript = next(e for e in events if e["type"] == "transcript")
    feedback = next(e for e in events if e["type"] == "feedback")
    assert feedback["message_id"] == transcript["message_id"]
    assert feedback["source"] == "audio" and feedback["ok"] is False
    assert feedback["errs"][0]["c"] == "dwa koty"
    assert feedback["pron"][0]["w"] == "kot"

    call = fake_llm.analyze_calls[0]
    assert call["model"] == "fb-model" and call["audio"] is not None
    assert "written in Brazilian Portuguese" in str(call["system"])
    with Session(sync_engine) as db:
        stored = db.get(Message, uuid.UUID(feedback["message_id"]))
        assert stored is not None and json.loads(stored.feedback or "")["errs"]
        roles = {u.role for u in db.scalars(select(UsageEvent))}
    assert "feedback" in roles


def test_recast_sends_audio_to_the_chat_model_only_when_enabled(
    fb_client: TestClient, sync_engine: Engine, fake_llm: FakeLlm
) -> None:
    token = add_user(sync_engine)
    with fb_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        _speak(ws)
        _until(ws, "usage", "feedback")
        assert fake_llm.stream_calls[-1]["audio"] is not None
        assert "Pronunciation recast" in str(fake_llm.stream_calls[-1]["system"])

        ws.send_json({"type": "set_recast", "enabled": False})
        updated = _until(ws, "user_updated")[-1]
        assert updated["user"]["recast_pronunciation"] is False
        _speak(ws)
        _until(ws, "usage", "feedback")
        assert fake_llm.stream_calls[-1]["audio"] is None
        assert "Pronunciation recast" not in str(fake_llm.stream_calls[-1]["system"])
    with Session(sync_engine) as db:
        assert db.scalars(select(User)).one().recast_pronunciation is False


def test_typed_turn_gets_grammar_only(
    fb_client: TestClient, sync_engine: Engine, fake_llm: FakeLlm
) -> None:
    token = add_user(sync_engine)
    with fb_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        ws.send_json({"type": "user_text", "text": "Ja mam dwa kot w domu."})
        feedback = next(e for e in _until(ws, "feedback", "usage") if e["type"] == "feedback")
    assert feedback["source"] == "text" and feedback["pron"] == []
    assert fake_llm.analyze_calls[0]["audio"] is None
    assert fake_llm.stream_calls[-1]["audio"] is None  # typed turns never recast


def test_short_messages_are_not_analysed(
    fb_client: TestClient, sync_engine: Engine, fake_llm: FakeLlm
) -> None:
    token = add_user(sync_engine)
    with fb_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        ws.send_json({"type": "user_text", "text": "Cześć Kasia"})
        _until(ws, "usage")
    assert fake_llm.analyze_calls == []


def test_regrade_updates_the_message_and_reruns_grammar(
    fb_client: TestClient, sync_engine: Engine, fake_llm: FakeLlm
) -> None:
    token = add_user(sync_engine)
    with fb_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        _speak(ws)
        events = _until(ws, "feedback", "usage")
        msg_id = next(e for e in events if e["type"] == "transcript")["message_id"]
        fake_llm.analysis = '{"ok": true}'
        ws.send_json({"type": "regrade", "message_id": msg_id, "text": "Ja mam dwa koty w domu."})
        regraded = _until(ws, "feedback")[-1]
    assert regraded == {
        "type": "feedback",
        "message_id": msg_id,
        "source": "text",
        "ok": True,
        "errs": [],
        "pron": [],
    }
    assert fake_llm.analyze_calls[-1]["audio"] is None
    with Session(sync_engine) as db:
        stored = db.get(Message, uuid.UUID(msg_id))
        assert stored is not None and stored.text == "Ja mam dwa koty w domu."


@pytest.mark.parametrize("target", ["not-a-uuid", str(uuid.uuid4()), "ai"])
def test_regrade_rejects_unknown_or_foreign_messages(
    fb_client: TestClient, sync_engine: Engine, target: str
) -> None:
    token = add_user(sync_engine)
    with fb_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        if target == "ai":  # an AI message cannot be regraded
            ws.send_json({"type": "user_text", "text": "Cześć Kasia"})
            target = next(e for e in _until(ws, "ai_text_done") if e["type"] == "ai_text_done")[
                "message_id"
            ]
            _until(ws, "usage")
        ws.send_json({"type": "regrade", "message_id": target, "text": "Nowy tekst tutaj"})
        assert _until(ws, "error")[-1]["code"] == "bad_request"


def test_barge_in_does_not_cancel_feedback(
    fb_client: TestClient, sync_engine: Engine, fake_llm: FakeLlm
) -> None:
    fake_llm.stream_delay_s = 0.05
    fake_llm.analyze_delay_s = 0.2
    token = add_user(sync_engine)
    with fb_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        ws.send_json({"type": "user_text", "text": "Ja mam dwa kot w domu."})
        _until(ws, "ai_text_delta")
        ws.send_json({"type": "user_started_speaking"})
        events = _until(ws, "interrupted", "feedback")
    assert any(e["type"] == "feedback" for e in events)


def test_invalid_feedback_json_sends_nothing(
    fb_client: TestClient, sync_engine: Engine, fake_llm: FakeLlm
) -> None:
    fake_llm.analysis = "not json"
    token = add_user(sync_engine)
    with fb_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        ws.send_json({"type": "user_text", "text": "Ja mam dwa kot w domu."})
        _until(ws, "usage")
        ws.send_json({"type": "user_text", "text": "Cześć Kasia"})  # 2 words: no feedback
        events = _until(ws, "usage")
    assert not any(e["type"] == "feedback" for e in events)
    assert len(fake_llm.analyze_calls) == 1


def test_set_ui_lang_switches_explanations_and_messages(
    fb_client: TestClient, sync_engine: Engine, fake_llm: FakeLlm
) -> None:
    token = add_user(sync_engine, native="pl-PL")  # learns Portuguese
    with fb_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        ws.send_json({"type": "auth", "token": token})
        assert ws.receive_json()["user"]["ui_lang"] == "pl-PL"
        ws.receive_json()
        ws.send_json({"type": "set_ui_lang", "ui_lang": "pt-BR"})
        updated = _until(ws, "user_updated")[-1]
        assert updated["user"]["ui_lang"] == "pt-BR"
        assert updated["user"]["native_lang"] == "pl-PL"
        ws.send_json({"type": "user_text", "text": "Eu gosta muito de praia."})
        _until(ws, "feedback", "usage")
        ws.send_json({"nonsense": 1})
        error = _until(ws, "error")[-1]
    assert "MUST be written in Brazilian Portuguese" in str(fake_llm.analyze_calls[-1]["system"])
    assert error["message"] == "Mensagem inválida."  # server messages follow ui_lang too
    with Session(sync_engine) as db:
        assert db.scalars(select(User)).one().ui_lang == "pt-BR"


def test_correction_in_chat_is_on_by_default_and_can_be_turned_off(
    fb_client: TestClient, sync_engine: Engine, fake_llm: FakeLlm
) -> None:
    token = add_user(sync_engine)  # pt-BR learner of Polish, A1
    with fb_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        ws.send_json({"type": "auth", "token": token})
        assert ws.receive_json()["user"]["correct_in_chat"] is True
        ws.receive_json()
        ws.send_json({"type": "user_text", "text": "Ja mam dwa kot w domu."})
        _until(ws, "usage")
        system_on = str(fake_llm.stream_calls[-1]["system"])
        ws.send_json({"type": "set_correction", "enabled": False})
        assert _until(ws, "user_updated")[-1]["user"]["correct_in_chat"] is False
        ws.send_json({"type": "user_text", "text": "Ja mam dwa kot w domu."})
        _until(ws, "usage")
        system_off = str(fake_llm.stream_calls[-1]["system"])
    assert "correcting ONE mistake only" in system_on
    assert "saying why" in system_on  # A1 → one short reason in the UI language
    assert "Never explain grammar" in system_off
    with Session(sync_engine) as db:
        assert db.scalars(select(User)).one().correct_in_chat is False
