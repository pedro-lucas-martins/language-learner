"""Shared fixtures. Tests use SQLite, FakeLlm and FakeTts — never Postgres or a real provider."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app import (
    database,
    models,  # noqa: F401  (registers tables)
)
from app.config import Settings
from app.main import app
from app.models import User
from app.services.auth import generate_token, hash_token
from app.services.llm import FakeLlm
from app.services.tts.chain import TtsChain
from tests.fakes_tts import FakeTts, MemoryCache

ORIGIN = "http://localhost:5173"


def make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "app_env": "development",
        "frontend_url": ORIGIN,
        "gemini_chat_model": "chat-model",
        "gemini_utility_model": "utility-model",
        "window_turns": 3,
        "summary_batch_turns": 3,
        "daily_llm_calls_per_user": 400,
        "monthly_budget_usd": 15,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def sync_engine(db_path: Path) -> Iterator[Engine]:
    """Creates the schema and points the app's async engine at the same file."""
    engine = create_engine(f"sqlite:///{db_path}")
    database.Base.metadata.create_all(engine)
    database.init_engine(f"sqlite+aiosqlite:///{db_path}")
    yield engine
    engine.dispose()
    database._engine = None  # NullPool: nothing to dispose
    database._session_factory = None


def add_user(
    engine: Engine, *, native: str = "pt-BR", level: str = "A1", name: str = "Pedro"
) -> str:
    token = generate_token()
    with Session(engine) as db:
        db.add(
            User(
                name=name,
                native_lang=native,
                target_lang="pl-PL" if native == "pt-BR" else "pt-BR",
                level=level,
                user_facts="",
                recast_pronunciation=True,
                access_token_hash=hash_token(token),
            )
        )
        db.commit()
    return token


@pytest.fixture(autouse=True)
def fake_tts() -> Iterator[TtsChain]:
    """Installed for every test so the app never builds a real (networked) TTS chain."""
    chain = TtsChain(FakeTts("google"), FakeTts("edge"), cache=MemoryCache(), retry_delay_s=0)
    app.state.tts = chain
    yield chain
    app.state.tts = None


def wait_sessions_closed(engine: Engine, timeout: float = 5.0) -> None:
    """Let the server finish closing every chat session before the test client stops.

    The close runs after the client disconnects (it writes to SQLite). If the TestClient
    shut its event loop first, aiosqlite's worker thread would hit a closed loop.
    """
    import time

    from sqlalchemy import func, select

    from app.models import ChatSession

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with Session(engine) as db:
            open_sessions = db.scalar(
                select(func.count(ChatSession.id)).where(ChatSession.ended_at.is_(None))
            )
        if not open_sessions:
            return
        time.sleep(0.01)


@pytest.fixture
def fake_llm() -> FakeLlm:
    return FakeLlm()


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def client(sync_engine: Engine, settings: Settings, fake_llm: FakeLlm) -> Iterator[TestClient]:
    original_settings = app.state.settings
    app.state.settings = settings
    app.state.llm = fake_llm
    with TestClient(app) as test_client:
        yield test_client
        wait_sessions_closed(sync_engine)
    app.state.settings = original_settings
    app.state.llm = None
