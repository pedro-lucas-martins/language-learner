"""Real-time conversation WebSocket (SPEC §3, §7)."""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError

from app.database import session_factory
from app.i18n import error_text
from app.protocol import AuthMsg, ErrorMsg, ReadyMsg, SetLevelMsg, UserTextMsg, client_msg_adapter
from app.security import is_allowed_origin
from app.services.auth import authenticate
from app.services.conversation import Conversation

log = logging.getLogger(__name__)
router = APIRouter()

AUTH_TIMEOUT_S = 5.0
CLOSE_UNAUTHORIZED = 4401
CLOSE_FORBIDDEN_ORIGIN = 4403


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

    async def send(msg: BaseModel) -> None:
        await websocket.send_text(msg.model_dump_json())

    conversation = await Conversation.start(
        user=user, settings=settings, llm=websocket.app.state.llm, send=send
    )
    try:
        await send(
            ReadyMsg(user=conversation.learner.info(), session_id=str(conversation.session_id))
        )
        await conversation.send_initial_usage()
        while True:
            raw = await websocket.receive_text()
            try:
                msg = client_msg_adapter.validate_python(json.loads(raw))
            except (ValidationError, ValueError):
                await send(
                    ErrorMsg(
                        code="bad_request",
                        message=error_text(conversation.learner.native_lang, "bad_request"),
                    )
                )
                continue
            if isinstance(msg, UserTextMsg):
                await conversation.handle_user_text(msg.text)
            elif isinstance(msg, SetLevelMsg):
                await conversation.set_level(msg.level)
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
