"""🌐 translate: one AI message into the interface language (utility model, cached)."""

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
from app.services.llm import FakeLlm
from tests.conftest import ORIGIN, add_user, make_settings, wait_sessions_closed

TRANSLATED = "Cześć! Lubisz kawę?"


@pytest.fixture
def translate_llm() -> FakeLlm:
    return FakeLlm(summary=TRANSLATED)


def _client(sync_engine: Engine, llm: FakeLlm, **overrides: object) -> Iterator[TestClient]:
    original = app.state.settings
    app.state.settings = make_settings(**overrides)
    app.state.llm = llm
    with TestClient(app) as client:
        yield client
        wait_sessions_closed(sync_engine)
    app.state.settings = original
    app.state.llm = None


@pytest.fixture
def tr_client(sync_engine: Engine, translate_llm: FakeLlm) -> Iterator[TestClient]:
    yield from _client(sync_engine, translate_llm)


@pytest.fixture
def capped_client(sync_engine: Engine, translate_llm: FakeLlm) -> Iterator[TestClient]:
    yield from _client(sync_engine, translate_llm, daily_llm_calls_per_user=1)


def _login(ws: WebSocketTestSession, token: str) -> None:
    ws.send_json({"type": "auth", "token": token})
    assert ws.receive_json()["type"] == "ready"
    ws.receive_json()  # usage


def _until(ws: WebSocketTestSession, *types: str) -> dict[str, Any]:
    """Return the first event of one of `types`, skipping audio and everything else."""
    while True:
        frame = ws.receive()
        if frame.get("bytes") is not None:
            continue
        event = json.loads(frame["text"])
        if event["type"] in types:
            return event


def _ai_reply(ws: WebSocketTestSession) -> str:
    ws.send_json({"type": "user_text", "text": "Oi, tudo bem?"})
    return _until(ws, "ai_text_done")["message_id"]


def _translate_calls(llm: FakeLlm) -> list[dict[str, object]]:
    return [c for c in llm.complete_calls if str(c["system"]).startswith("Translate")]


def test_translates_ai_message_into_ui_lang_and_caches_it(
    tr_client: TestClient, sync_engine: Engine, translate_llm: FakeLlm
) -> None:
    token = add_user(sync_engine, native="pl-PL", level="A2")  # learns Portuguese, UI in Polish
    with tr_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        ai_id = _ai_reply(ws)
        ws.send_json({"type": "translate", "message_id": ai_id})
        first = _until(ws, "translation", "error")
        ws.send_json({"type": "translate", "message_id": ai_id})
        second = _until(ws, "translation", "error")
    expected = {"type": "translation", "message_id": ai_id, "text": TRANSLATED, "lang": "pl-PL"}
    assert first == expected
    assert second == first
    calls = _translate_calls(translate_llm)
    assert len(calls) == 1  # the second one came from the session cache
    assert calls[0]["model"] == "utility-model"
    assert "from Brazilian Portuguese into natural, everyday Polish" in str(calls[0]["system"])
    with Session(sync_engine) as db:
        reply = db.get(Message, uuid.UUID(ai_id))
        utility = db.scalars(
            select(UsageEvent).where(UsageEvent.role == "utility", UsageEvent.kind.like("llm%"))
        ).all()
    assert reply is not None and calls[0]["prompt"] == reply.text
    assert utility  # the translation is counted in usage and spend


@pytest.mark.parametrize("which", ["user", "unknown", "not-a-uuid"])
def test_only_ai_messages_of_this_session(
    tr_client: TestClient, sync_engine: Engine, translate_llm: FakeLlm, which: str
) -> None:
    token = add_user(sync_engine, native="pl-PL")
    with tr_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        _ai_reply(ws)
        if which == "user":
            with Session(sync_engine) as db:
                target = str(db.scalars(select(Message.id).where(Message.role == "user")).first())
        elif which == "unknown":
            target = str(uuid.uuid4())
        else:
            target = "not-a-uuid"
        ws.send_json({"type": "translate", "message_id": target})
        event = _until(ws, "translation", "error")
    assert event["type"] == "error" and event["code"] == "bad_request"
    assert _translate_calls(translate_llm) == []


def test_previous_session_message_after_reconnect(
    tr_client: TestClient, sync_engine: Engine, translate_llm: FakeLlm
) -> None:
    token = add_user(sync_engine, native="pl-PL")
    with tr_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        ai_id = _ai_reply(ws)
    with tr_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        ws.send_json({"type": "translate", "message_id": ai_id})
        event = _until(ws, "translation", "error")
    assert event["type"] == "translation" and event["text"] == TRANSLATED


def test_another_learners_message_is_refused(
    tr_client: TestClient, sync_engine: Engine, translate_llm: FakeLlm
) -> None:
    owner = add_user(sync_engine, native="pl-PL", name="Ola")
    other = add_user(sync_engine, native="pl-PL", name="Kasia")
    with tr_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, owner)
        ai_id = _ai_reply(ws)
    with tr_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, other)
        ws.send_json({"type": "translate", "message_id": ai_id})
        event = _until(ws, "translation", "error")
    assert event["code"] == "bad_request"
    assert _translate_calls(translate_llm) == []


def test_daily_cap_blocks_translation(
    capped_client: TestClient, sync_engine: Engine, translate_llm: FakeLlm
) -> None:
    token = add_user(sync_engine, native="pl-PL")
    with capped_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        ai_id = _ai_reply(ws)  # the reply itself uses the only call of the day
        ws.send_json({"type": "translate", "message_id": ai_id})
        event = _until(ws, "translation", "error")
    assert event["code"] == "quota_exceeded"
    assert _translate_calls(translate_llm) == []
