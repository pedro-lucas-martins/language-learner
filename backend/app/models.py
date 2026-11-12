"""Database tables (SPEC §3, §4, §5, §6)."""

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

Lang = Literal["pt-BR", "pl-PL"]
Level = Literal["A1", "A2", "B1", "B2", "C1"]
Role = Literal["user", "ai"]
UsageKind = Literal["llm_in", "llm_out", "llm_audio_in", "stt_audio_s", "tts_chars"]

LANGS: tuple[str, ...] = ("pt-BR", "pl-PL")
LEVELS: tuple[str, ...] = ("A1", "A2", "B1", "B2", "C1")


def utcnow() -> datetime:
    return datetime.now(UTC)


def _in(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(_in("native_lang", LANGS), name="ck_users_native_lang"),
        CheckConstraint(_in("target_lang", LANGS), name="ck_users_target_lang"),
        CheckConstraint("native_lang <> target_lang", name="ck_users_langs_differ"),
        CheckConstraint(_in("level", LEVELS), name="ck_users_level"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80))
    native_lang: Mapped[str] = mapped_column(String(5))
    target_lang: Mapped[str] = mapped_column(String(5))
    level: Mapped[str] = mapped_column(String(2), default="A1")
    user_facts: Mapped[str] = mapped_column(Text, default="")
    voice_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    recast_pronunciation: Mapped[bool] = mapped_column(Boolean, default=True)
    access_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    running_summary: Mapped[str] = mapped_column(Text, default="")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'ai')", name="ck_messages_role"),
        Index("ix_messages_session_created", "session_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(4))
    text: Mapped[str] = mapped_column(Text)
    # Track 2 result for user messages, as JSON (SPEC §5).
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UsageEvent(Base):
    """One row per paid/quota-limited call. Single source for caps and spend (SPEC §3)."""

    __tablename__ = "usage_events"
    __table_args__ = (Index("ix_usage_user_kind_created", "user_id", "kind", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    # Which price applies: "chat", "utility", "stt" or a TTS provider name.
    role: Mapped[str] = mapped_column(String(16))
    model: Mapped[str] = mapped_column(String(80), default="")
    amount: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TtsCache(Base):
    """Synthesized audio, keyed by sha256(provider + voice + model + rate + text) (SPEC §6)."""

    __tablename__ = "tts_cache"
    __table_args__ = (Index("ix_tts_cache_last_used", "last_used_at"),)

    hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(16))
    voice_id: Mapped[str] = mapped_column(String(120))
    model: Mapped[str] = mapped_column(String(80))
    mime: Mapped[str] = mapped_column(String(40))
    audio: Mapped[bytes] = mapped_column(LargeBinary)
    bytes: Mapped[int] = mapped_column(Integer)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Flashcard(Base):
    """One card per mistake, scheduled with SM-2 (SPEC §5)."""

    __tablename__ = "flashcards"
    __table_args__ = (
        CheckConstraint("kind IN ('grammar', 'pronunciation')", name="ck_flashcards_kind"),
        UniqueConstraint("user_id", "kind", "front", name="uq_flashcards_user_kind_front"),
        Index("ix_flashcards_user_due", "user_id", "due_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))
    front: Mapped[str] = mapped_column(Text)
    back: Mapped[str] = mapped_column(Text)
    # Pronunciation cards: the word to listen to and retry.
    word: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lang: Mapped[str] = mapped_column(String(5))
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    ease: Mapped[float] = mapped_column(Float, default=2.5)
    interval_days: Mapped[int] = mapped_column(Integer, default=0)
    repetitions: Mapped[int] = mapped_column(Integer, default=0)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
