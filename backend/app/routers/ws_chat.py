"""Real-time conversation WebSocket (SPEC §3, §7)."""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError

from app.database import session_factory
from app.i18n import error_text
from app.protocol import (
    AudioMetaMsg,
    AuthMsg,
    EndOfSpeechMsg,
    ErrorMsg,
    ReadyMsg,
    RegradeMsg,
    SetCorrectionMsg,
    SetLevelMsg,
    SetRecastMsg,
    SetUiLangMsg,
    SpeakWordMsg,
    StartOfSpeechMsg,
    UserStartedSpeakingMsg,
    UserTextMsg,
    client_msg_adapter,
)
from app.security import is_allowed_origin
from app.services import warmup
from app.services.auth import authenticate
from app.services.conversation import Conversation

log = logging.getLogger(__name__)
router = APIRouter()

AUTH_TIMEOUT_S = 5.0
CLOSE_UNAUTHORIZED = 4401
CLOSE_FORBIDDEN_ORIGIN = 4403
# One utterance as a single binary message (SPEC §6). ~2 min of Opus at 32 kbps is ~0.5 MB.
MAX_UTTERANCE_BYTES = 2 * 1024 * 1024


class _Utterance:
    """Audio announced by start_of_speech, received as binary, closed by end_of_speech."""

    def __init__(self, start: StartOfSpeechMsg) -> None:
        self.mime = start.mime
        self.purpose = start.purpose
        self.target_word = start.target_word or ""
        self.message_id = start.message_id or ""
        self.parts: list[bytes] = []
        self.size = 0


@router.websocket("/ws")
async def chat_socket(websocket: WebSocket) -> None:
    settings = websocket.app.state.settings

    # CORS middleware does not cover WebSockets: check Origin by hand (SPEC §3).
    if not is_allowed_origin(websocket.headers.get("origin"), settings):
        await websocket.close(code=CLOSE_FORBIDDEN_ORIGIN)
        return
    await websocket.accept()

    # The first message must be a valid auth within the timeout.
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), AUTH_TIMEOUT_S)
        auth = AuthMsg.model_validate_json(raw)
    except (TimeoutError, ValidationError, WebSocketDisconnect):
        await _safe_close(websocket, CLOSE_UNAUTHORIZED)
        return
    async with session_factory()() as db:
        user = await authenticate(db, auth.token)
    if user is None:
        await _safe_close(websocket, CLOSE_UNAUTHORIZED)
        return

    # Turns run in their own task; the lock keeps each audio_meta next to its binary frame.
    send_lock = asyncio.Lock()

    # Open provider connections now, so the first spoken turn is not the slow one.
    tts = getattr(websocket.app.state, "tts", None)
    warmup.schedule(
        [websocket.app.state.llm, getattr(tts, "active", None), getattr(tts, "backup", None)]
    )

    closed = False

    async def send(msg: BaseModel) -> None:
        nonlocal closed
        if closed:
            return  # e.g. feedback that finished after the learner left
        async with send_lock:
            try:
                await websocket.send_text(msg.model_dump_json())
            except Exception:  # noqa: BLE001 — client gone (uvicorn/starlette raise various types)
                closed = True

    async def send_audio(meta: AudioMetaMsg, data: bytes) -> None:
        nonlocal closed
        if closed:
            return
        async with send_lock:
            try:
                await websocket.send_text(meta.model_dump_json())
                await websocket.send_bytes(data)
            except Exception:  # noqa: BLE001 — client gone (uvicorn/starlette raise various types)
                closed = True

    conversation = await Conversation.start(
        user=user,
        settings=settings,
        llm=websocket.app.state.llm,
        send=send,
        tts=getattr(websocket.app.state, "tts", None),
        send_audio=send_audio,
    )

    async def bad_request() -> None:
        await send(
            ErrorMsg(
                code="bad_request",
                message=error_text(conversation.learner.ui_lang, "bad_request"),
            )
        )

    utterance: _Utterance | None = None
    try:
        await send(
            ReadyMsg(user=conversation.learner.info(), session_id=str(conversation.session_id))
        )
        await conversation.send_initial_usage()
        while True:
            frame = await websocket.receive()
            if frame["type"] == "websocket.disconnect":
                raise WebSocketDisconnect(frame.get("code", 1000))
            data = frame.get("bytes")
            if data is not None:
                if utterance is None:
                    await bad_request()  # audio without start_of_speech
                    continue
                utterance.size += len(data)
                if utterance.size > MAX_UTTERANCE_BYTES:
                    utterance = None
                    await bad_request()
                    continue
                utterance.parts.append(data)
                continue
            try:
                msg = client_msg_adapter.validate_python(json.loads(frame.get("text") or ""))
            except (ValidationError, ValueError):
                await bad_request()
                continue
            if isinstance(msg, UserTextMsg):
                await conversation.submit_text(msg.text)
            elif isinstance(msg, SetLevelMsg):
                await conversation.set_level(msg.level)
            elif isinstance(msg, SetCorrectionMsg):
                await conversation.set_correction(msg.enabled)
            elif isinstance(msg, SetUiLangMsg):
                await conversation.set_ui_lang(msg.ui_lang)
            elif isinstance(msg, SetRecastMsg):
                await conversation.set_recast(msg.enabled)
            elif isinstance(msg, RegradeMsg):
                await conversation.regrade(msg.message_id, msg.text)
            elif isinstance(msg, StartOfSpeechMsg):
                if msg.purpose == "pron_retry" and not (msg.target_word or "").strip():
                    await bad_request()
                    continue
                utterance = _Utterance(msg)
            elif isinstance(msg, EndOfSpeechMsg):
                if utterance is None or not utterance.parts:
                    utterance = None
                    await bad_request()
                    continue
                done, utterance = utterance, None
                audio = b"".join(done.parts)
                if done.purpose == "pron_retry":
                    conversation.pron_retry(audio, done.mime, done.target_word, done.message_id)
                else:
                    await conversation.submit_utterance(audio, done.mime)
            elif isinstance(msg, SpeakWordMsg):
                conversation.speak_word(msg.word)
            elif isinstance(msg, UserStartedSpeakingMsg):
                await conversation.interrupt()
            # A second `auth` after login is ignored.
    except WebSocketDisconnect:
        pass
    finally:
        # Shielded: if the handler is cancelled (server shutdown, test client teardown),
        # the session is still closed and its summary saved.
        await asyncio.shield(conversation.close())


async def _safe_close(websocket: WebSocket, code: int) -> None:
    try:
        await websocket.close(code=code)
    except RuntimeError:
        pass  # already closed by the client
