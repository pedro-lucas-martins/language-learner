"""Usage tracking, daily caps and monthly spend estimate (SPEC §1, §3)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import UsageEvent
from app.services.llm import LlmUsage

# edge-tts is free: its characters are tracked but cost nothing and do not count toward caps.
FREE_TTS_PROVIDER = "edge"


def _start_of_day(now: datetime) -> datetime:
    return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def _start_of_month(now: datetime) -> datetime:
    return _start_of_day(now).replace(day=1)


def _unit_price(settings: Settings, kind: str, role: str) -> float:
    """USD per unit of `amount` for a usage row."""
    per_m = 1_000_000
    if role == "stt":
        if kind == "llm_in":
            return settings.price_stt_audio_input_per_m / per_m
        if kind == "llm_out":
            return settings.price_utility_output_per_m / per_m
        return 0.0
    if kind == "llm_in":
        price = (
            settings.price_chat_input_per_m
            if role == "chat"
            else settings.price_utility_input_per_m
        )
        return price / per_m
    if kind == "llm_out":
        price = (
            settings.price_chat_output_per_m
            if role == "chat"
            else settings.price_utility_output_per_m
        )
        return price / per_m
    if kind == "llm_audio_in":
        return settings.price_stt_audio_input_per_m / per_m
    if kind == "tts_chars":
        if role == FREE_TTS_PROVIDER:
            return 0.0
        return settings.price_tts_per_1k_chars / 1000
    return 0.0


async def record_llm(
    db: AsyncSession, *, user_id: uuid.UUID | None, role: str, model: str, usage: LlmUsage
) -> None:
    db.add_all(
        [
            UsageEvent(
                user_id=user_id, kind="llm_in", role=role, model=model, amount=usage.input_tokens
            ),
            UsageEvent(
                user_id=user_id, kind="llm_out", role=role, model=model, amount=usage.output_tokens
            ),
        ]
    )
    await db.commit()


async def record_stt(
    db: AsyncSession, *, user_id: uuid.UUID | None, model: str, usage: LlmUsage, seconds: float
) -> None:
    """Token rows (priced as audio input) plus the audio seconds for the daily cap."""
    await record_llm(db, user_id=user_id, role="stt", model=model, usage=usage)
    db.add(UsageEvent(user_id=user_id, kind="stt_audio_s", role="stt", model=model, amount=seconds))
    await db.commit()


async def stt_seconds_today(
    db: AsyncSession, user_id: uuid.UUID, now: datetime | None = None
) -> float:
    since = _start_of_day(now or datetime.now(UTC))
    total = await db.scalar(
        select(func.sum(UsageEvent.amount)).where(
            UsageEvent.user_id == user_id,
            UsageEvent.kind == "stt_audio_s",
            UsageEvent.created_at >= since,
        )
    )
    return float(total or 0)


async def record_tts(
    db: AsyncSession, *, user_id: uuid.UUID | None, provider: str, model: str, chars: int
) -> None:
    db.add(UsageEvent(user_id=user_id, kind="tts_chars", role=provider, model=model, amount=chars))
    await db.commit()


async def tts_chars_today(db: AsyncSession, user_id: uuid.UUID, now: datetime | None = None) -> int:
    """Paid TTS characters today for one user (the free fallback is not counted)."""
    since = _start_of_day(now or datetime.now(UTC))
    total = await db.scalar(
        select(func.sum(UsageEvent.amount)).where(
            UsageEvent.user_id == user_id,
            UsageEvent.kind == "tts_chars",
            UsageEvent.role != FREE_TTS_PROVIDER,
            UsageEvent.created_at >= since,
        )
    )
    return int(total or 0)


async def llm_calls_today(db: AsyncSession, user_id: uuid.UUID, now: datetime | None = None) -> int:
    """One `llm_in` row is written per LLM call, so counting them counts calls."""
    since = _start_of_day(now or datetime.now(UTC))
    count = await db.scalar(
        select(func.count(UsageEvent.id)).where(
            UsageEvent.user_id == user_id,
            UsageEvent.kind == "llm_in",
            UsageEvent.created_at >= since,
        )
    )
    return int(count or 0)


async def month_spend_usd(
    db: AsyncSession, settings: Settings, now: datetime | None = None
) -> float:
    """Estimated spend this calendar month (UTC), across all users."""
    since = _start_of_month(now or datetime.now(UTC))
    rows = await db.execute(
        select(UsageEvent.kind, UsageEvent.role, func.sum(UsageEvent.amount))
        .where(UsageEvent.created_at >= since)
        .group_by(UsageEvent.kind, UsageEvent.role)
    )
    return sum(float(total or 0) * _unit_price(settings, kind, role) for kind, role, total in rows)


async def tts_chars_month(db: AsyncSession, provider: str, now: datetime | None = None) -> int:
    since = _start_of_month(now or datetime.now(UTC))
    total = await db.scalar(
        select(func.sum(UsageEvent.amount)).where(
            UsageEvent.kind == "tts_chars",
            UsageEvent.role == provider,
            UsageEvent.created_at >= since,
        )
    )
    return int(total or 0)


@dataclass(frozen=True)
class UsageSnapshot:
    month_usd_est: float
    budget_usd: float
    tts_chars_month: int
    tts_chars_allowance: int
    tts_provider_active: str
    llm_calls_today: int
    llm_calls_cap: int
    tts_chars_today: int = 0
    tts_chars_cap: int = 0
    stt_seconds_today: float = 0.0
    stt_seconds_cap: int = 0

    def stt_cap_reached(self, extra_seconds: float = 0.0) -> bool:
        return self.stt_seconds_cap > 0 and (
            self.stt_seconds_today + extra_seconds > self.stt_seconds_cap
        )

    @property
    def budget_exceeded(self) -> bool:
        return self.budget_usd > 0 and self.month_usd_est >= self.budget_usd

    @property
    def tts_over_allowance(self) -> bool:
        """Switch to the free fallback: 95% of the monthly allowance or the daily cap (SPEC §1)."""
        monthly = self.tts_chars_allowance > 0 and (
            self.tts_chars_month >= 0.95 * self.tts_chars_allowance
        )
        daily = self.tts_chars_cap > 0 and self.tts_chars_today >= self.tts_chars_cap
        return monthly or daily

    @property
    def daily_cap_reached(self) -> bool:
        return self.llm_calls_cap > 0 and self.llm_calls_today >= self.llm_calls_cap


async def snapshot(db: AsyncSession, settings: Settings, user_id: uuid.UUID) -> UsageSnapshot:
    return UsageSnapshot(
        month_usd_est=round(await month_spend_usd(db, settings), 4),
        budget_usd=settings.monthly_budget_usd,
        tts_chars_month=await tts_chars_month(db, settings.tts_provider),
        tts_chars_allowance=settings.tts_monthly_chars,
        tts_provider_active=settings.tts_provider,
        llm_calls_today=await llm_calls_today(db, user_id),
        llm_calls_cap=settings.daily_llm_calls_per_user,
        tts_chars_today=await tts_chars_today(db, user_id),
        tts_chars_cap=settings.daily_tts_chars_per_user,
        stt_seconds_today=await stt_seconds_today(db, user_id),
        stt_seconds_cap=settings.daily_stt_seconds_per_user,
    )
