"""End-to-end WebSocket tests with SQLite and FakeLlm."""

import time
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.models import ChatSession, Message, User
from app.services import llm as llm_mod
from app.services.llm import FakeLlm
from tests.conftest import ORIGIN, add_user, make_settings


def _session_ended(engine: Engine) -> bool:
    with Session(engine) as db:
        return db.scalars(select(ChatSession)).one().ended_at is not None


def _wait_until(check: Callable[[], bool], timeout: float = 3.0) -> bool:
    """The server finishes closing the session after the client disconnects."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.02)
    return check()


def _connect(client: TestClient, origin: str = ORIGIN):  # type: ignore[no-untyped-def]
    return client.websocket_connect("/ws", headers={"origin": origin})


def _login(ws: WebSocketTestSession, token: str) -> dict[str, Any]:
    ws.send_json({"type": "auth", "token": token})
    ready = ws.receive_json()
    assert ready["type"] == "ready"
    usage = ws.receive_json()
    assert usage["type"] == "usage"
    return ready


def _say(ws: WebSocketTestSession, text: str) -> list[dict[str, Any]]:
    """Send a message and collect events until the turn ends (usage or error)."""
    ws.send_json({"type": "user_text", "text": text})
    events = []
    while True:
        event = ws.receive_json()
        events.append(event)
        if event["type"] in ("usage", "error"):
            return events


def test_rejects_foreign_origin(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as info:
        with _connect(client, origin="https://evil.example.com") as ws:
            ws.receive_json()
    assert info.value.code == 4403


def test_rejects_missing_origin(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()


@pytest.mark.parametrize(
    "first_message",
    [{"type": "auth", "token": "wrong"}, {"type": "user_text", "text": "hi"}, {"nonsense": 1}],
)
def test_bad_auth_closes_with_4401(client: TestClient, first_message: dict[str, Any]) -> None:
    with _connect(client) as ws:
        ws.send_json(first_message)
        with pytest.raises(WebSocketDisconnect) as info:
            ws.receive_json()
    assert info.value.code == 4401


def test_ready_contains_user_info(client: TestClient, sync_engine: Engine) -> None:
    token = add_user(sync_engine, native="pl-PL", level="B2", name="Ola")
    with _connect(client) as ws:
        ready = _login(ws, token)
    assert ready["user"] == {
        "name": "Ola",
        "native_lang": "pl-PL",
        "target_lang": "pt-BR",
        "level": "B2",
        "recast_pronunciation": True,
    }


def test_text_turn_streams_and_persists(
    client: TestClient, sync_engine: Engine, fake_llm: FakeLlm
) -> None:
    token = add_user(sync_engine)
    fake_llm.reply = "Cześć! Co dziś robisz?"
    with _connect(client) as ws:
        _login(ws, token)
        events = _say(ws, "  Cześć Kasia  ")

    types = [e["type"] for e in events]
    assert types[0] == "transcript" and events[0]["text"] == "Cześć Kasia"
    assert types[-2:] == ["ai_text_done", "usage"]
    deltas = [e["delta"] for e in events if e["type"] == "ai_text_delta"]
    assert "".join(deltas) == "Cześć! Co dziś robisz?"
    done = events[-2]
    assert {e["message_id"] for e in events if e["type"] == "ai_text_delta"} == {done["message_id"]}

    # Uses the chat model with a Polish system prompt and the user's text last.
    call = fake_llm.stream_calls[-1]
    assert call["model"] == "chat-model"
    assert "Reply ONLY in Polish." in str(call["system"])
    assert call["history"] == [("user", "Cześć Kasia")]

    with Session(sync_engine) as db:
        messages = db.scalars(select(Message).order_by(Message.created_at)).all()
        assert [(m.role, m.text) for m in messages] == [
            ("user", "Cześć Kasia"),
            ("ai", "Cześć! Co dziś robisz?"),
        ]
    assert _wait_until(lambda: _session_ended(sync_engine)), "session not closed on disconnect"


def test_history_and_summary_reach_the_llm(
    client: TestClient, sync_engine: Engine, fake_llm: FakeLlm
) -> None:
    token = add_user(sync_engine)
    fake_llm.summary = "They talked about pierogi."
    with _connect(client) as ws:
        _login(ws, token)
        for i in range(8):
            _say(ws, f"msg {i}")

    # 3-turn window + 3-turn batch: the first batch (msg 0..2) is summarized
    # once 6 turns exist; later calls carry the summary instead of those turns.
    assert fake_llm.complete_calls, "summary was never requested"
    assert "Learner: msg 0" in str(fake_llm.complete_calls[0]["prompt"])
    last = fake_llm.stream_calls[-1]
    assert "They talked about pierogi." in str(last["system"])
    sent_user_texts = [text for role, text in last["history"] if role == "user"]  # type: ignore[union-attr]
    assert "msg 0" not in sent_user_texts
    assert sent_user_texts[-1] == "msg 7"

    def summary_saved() -> bool:
        with Session(sync_engine) as db:
            summary = db.scalars(select(ChatSession)).one().running_summary
            return summary == "They talked about pierogi."

    assert _wait_until(summary_saved)


def test_set_level_updates_db_and_prompt(
    client: TestClient, sync_engine: Engine, fake_llm: FakeLlm
) -> None:
    token = add_user(sync_engine, level="A1")
    with _connect(client) as ws:
        _login(ws, token)
        ws.send_json({"type": "set_level", "level": "C1"})
        updated = ws.receive_json()
        assert updated["type"] == "user_updated" and updated["user"]["level"] == "C1"
        _say(ws, "Hej")
    assert "Level C1" in str(fake_llm.stream_calls[-1]["system"])
    with Session(sync_engine) as db:
        assert db.scalars(select(User)).one().level == "C1"


def test_invalid_message_returns_localized_error(client: TestClient, sync_engine: Engine) -> None:
    token = add_user(sync_engine, native="pl-PL")
    with _connect(client) as ws:
        _login(ws, token)
        ws.send_json({"type": "set_level", "level": "Z9"})
        error = ws.receive_json()
        assert error == {
            "type": "error",
            "code": "bad_request",
            "message": "Nieprawidłowa wiadomość.",
        }
        # The connection stays usable.
        events = _say(ws, "Olá")
        assert events[0]["type"] == "transcript"


def test_daily_cap_blocks_llm_calls(sync_engine: Engine, fake_llm: FakeLlm) -> None:
    original = app.state.settings
    app.state.settings = make_settings(daily_llm_calls_per_user=1)
    app.state.llm = fake_llm
    token = add_user(sync_engine)
    try:
        with TestClient(app) as client, _connect(client) as ws:
            _login(ws, token)
            first = _say(ws, "jeden")
            second = _say(ws, "dwa")
    finally:
        app.state.llm = None
        app.state.settings = original
    assert first[-1]["type"] == "usage"
    assert second == [
        {
            "type": "error",
            "code": "quota_exceeded",
            "message": "Você atingiu o limite de uso de hoje. Volte amanhã!",
        }
    ]
    assert len(fake_llm.stream_calls) == 1


def test_provider_down_returns_error_and_keeps_socket(
    client: TestClient, sync_engine: Engine, fake_llm: FakeLlm, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(llm_mod, "RETRY_DELAY_S", 0)
    fake_llm.fail_models = {"chat-model": "unavailable", "utility-model": "unavailable"}
    token = add_user(sync_engine)
    with _connect(client) as ws:
        _login(ws, token)
        events = _say(ws, "Hej")
        assert events[0]["type"] == "transcript"
        assert events[-1]["type"] == "error" and events[-1]["code"] == "provider_unavailable"
        fake_llm.fail_models = {}
        events = _say(ws, "Hej znowu")
        assert events[-1]["type"] == "usage"


def test_missing_models_report_not_configured(sync_engine: Engine, fake_llm: FakeLlm) -> None:
    original = app.state.settings
    app.state.settings = make_settings(gemini_chat_model="", gemini_utility_model="")
    app.state.llm = fake_llm
    token = add_user(sync_engine)
    try:
        with TestClient(app) as client, _connect(client) as ws:
            _login(ws, token)
            events = _say(ws, "Oi")
    finally:
        app.state.llm = None
        app.state.settings = original
    assert events[-1]["code"] == "provider_unavailable"
    assert "não foi configurada" in events[-1]["message"]
