"""One live conversation over a WebSocket (SPEC §4, §6).

The orchestrator owns the in-memory window, persists messages, calls the LLM with
fallback, turns the reply into speech sentence by sentence, tracks usage and enforces
caps. It never touches the WebSocket directly: it emits protocol messages through
`send` and audio through `send_audio`.

Each turn runs as its own task so the socket keeps reading: a new utterance, a typed
message or `user_started_speaking` cancels the running turn (barge-in).
"""

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.config import Settings
from app.database import session_factory
from app.i18n import error_text, wire_code
from app.models import ChatSession, Message, User, utcnow
from app.protocol import (
    AiTextDeltaMsg,
    AiTextDoneMsg,
    AudioMetaMsg,
    ErrorMsg,
    FeedbackMsg,
    InterruptedMsg,
    MetricsMsg,
    PronResultMsg,
    TranscriptMsg,
    TtsFallbackMsg,
    UsageMsg,
    UserInfo,
    UserUpdatedMsg,
)
from app.services import feedback as feedback_svc
from app.services import flashcards as flashcards_svc
from app.services import usage as usage_svc
from app.services.llm import (
    AudioInput,
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
from app.services.sentence_buffer import SentenceBuffer
from app.services.stt_service import (
    AUDIO_TOKENS_PER_SECOND,
    SttError,
    estimate_seconds,
    gemini_mime,
    transcribe,
)
from app.services.tts.chain import TtsChain, TtsChunk, TtsUnavailable

log = logging.getLogger(__name__)

Send = Callable[[BaseModel], Awaitable[None]]
SendAudio = Callable[[AudioMetaMsg, bytes], Awaitable[None]]

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
    voice_id: str | None = None
    ui_lang: str = ""

    def __post_init__(self) -> None:
        self.ui_lang = self.ui_lang or self.native_lang

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
            voice_id=user.voice_id,
            ui_lang=user.ui_lang or user.native_lang,
        )

    def info(self) -> UserInfo:
        return UserInfo(
            name=self.name,
            native_lang=self.native_lang,  # type: ignore[arg-type]
            target_lang=self.target_lang,  # type: ignore[arg-type]
            ui_lang=self.ui_lang,  # type: ignore[arg-type]
            level=self.level,  # type: ignore[arg-type]
            recast_pronunciation=self.recast_pronunciation,
        )


def _ms(since: float) -> int:
    return round((time.perf_counter() - since) * 1000)


@dataclass
class Timings:
    """Per-turn latency, measured from end_of_speech / user_text (SPEC §6)."""

    started: float
    stt_ms: int | None = None
    llm_first_token_ms: int | None = None
    first_audio_ms: int | None = None


async def _no_audio(meta: AudioMetaMsg, data: bytes) -> None:
    """Used when no audio sink is given (e.g. scripts)."""


