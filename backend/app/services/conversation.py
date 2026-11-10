"""One live conversation over a WebSocket (SPEC §4). Text-only in slice 1.

The orchestrator owns the in-memory window, persists messages, calls the LLM with
fallback, tracks usage and enforces caps. It never touches the WebSocket directly:
it emits protocol messages through `send`.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel

from app.config import Settings
from app.database import session_factory
from app.i18n import error_text, wire_code
from app.models import ChatSession, Message, User, utcnow
from app.protocol import (
    AiTextDeltaMsg,
    AiTextDoneMsg,
    ErrorMsg,
    TranscriptMsg,
    UsageMsg,
    UserInfo,
    UserUpdatedMsg,
)
from app.services import usage as usage_svc
from app.services.llm import (
    LlmError,
    LlmProvider,
    LlmUsage,
    StreamEnd,
    TextDelta,
    chat_model_chain,
    stream_with_fallback,
)
from app.services.memory import ConversationMemory
from app.services.prompts import (
    SUMMARY_SYSTEM_PROMPT,
    chat_system_prompt,
    summary_user_prompt,
    truncate_words,
)

log = logging.getLogger(__name__)

Send = Callable[[BaseModel], Awaitable[None]]

CHAT_MAX_OUTPUT_TOKENS = 400  # the prompt keeps replies short; this only guards runaway output
CHAT_TEMPERATURE = 0.8
SUMMARY_MAX_WORDS = 40


@dataclass
class Learner:
    """Plain copy of the user row, safe to keep across DB sessions."""

    id: uuid.UUID
    name: str
    native_lang: str
    target_lang: str
    level: str
    user_facts: str
    recast_pronunciation: bool

    @classmethod
    def from_model(cls, user: User) -> "Learner":
        return cls(
            id=user.id,
            name=user.name,
            native_lang=user.native_lang,
            target_lang=user.target_lang,
            level=user.level,
            user_facts=user.user_facts,
            recast_pronunciation=user.recast_pronunciation,
        )

    def info(self) -> UserInfo:
        return UserInfo(
            name=self.name,
            native_lang=self.native_lang,  # type: ignore[arg-type]
            target_lang=self.target_lang,  # type: ignore[arg-type]
            level=self.level,  # type: ignore[arg-type]
            recast_pronunciation=self.recast_pronunciation,
        )


class Conversation:
    def __init__(
        self,
        *,
        learner: Learner,
        session_id: uuid.UUID,
        settings: Settings,
        llm: LlmProvider,
        send: Send,
    ) -> None:
        self.learner = learner
        self.session_id = session_id
        self.settings = settings
        self.llm = llm
        self.send = send
        self.memory = ConversationMemory(
            window_turns=settings.window_turns, summary_batch_turns=settings.summary_batch_turns
        )
        self._background: set[asyncio.Task[None]] = set()

    # --- lifecycle --------------------------------------------------------------

    @classmethod
    async def start(
        cls, *, user: User, settings: Settings, llm: LlmProvider, send: Send
    ) -> "Conversation":
        async with session_factory()() as db:
            chat = ChatSession(user_id=user.id, running_summary="")
            db.add(chat)
            await db.commit()
            session_id = chat.id
        return cls(
            learner=Learner.from_model(user),
            session_id=session_id,
            settings=settings,
            llm=llm,
            send=send,
        )

    async def close(self) -> None:
        if self._background:
            await asyncio.wait(self._background, timeout=10)
        async with session_factory()() as db:
            chat = await db.get(ChatSession, self.session_id)
            if chat is not None:
                chat.ended_at = utcnow()
                chat.running_summary = self.memory.summary
                await db.commit()

    # --- helpers ------------------------------------------------------------------

    async def _error(self, key: str) -> None:
        await self.send(
            ErrorMsg(code=wire_code(key), message=error_text(self.learner.native_lang, key))
        )

    async def _send_usage(self) -> usage_svc.UsageSnapshot:
        async with session_factory()() as db:
            snap = await usage_svc.snapshot(db, self.settings, self.learner.id)
        await self.send(
            UsageMsg(
                month_usd_est=snap.month_usd_est,
                budget_usd=snap.budget_usd,
                tts_chars_month=snap.tts_chars_month,
                tts_chars_allowance=snap.tts_chars_allowance,
                tts_provider_active=snap.tts_provider_active,
            )
        )
        return snap

    async def send_initial_usage(self) -> None:
        await self._send_usage()

    # --- commands -------------------------------------------------------------------

    async def set_level(self, level: str) -> None:
        async with session_factory()() as db:
            user = await db.get(User, self.learner.id)
            if user is None:
                await self._error("bad_request")
                return
            user.level = level
            await db.commit()
        self.learner.level = level
        await self.send(UserUpdatedMsg(user=self.learner.info()))

    async def handle_user_text(self, text: str) -> None:
        text = text.strip()
        if not text:
            await self._error("bad_request")
            return

        async with session_factory()() as db:
            snap = await usage_svc.snapshot(db, self.settings, self.learner.id)
        if snap.daily_cap_reached:
            await self._error("quota_exceeded")
            return

        user_msg_id = await self._persist(role="user", text=text)
        await self.send(TranscriptMsg(message_id=str(user_msg_id), text=text))

        ai_msg_id = uuid.uuid4()
        reply = await self._stream_reply(text, ai_msg_id, budget_exceeded=snap.budget_exceeded)
        if reply is None:
            return

        await self._persist(role="ai", text=reply, message_id=ai_msg_id)
        await self.send(AiTextDoneMsg(message_id=str(ai_msg_id), text=reply))
        self.memory.add_turn(text, reply)
        self._maybe_summarize()
        await self._send_usage()

    async def _stream_reply(
        self, text: str, ai_msg_id: uuid.UUID, *, budget_exceeded: bool
    ) -> str | None:
        system = chat_system_prompt(
            target_lang=self.learner.target_lang,
            native_lang=self.learner.native_lang,
            level=self.learner.level,
            user_facts=self.learner.user_facts,
            summary=self.memory.summary,
        )
        history: list[tuple[str, str]] = []
        for turn in self.memory.context_turns():
            history += [("user", turn.user), ("model", turn.ai)]
        history.append(("user", text))

        chain = chat_model_chain(self.settings, budget_exceeded=budget_exceeded)
        parts: list[str] = []
        try:
            async for choice, event in stream_with_fallback(
                self.llm,
                chain,
                system=system,
                history=history,  # type: ignore[arg-type]
                max_output_tokens=CHAT_MAX_OUTPUT_TOKENS,
                temperature=CHAT_TEMPERATURE,
            ):
                if isinstance(event, TextDelta):
                    parts.append(event.text)
                    await self.send(AiTextDeltaMsg(message_id=str(ai_msg_id), delta=event.text))
                elif isinstance(event, StreamEnd):
                    await self._record_llm(choice.role, choice.model, event.usage)
        except LlmError as exc:
            log.warning("Chat reply failed: %s", exc)
            if parts:
                await self._error("interrupted")
            else:
                await self._error(
                    "not_configured" if exc.code == "not_configured" else "provider_unavailable"
                )
            return None
        reply = "".join(parts).strip()
        if not reply:
            await self._error("provider_unavailable")
            return None
        return reply

    # --- persistence & usage ----------------------------------------------------------

    async def _persist(
        self, *, role: str, text: str, message_id: uuid.UUID | None = None
    ) -> uuid.UUID:
        async with session_factory()() as db:
            msg = Message(
                id=message_id or uuid.uuid4(), session_id=self.session_id, role=role, text=text
            )
            db.add(msg)
            await db.commit()
            return msg.id

    async def _record_llm(self, role: str, model: str, usage: LlmUsage) -> None:
        async with session_factory()() as db:
            await usage_svc.record_llm(
                db, user_id=self.learner.id, role=role, model=model, usage=usage
            )

    # --- running summary (SPEC §4.2) ---------------------------------------------------

    def _maybe_summarize(self) -> None:
        if not self.memory.needs_summary() or not self.settings.gemini_utility_model:
            return
        previous, turns = self.memory.begin_summary()
        task = asyncio.create_task(self._summarize(previous, turns))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _summarize(self, previous: str, turns: list) -> None:  # type: ignore[type-arg]
        model = self.settings.gemini_utility_model
        try:
            summary, used = await self.llm.complete(
                model=model,
                system=SUMMARY_SYSTEM_PROMPT,
                prompt=summary_user_prompt(previous, turns),
                max_output_tokens=200,
                temperature=0.2,
            )
        except LlmError as exc:
            log.warning("Summary failed, turns stay pending: %s", exc)
            self.memory.abort_summary()
            return
        await self._record_llm("utility", model, used)
        if not summary.strip():
            self.memory.abort_summary()
            return
        self.memory.apply_summary(truncate_words(summary, SUMMARY_MAX_WORDS))
        async with session_factory()() as db:
            chat = await db.get(ChatSession, self.session_id)
            if chat is not None:
                chat.running_summary = self.memory.summary
                await db.commit()
