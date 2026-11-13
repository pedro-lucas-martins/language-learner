"""Slice 4 over the WebSocket: suggest_topic (zero LLM), theme, facts."""

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
from app.models import Message, UsageEvent, User
from app.services.llm import FakeLlm
from app.services.tts.chain import TtsChain
from tests.conftest import ORIGIN, add_user, make_settings, wait_sessions_closed
from tests.fakes_tts import FakeTts


@pytest.fixture
def topic_client(sync_engine: Engine, fake_llm: FakeLlm) -> Iterator[TestClient]:
    original = app.state.settings
    app.state.settings = make_settings()
    app.state.llm = fake_llm
    with TestClient(app) as client:
        yield client
        wait_sessions_closed(sync_engine)
    app.state.settings = original
    app.state.llm = None


def _login(ws: WebSocketTestSession, token: str) -> dict[str, Any]:
    ws.send_json({"type": "auth", "token": token})
    ready = ws.receive_json()
    ws.receive_json()
    return ready


def _until(ws: WebSocketTestSession, *types: str) -> list[dict[str, Any]]:
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


def _last_audio(ws: WebSocketTestSession) -> None:
    """Wait for the final audio chunk of a sentence."""
    while True:
        frame = ws.receive()
        if frame.get("text") and json.loads(frame["text"]).get("final"):
            ws.receive()  # its binary frame
            return


def test_suggest_topic_uses_no_llm_and_no_new_tts_when_cached(
    topic_client: TestClient, sync_engine: Engine, fake_llm: FakeLlm, fake_tts: TtsChain
) -> None:
    token = add_user(sync_engine, native="pl-PL", level="A2")  # learns Portuguese
    with topic_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        ws.send_json({"type": "suggest_topic"})
        first = _until(ws, "topic")[-1]
        _last_audio(ws)
        # Same topic again (forced) must come from the TTS cache.
        with Session(sync_engine) as db:
            tts_rows = db.scalars(select(UsageEvent).where(UsageEvent.kind == "tts_chars")).all()
        assert len(tts_rows) == 1
    assert fake_llm.stream_calls == [] and fake_llm.complete_calls == []
    with Session(sync_engine) as db:
        llm_rows = db.scalars(select(UsageEvent).where(UsageEvent.kind.like("llm%"))).all()
        stored = db.scalars(select(Message)).all()
    assert llm_rows == []
    assert [(m.role, m.text) for m in stored] == [("ai", first["text"])]

    # A second play of the same text: cached, 0 new characters.
    active = fake_tts.active
    assert isinstance(active, FakeTts)
    calls_before = len(active.calls)
    import asyncio

    async def replay() -> int:
        chunks = [c async for c in fake_tts.stream(first["text"], "pt-BR", None, record=_no_record)]
        return len(chunks)

    async def _no_record(provider: str, model: str, chars: int) -> None:
        raise AssertionError("a cached topic must not be billed")

    assert asyncio.run(replay()) == 1
    assert len(active.calls) == calls_before


def test_topics_are_not_repeated_in_a_session(
    topic_client: TestClient, sync_engine: Engine
) -> None:
    token = add_user(sync_engine, native="pl-PL", level="B1")
    texts = []
    with topic_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        for _ in range(5):
            ws.send_json({"type": "suggest_topic"})
            texts.append(_until(ws, "topic")[-1]["text"])
            _last_audio(ws)
    assert len(set(texts)) == 5


def test_suggest_topic_is_unavailable_for_learners_of_polish(
    topic_client: TestClient, sync_engine: Engine
) -> None:
    token = add_user(sync_engine, native="pt-BR")
    with topic_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        ws.send_json({"type": "suggest_topic"})
        assert _until(ws, "error")[-1]["code"] == "bad_request"


def test_answer_to_a_topic_sees_it_and_theme_reaches_the_prompt(
    topic_client: TestClient, sync_engine: Engine, fake_llm: FakeLlm
) -> None:
    token = add_user(sync_engine, native="pl-PL", level="A1")
    with topic_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        ws.send_json({"type": "set_theme", "theme": "viagens pela Europa"})
        ws.send_json({"type": "suggest_topic"})
        topic = _until(ws, "topic")[-1]["text"]
        _last_audio(ws)
        ws.send_json({"type": "user_text", "text": "Sim, eu gosto."})
        _until(ws, "usage")
        call = fake_llm.stream_calls[-1]
        ws.send_json({"type": "set_theme", "theme": ""})
        ws.send_json({"type": "user_text", "text": "Tudo bem."})
        _until(ws, "usage")
        cleared = fake_llm.stream_calls[-1]
    assert ("model", topic) in call["history"]
    assert call["history"][-1] == ("user", "Sim, eu gosto.")
    assert "«viagens pela Europa»" in str(call["system"])
    assert "Theme chosen by the learner" not in str(cleared["system"])
    assert all(m != ("model", topic) for m in cleared["history"][-2:])  # used once


def test_set_facts_truncates_and_saves(topic_client: TestClient, sync_engine: Engine) -> None:
    token = add_user(sync_engine, native="pl-PL")
    long_text = " ".join(f"fato{i}" for i in range(150))
    with topic_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        ws.send_json({"type": "set_facts", "text": long_text})
        updated = _until(ws, "user_updated")[-1]
    assert len(updated["user"]["user_facts"].split()) == 100
    with Session(sync_engine) as db:
        assert len(db.scalars(select(User)).one().user_facts.split()) == 100


def test_facts_are_updated_at_session_end(
    topic_client: TestClient, sync_engine: Engine, fake_llm: FakeLlm
) -> None:
    fake_llm.summary = "Ola; mora em Cracóvia; gosta de praia"
    token = add_user(sync_engine, native="pl-PL")
    with topic_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        ws.send_json({"type": "user_text", "text": "Eu moro em Cracóvia."})
        _until(ws, "usage")
    wait_sessions_closed(sync_engine)
    with Session(sync_engine) as db:
        assert db.scalars(select(User)).one().user_facts == "Ola; mora em Cracóvia; gosta de praia"
    facts_call = fake_llm.complete_calls[-1]
    assert "Brazilian Portuguese" not in str(facts_call["system"])  # ui_lang is Polish here
    assert "Polish" in str(facts_call["system"])


def test_failed_facts_update_keeps_the_old_ones(
    topic_client: TestClient, sync_engine: Engine, fake_llm: FakeLlm
) -> None:
    token = add_user(sync_engine, native="pl-PL")
    with Session(sync_engine) as db:
        user = db.scalars(select(User)).one()
        user.user_facts = "gosta de café"
        db.commit()
    fake_llm.fail_models = {"utility-model": "unavailable"}
    with topic_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
        ws.send_json({"type": "user_text", "text": "Hoje está frio."})
        _until(ws, "usage")
    wait_sessions_closed(sync_engine)
    with Session(sync_engine) as db:
        assert db.scalars(select(User)).one().user_facts == "gosta de café"


def test_no_facts_update_without_conversation(
    topic_client: TestClient, sync_engine: Engine, fake_llm: FakeLlm
) -> None:
    token = add_user(sync_engine, native="pl-PL")
    with topic_client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        _login(ws, token)
    wait_sessions_closed(sync_engine)
    assert fake_llm.complete_calls == []
