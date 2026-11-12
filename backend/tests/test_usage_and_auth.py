from datetime import UTC, datetime, timedelta

from sqlalchemy.engine import Engine

from app.database import session_factory
from app.models import UsageEvent
from app.services import usage as usage_svc
from app.services.auth import authenticate, create_user, hash_token
from app.services.llm import LlmUsage
from tests.conftest import add_user, make_settings


async def test_create_user_sets_opposite_target_and_stores_only_hash(sync_engine: Engine) -> None:
    async with session_factory()() as db:
        user, token = await create_user(db, name="Ola", native_lang="pl-PL", level="B1")
    assert user.target_lang == "pt-BR"
    assert user.access_token_hash == hash_token(token)
    assert token not in user.access_token_hash


async def test_authenticate(sync_engine: Engine) -> None:
    token = add_user(sync_engine)
    async with session_factory()() as db:
        assert (await authenticate(db, token)) is not None
        assert (await authenticate(db, token + "x")) is None
        assert (await authenticate(db, "")) is None
        assert (await authenticate(db, None)) is None
        assert (await authenticate(db, "x" * 500)) is None


async def test_spend_estimate_uses_configured_prices(sync_engine: Engine) -> None:
    add_user(sync_engine)
    settings = make_settings(
        price_chat_input_per_m=1.0,
        price_chat_output_per_m=4.0,
        price_utility_input_per_m=0.1,
        price_utility_output_per_m=0.4,
    )
    async with session_factory()() as db:
        await usage_svc.record_llm(
            db, user_id=None, role="chat", model="m", usage=LlmUsage(1_000_000, 500_000)
        )
        await usage_svc.record_llm(
            db, user_id=None, role="utility", model="u", usage=LlmUsage(2_000_000, 0)
        )
        spend = await usage_svc.month_spend_usd(db, settings)
    assert round(spend, 6) == round(1.0 + 2.0 + 0.2, 6)


async def test_last_month_is_not_counted(sync_engine: Engine) -> None:
    settings = make_settings(price_chat_input_per_m=1.0)
    old = datetime.now(UTC) - timedelta(days=40)
    async with session_factory()() as db:
        db.add(UsageEvent(kind="llm_in", role="chat", model="m", amount=1_000_000, created_at=old))
        await db.commit()
        assert await usage_svc.month_spend_usd(db, settings) == 0


async def test_daily_cap_and_budget_flags(sync_engine: Engine) -> None:
    add_user(sync_engine)
    settings = make_settings(
        daily_llm_calls_per_user=2, monthly_budget_usd=0.000001, price_chat_input_per_m=1.0
    )
    async with session_factory()() as db:
        from sqlalchemy import select

        from app.models import User

        user = await db.scalar(select(User))
        assert user is not None
        snap = await usage_svc.snapshot(db, settings, user.id)
        assert not snap.daily_cap_reached and not snap.budget_exceeded
        for _ in range(2):
            await usage_svc.record_llm(
                db, user_id=user.id, role="chat", model="m", usage=LlmUsage(100, 10)
            )
        snap = await usage_svc.snapshot(db, settings, user.id)
    assert snap.llm_calls_today == 2
    assert snap.daily_cap_reached
    assert snap.budget_exceeded


async def test_tts_usage_prices_paid_providers_only(sync_engine: Engine) -> None:
    settings = make_settings(price_tts_per_1k_chars=0.5)
    async with session_factory()() as db:
        await usage_svc.record_tts(db, user_id=None, provider="google", model="m", chars=2000)
        await usage_svc.record_tts(db, user_id=None, provider="edge", model="edge", chars=5000)
        assert round(await usage_svc.month_spend_usd(db, settings), 6) == 1.0
        assert await usage_svc.tts_chars_month(db, "google") == 2000


async def test_tts_over_allowance_at_95_percent_or_daily_cap(sync_engine: Engine) -> None:
    add_user(sync_engine)
    async with session_factory()() as db:
        from sqlalchemy import select

        from app.models import User

        user = await db.scalar(select(User))
        assert user is not None
        await usage_svc.record_tts(db, user_id=user.id, provider="google", model="m", chars=94)
        await usage_svc.record_tts(db, user_id=user.id, provider="edge", model="e", chars=500)
        below = await usage_svc.snapshot(
            db, make_settings(tts_monthly_chars=100, daily_tts_chars_per_user=0), user.id
        )
        await usage_svc.record_tts(db, user_id=user.id, provider="google", model="m", chars=1)
        at_95 = await usage_svc.snapshot(
            db, make_settings(tts_monthly_chars=100, daily_tts_chars_per_user=0), user.id
        )
        capped = await usage_svc.snapshot(
            db, make_settings(tts_monthly_chars=0, daily_tts_chars_per_user=95), user.id
        )
    assert not below.tts_over_allowance
    assert at_95.tts_over_allowance
    assert capped.tts_chars_today == 95  # edge characters are not counted
    assert capped.tts_over_allowance
