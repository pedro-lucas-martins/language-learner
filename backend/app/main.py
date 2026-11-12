import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import database
from app.config import get_settings
from app.routers import flashcards, me, ws_chat
from app.services.llm import GeminiProvider
from app.services.tts.cache import DbTtsCache
from app.services.tts.chain import TtsChain, build_active_provider
from app.services.tts.edge import EdgeTts

settings = get_settings()
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Tests may install their own engine and LLM before startup; keep them.
    owns_engine = not database.is_initialized()
    if owns_engine:
        database.init_engine(settings.database_url)
    if getattr(app.state, "llm", None) is None:
        app.state.llm = GeminiProvider(
            settings.gemini_api_key, thinking_level=settings.gemini_thinking_level
        )
    if getattr(app.state, "tts", None) is None:
        app.state.tts = TtsChain(
            build_active_provider(settings),
            EdgeTts(settings),
            cache=DbTtsCache(settings.tts_cache_max_mb),
        )
    yield
    if owns_engine:
        await database.dispose_engine()


app = FastAPI(title="Language Learner API", version="0.2.0", lifespan=lifespan)
app.state.llm = None
app.state.tts = None
app.state.settings = settings

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=settings.vercel_preview_regex or None,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(me.router)
app.include_router(flashcards.router)
app.include_router(ws_chat.router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe for the PaaS and for the frontend's connection check."""
    return {"status": "ok", "env": settings.app_env}