class Conversation:
    def __init__(
        self,
        *,
        learner: Learner,
        session_id: uuid.UUID,
        settings: Settings,
        llm: LlmProvider,
        send: Send,
        tts: TtsChain | None = None,
        send_audio: SendAudio = _no_audio,
    ) -> None:
        self.learner = learner
        self.session_id = session_id
        self.settings = settings
        self.llm = llm
        self.send = send
        self.tts = tts
        self.send_audio = send_audio
        self.memory = ConversationMemory(
            window_turns=settings.window_turns, summary_batch_turns=settings.summary_batch_turns
        )
        self._background: set[asyncio.Task[None]] = set()
        self._turn: asyncio.Task[None] | None = None
        self._turn_ai_id: uuid.UUID | None = None

    # --- lifecycle --------------------------------------------------------------

    @classmethod
    async def start(
        cls,
        *,
        user: User,
        settings: Settings,
        llm: LlmProvider,
        send: Send,
        tts: TtsChain | None = None,
        send_audio: SendAudio = _no_audio,
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
            tts=tts,
            send_audio=send_audio,
        )

    async def close(self) -> None:
        await self._cancel_turn()
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
            ErrorMsg(code=wire_code(key), message=error_text(self.learner.ui_lang, key))
        )

    async def _snapshot(self) -> usage_svc.UsageSnapshot:
        async with session_factory()() as db:
            return await usage_svc.snapshot(db, self.settings, self.learner.id)

    def _tts_provider_active(self, snap: usage_svc.UsageSnapshot) -> str:
        if self.tts is None:
            return "browser"
        if self.tts.active is None or snap.tts_over_allowance:
            return self.tts.fallback.name
        return self.tts.active.name

    async def _send_usage(self) -> usage_svc.UsageSnapshot:
        snap = await self._snapshot()
        await self.send(
            UsageMsg(
                month_usd_est=snap.month_usd_est,
                budget_usd=snap.budget_usd,
                tts_chars_month=snap.tts_chars_month,
                tts_chars_allowance=snap.tts_chars_allowance,
                tts_provider_active=self._tts_provider_active(snap),
            )
        )
        return snap

    async def send_initial_usage(self) -> None:
        await self._send_usage()

    # --- commands -------------------------------------------------------------------

    async def set_ui_lang(self, ui_lang: str) -> None:
        """Interface + explanation language (SPEC §1)."""
        async with session_factory()() as db:
            user = await db.get(User, self.learner.id)
            if user is not None:
                user.ui_lang = None if ui_lang == user.native_lang else ui_lang
            await db.commit()
        if user is None:
            await self._error("bad_request")
            return
        self.learner.ui_lang = ui_lang
        await self.send(UserUpdatedMsg(user=self.learner.info()))

    async def set_recast(self, enabled: bool) -> None:
        """Pronunciation recast in Track 1 on/off (SPEC §4.1)."""
        async with session_factory()() as db:
            user = await db.get(User, self.learner.id)
            if user is None:
                await self._error("bad_request")
                return
            user.recast_pronunciation = enabled
            await db.commit()
        self.learner.recast_pronunciation = enabled
        await self.send(UserUpdatedMsg(user=self.learner.info()))

    async def regrade(self, message_id: str, text: str) -> None:
        """The learner fixed the transcript of one of their messages: re-run grammar only."""
        text = text.strip()
        try:
            msg_uuid = uuid.UUID(message_id)
        except ValueError:
            await self._error("bad_request")
            return
        async with session_factory()() as db:
            msg = await db.get(Message, msg_uuid)
            allowed = (
                msg is not None
                and msg.session_id == self.session_id
                and msg.role == "user"
                and bool(text)
            )
            if allowed:
                assert msg is not None
                msg.text = text
            await db.commit()  # also ends the read transaction when nothing changed
        if not allowed:
            await self._error("bad_request")
            return
        snap = await self._snapshot()
        if snap.daily_cap_reached:
            await self._error("quota_exceeded")
            return
        self._spawn_feedback(msg_uuid, text, None, budget_exceeded=snap.budget_exceeded)

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

    # --- turns (each one is a cancellable task) -----------------------------------------

    async def submit_text(self, text: str) -> None:
        await self.interrupt()
        self._launch(self._text_turn(text, Timings(time.perf_counter())))

    async def submit_utterance(self, audio: bytes, mime: str) -> None:
        await self.interrupt()
        self._launch(self._voice_turn(audio, mime, Timings(time.perf_counter())))

    async def interrupt(self) -> None:
        """Barge-in: stop the running turn (LLM and TTS) and tell the client."""
        ai_id = self._turn_ai_id
        if await self._cancel_turn() and ai_id is not None:
            await self.send(InterruptedMsg(message_id=str(ai_id)))

    async def wait_idle(self) -> None:
        """Wait for the running turn to finish (scripts and tests)."""
        if self._turn is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._turn

    def _launch(self, coro: Coroutine[Any, Any, None]) -> None:
        self._turn = asyncio.create_task(self._guarded(coro))

    async def _cancel_turn(self) -> bool:
        task = self._turn
        if task is None or task.done():
            return False
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        return True

    async def _guarded(self, coro: Coroutine[Any, Any, None]) -> None:
        """A failing turn must never take the WebSocket down."""
        try:
            await coro
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Turn failed")
            with contextlib.suppress(Exception):
                await self._error("provider_unavailable")
        finally:
            self._turn_ai_id = None

    async def handle_user_text(self, text: str) -> None:
        """Run a typed turn to completion (kept for callers that do not need barge-in)."""
        await self._text_turn(text, Timings(time.perf_counter()))

    async def _text_turn(self, text: str, timings: Timings) -> None:
        text = text.strip()
        if not text:
            await self._error("bad_request")
            return
        snap = await self._snapshot()
        if snap.daily_cap_reached:
            await self._error("quota_exceeded")
            return
        await self._respond(text, snap, timings)

    async def _voice_turn(self, audio: bytes, mime: str, timings: Timings) -> None:
        snap = await self._snapshot()
        if snap.daily_cap_reached or snap.stt_cap_reached(estimate_seconds(len(audio), mime)):
            await self._error("quota_exceeded")
            return
        try:
            result = await transcribe(
                self.llm,
                self.settings,
                audio=audio,
                mime=mime,
                target_lang=self.learner.target_lang,
                native_lang=self.learner.native_lang,
                record=self._record_stt,
                context=self._last_ai_text(),
            )
        except SttError as exc:
            await self._error("not_configured" if exc.code == "not_configured" else "stt_failed")
            return
        timings.stt_ms = _ms(timings.started)
        await self._respond(
            result.text, snap, timings, audio=AudioInput(data=audio, mime=gemini_mime(mime))
        )

    def _last_ai_text(self) -> str | None:
        """The AI's last reply (context for the STT): what the learner is answering."""
        turns = self.memory.context_turns()
        return turns[-1].ai if turns else None

    async def _respond(
        self,
        text: str,
        snap: usage_svc.UsageSnapshot,
        timings: Timings,
        *,
        audio: AudioInput | None = None,
    ) -> None:
        user_msg_id = await self._persist(role="user", text=text)
        await self.send(TranscriptMsg(message_id=str(user_msg_id), text=text))
        # Track 2 runs beside the reply and survives barge-in (SPEC §5).
        if feedback_svc.needs_feedback(text):
            self._spawn_feedback(user_msg_id, text, audio, budget_exceeded=snap.budget_exceeded)
        recast_audio = audio if self.learner.recast_pronunciation else None

        ai_msg_id = uuid.uuid4()
        self._turn_ai_id = ai_msg_id
        sentences: asyncio.Queue[str | None] = asyncio.Queue()
        speaker = (
            asyncio.create_task(
                self._speak(ai_msg_id, sentences, timings, over=snap.tts_over_allowance)
            )
            if self.tts is not None
            else None
        )
        buffer = SentenceBuffer()
        parts: list[str] = []

        def on_delta(delta: str) -> None:
            parts.append(delta)
            for sentence in buffer.push(delta):
                sentences.put_nowait(sentence)

        try:
            reply = await self._stream_reply(
                text,
                ai_msg_id,
                budget_exceeded=snap.budget_exceeded,
                on_delta=on_delta,
                timings=timings,
                audio=recast_audio,
            )
        except asyncio.CancelledError:
            if speaker is not None:
                speaker.cancel()
            await self._keep_partial(text, "".join(parts), ai_msg_id)
            raise
        if reply is None:
            if speaker is not None:
                speaker.cancel()
            return

        rest = buffer.flush()
        if rest:
            sentences.put_nowait(rest)
        sentences.put_nowait(None)

        await self._persist(role="ai", text=reply, message_id=ai_msg_id)
        await self.send(AiTextDoneMsg(message_id=str(ai_msg_id), text=reply))
        self.memory.add_turn(text, reply)
        self._maybe_summarize()

        if speaker is not None:
            try:
                await speaker
            except asyncio.CancelledError:
                speaker.cancel()
                raise
        await self.send(
            MetricsMsg(
                message_id=str(ai_msg_id),
                stt_ms=timings.stt_ms,
                llm_first_token_ms=timings.llm_first_token_ms,
                first_audio_ms=timings.first_audio_ms,
                total_ms=_ms(timings.started),
            )
        )
        await self._send_usage()

    async def _keep_partial(self, user_text: str, partial: str, ai_msg_id: uuid.UUID) -> None:
        """An interrupted reply still happened: keep what was said so far in the history."""
        partial = partial.strip()
        if not partial:
            return
        await self._persist(role="ai", text=partial, message_id=ai_msg_id)
        self.memory.add_turn(user_text, partial)
        self._maybe_summarize()

    async def _speak(
        self,
        ai_msg_id: uuid.UUID,
        sentences: "asyncio.Queue[str | None]",
        timings: Timings,
        *,
        over: bool,
    ) -> None:
        """Synthesize the reply's sentences in order."""
        index = 0
        seq = 0
        while (sentence := await sentences.get()) is not None:
            seq = await self._speak_sentence(
                str(ai_msg_id), index, sentence, seq, over=over, timings=timings
            )
            index += 1

    async def _speak_sentence(
        self,
        message_id: str,
        index: int,
        text: str,
        seq: int,
        *,
        over: bool,
        timings: Timings | None = None,
        speaking_rate: float = 1.0,
    ) -> int:
        """Send one sentence as audio_meta + binary frames (or tts_fallback). Returns next seq.

        One chunk is held back so the last chunk of the sentence can carry final=true.
        """
        lang = self.learner.target_lang
        held: TtsChunk | None = None
        if self.tts is not None:
            try:
                async for chunk in self.tts.stream(
                    text,
                    lang,  # type: ignore[arg-type]
                    self.learner.voice_id,
                    speaking_rate,
                    record=self._record_tts,
                    over_allowance=over,
                ):
                    if timings is not None and timings.first_audio_ms is None:
                        timings.first_audio_ms = _ms(timings.started)
                    if held is not None:
                        await self._send_chunk(message_id, seq, index, held, final=False)
                        seq += 1
                    held = chunk
            except TtsUnavailable:
                held = None
        if held is not None:
            await self._send_chunk(message_id, seq, index, held, final=True)
            return seq + 1
        await self.send(
            TtsFallbackMsg(
                message_id=message_id,
                sentence=index,
                text=text,
                lang=lang,  # type: ignore[arg-type]
            )
        )
        return seq

    async def _send_chunk(
        self, message_id: str, seq: int, sentence: int, chunk: TtsChunk, *, final: bool
    ) -> None:
        meta = AudioMetaMsg(
            message_id=message_id, seq=seq, sentence=sentence, mime=chunk.mime, final=final
        )
        await self.send_audio(meta, chunk.data)

    async def _stream_reply(
        self,
        text: str,
        ai_msg_id: uuid.UUID,
        *,
        budget_exceeded: bool,
        on_delta: Callable[[str], None] | None = None,
        timings: Timings | None = None,
        audio: AudioInput | None = None,
    ) -> str | None:
        system = chat_system_prompt(
            target_lang=self.learner.target_lang,
            native_lang=self.learner.native_lang,
            level=self.learner.level,
            user_facts=self.learner.user_facts,
            summary=self.memory.summary,
            recast=audio is not None,
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
                audio=audio,
            ):
                if isinstance(event, TextDelta):
                    if timings is not None and timings.llm_first_token_ms is None:
                        timings.llm_first_token_ms = _ms(timings.started)
                    parts.append(event.text)
                    if on_delta is not None:
                        on_delta(event.text)
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

    # --- listen and repeat (SPEC §5) ------------------------------------------------------

    def speak_word(self, word: str) -> None:
        """▶ in the panel: the word in the learner's voice, from the TTS cache when possible."""
        self._spawn(self._speak_word(word.strip()))

    async def _speak_word(self, word: str) -> None:
        if not word:
            await self._error("bad_request")
            return
        snap = await self._snapshot()
        await self._speak_sentence(f"word:{word}", 0, word, 0, over=snap.tts_over_allowance)

    def pron_retry(self, audio: bytes, mime: str, word: str, message_id: str) -> None:
        """🎙 in the panel: judge one new attempt at one word."""
        self._spawn(self._pron_retry(audio, mime, word.strip(), message_id))

    async def _pron_retry(self, audio: bytes, mime: str, word: str, message_id: str) -> None:
        snap = await self._snapshot()
        if snap.daily_cap_reached or snap.stt_cap_reached(estimate_seconds(len(audio), mime)):
            await self._error("quota_exceeded")
            return
        judged = await feedback_svc.judge_retry(
            self.llm,
            self.settings,
            word=word,
            audio=AudioInput(data=audio, mime=gemini_mime(mime)),
            target_lang=self.learner.target_lang,
            native_lang=self.learner.native_lang,
            budget_exceeded=snap.budget_exceeded,
            record=self._record_llm,
            explain_lang=self.learner.ui_lang,
        )
        if judged is None:
            await self._error("stt_failed")
            return
        result, used, model = judged
        seconds = (
            used.audio_tokens / AUDIO_TOKENS_PER_SECOND
            if used.audio_tokens
            else estimate_seconds(len(audio), mime)
        )
        async with session_factory()() as db:
            await usage_svc.record_audio_seconds(
                db, user_id=self.learner.id, role="feedback", model=model, seconds=round(seconds, 2)
            )
        await self.send(
            PronResultMsg(message_id=message_id, word=word, better=result.better, tip=result.tip)
        )

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> None:
        """Side work that must not block the socket or be cancelled by barge-in."""
        task = asyncio.create_task(self._quiet(coro))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _quiet(self, coro: Coroutine[Any, Any, None]) -> None:
        try:
            await coro
        except Exception:  # noqa: BLE001 — never break the conversation
            log.exception("Background task failed")
            with contextlib.suppress(Exception):
                await self._error("provider_unavailable")

    # --- Track 2: feedback (SPEC §5) ------------------------------------------------------

    def _spawn_feedback(
        self,
        message_id: uuid.UUID,
        text: str,
        audio: AudioInput | None,
        *,
        budget_exceeded: bool,
    ) -> None:
        task = asyncio.create_task(
            self._feedback(message_id, text, audio, budget_exceeded=budget_exceeded)
        )
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _feedback(
        self,
        message_id: uuid.UUID,
        text: str,
        audio: AudioInput | None,
        *,
        budget_exceeded: bool,
    ) -> None:
        try:
            result = await feedback_svc.analyze(
                self.llm,
                self.settings,
                text=text,
                audio=audio,
                target_lang=self.learner.target_lang,
                native_lang=self.learner.native_lang,
                budget_exceeded=budget_exceeded,
                record=self._record_llm,
                explain_lang=self.learner.ui_lang,
            )
            if result is None:
                return
            async with session_factory()() as db:
                msg = await db.get(Message, message_id)
                if msg is not None:
                    msg.feedback = result.as_json()
                await db.commit()  # always end the transaction (SQLite holds locks otherwise)
                if not result.ok:
                    await flashcards_svc.add_from_feedback(
                        db,
                        user_id=self.learner.id,
                        lang=self.learner.target_lang,
                        message_id=message_id,
                        message=text,
                        errs=result.errs,
                        pron=result.pron,
                    )
            await self.send(
                FeedbackMsg(
                    message_id=str(message_id),
                    source="audio" if audio is not None else "text",
                    ok=result.ok,
                    errs=result.errs,
                    pron=result.pron,
                )
            )
        except Exception:  # noqa: BLE001 — feedback must never break the conversation
            log.exception("Feedback task failed")

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

    async def _record_stt(self, model: str, usage: LlmUsage, seconds: float) -> None:
        async with session_factory()() as db:
            await usage_svc.record_stt(
                db, user_id=self.learner.id, model=model, usage=usage, seconds=seconds
            )

    async def _record_tts(self, provider: str, model: str, chars: int) -> None:
        async with session_factory()() as db:
            await usage_svc.record_tts(
                db, user_id=self.learner.id, provider=provider, model=model, chars=chars
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
