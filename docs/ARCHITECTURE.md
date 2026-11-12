# Architecture — current state

Describes what exists **now**. Target design lives in [`SPEC.md`](SPEC.md).

_Last updated: slice 2a (TTS adapters and benchmark; voice not wired into the chat yet)._

## Overview

```
browser (React)  ──WebSocket /ws──▶  FastAPI  ──▶  Gemini (chat + summaries)
      │                                 │
      └── GET /me (Bearer token) ───────┴──▶  Postgres (users, sessions, messages, usage)
```

## A text turn

1. The browser opens `/ws`. The server checks the `Origin` header by hand (CORS does not
   cover WebSockets) and closes with **4403** if it is not allowlisted.
2. The first message must be `{"type":"auth","token":…}` within 5 s, else close **4401**.
   The server sends `ready` (user info) and `usage`.
3. `user_text` → daily-cap check → the message is stored and echoed as `transcript`.
4. The system prompt is built (static persona + direction notes, level rules, `user_facts`,
   running summary) and sent with the pending + window turns and the new text.
5. Gemini streams the reply as `ai_text_delta`; then `ai_text_done` and an updated `usage`.
6. The turn enters the memory window. When enough turns have left the window, a background
   task summarizes them with the utility model (SPEC §4.2).
7. On disconnect the session gets `ended_at` and its final summary (close is shielded from
   cancellation).

## Backend (`backend/`)

| Path | Purpose |
|---|---|
| `app/main.py` | App, lifespan (DB engine, Gemini provider), REST CORS, `/health` |
| `app/config.py` | All settings from env. Model names, TTS provider + voices, prices, caps |
| `app/security.py` | `is_allowed_origin()` for REST CORS and the WebSocket check |
| `app/database.py` | Async SQLAlchemy engine/session factory (NullPool for SQLite in tests) |
| `app/models.py` | `users`, `chat_sessions`, `messages`, `usage_events` |
| `app/protocol.py` | Pydantic models of the WebSocket protocol (text subset) |
| `app/i18n.py` | Server error messages in pt-BR and pl-PL |
| `app/routers/ws_chat.py` | `/ws`: origin check, auth, message loop |
| `app/routers/me.py` | `GET /me` with `Authorization: Bearer` |
| `app/services/auth.py` | Token generation, SHA-256 storage, `authenticate`, `create_user` |
| `app/services/llm.py` | `LlmProvider` interface, `GeminiProvider`, retry + model fallback, `FakeLlm` |
| `app/services/prompts.py` | System prompts per direction and level, summary prompt |
| `app/services/memory.py` | Pure sliding window + pending buffer + summary bookkeeping |
| `app/services/usage.py` | `usage_events` rows, daily call cap, monthly spend estimate |
| `app/services/conversation.py` | Per-socket orchestrator for a turn |
| `app/services/tts/base.py` | `TtsProvider` interface, `TtsError`, first-byte/total timeouts, voice choice |
| `app/services/tts/google.py` | Google Chirp 3 HD via gRPC streaming, OGG_OPUS output |
| `app/services/tts/elevenlabs.py` | ElevenLabs streaming over HTTP (`httpx`), MP3 output |
| `app/services/tts/edge.py` | edge-tts, the free fallback (MP3) |
| `app/services/tts/chain.py` | Active provider → edge-tts → `TtsUnavailable` (browser speaks); retry once |
| `app/services/tts/cache.py` | `tts_cache` table access, sha256 key, LRU eviction by `TTS_CACHE_MAX_MB` |
| `alembic/` | Migrations (`0001_initial`, `0002_tts_cache`) |
| `scripts/create_user.py` | Creates a learner and prints the token once |
| `scripts/tts_bench.py` | TTS benchmark: TTFA per provider × language, blind A/B page, asks before spending |

**LLM fallback:** each model gets one retry for transient errors; then the next model in the
chain (`GEMINI_CHAT_MODEL` → `GEMINI_UTILITY_MODEL`). When the monthly budget is reached
only the utility model is used. Once text has been streamed, errors are not retried.

**TTS chain:** the provider in `TTS_PROVIDER` is tried first (one retry for 429/5xx/timeout,
3 s to first byte); before any audio is sent it can fall back to edge-tts; if that fails too the
caller must ask the browser to speak (`TtsUnavailable`). Over 95% of `TTS_MONTHLY_CHARS` or over
the daily character cap, edge-tts is used directly. A `tts_chars` row is written per request.
Not yet called by the conversation (slice 2b).

**Caps:** one `llm_in` row is written per LLM call; `DAILY_LLM_CALLS_PER_USER` counts them.
The spend estimate multiplies summed usage by the `PRICE_*` settings.

## Frontend (`frontend/`)

| Path | Purpose |
|---|---|
| `src/protocol.ts` | Protocol types mirroring `app/protocol.py`, safe frame parser |
| `src/i18n.ts` | UI strings in pt-BR and pl-PL (same keys enforced by a test) |
| `src/storage.ts` | Token in `localStorage`, every access wrapped in try/catch |
| `src/chat/state.ts` | Pure reducer for connection, messages, streaming, errors, usage |
| `src/chat/useChatSocket.ts` | Owns the WebSocket, auth, commands, reconnect |
| `src/components/LoginScreen.tsx` | Token login (language guessed from the browser) |
| `src/components/ChatScreen.tsx` | Text chat, level selector, errors, spend line |

## Tests

- Backend (pytest, SQLite + `FakeLlm`, never a real provider): memory invariant over random
  sequences, prompts in both directions, retry/fallback rules, usage and caps, auth, `/me`,
  and end-to-end WebSocket tests (origin, auth, streaming, persistence, summary, level,
  errors, daily cap, provider down, missing configuration).
- CI also applies the migrations to a real Postgres and runs `alembic check`.
- Frontend (vitest): reducer, frame parser, i18n key parity, language detection.

## Not built yet

Voice in the conversation (STT, sentence buffer, audio over the WebSocket, client audio), feedback track, pronunciation, topics, flashcards, user_facts updates,
responsive layouts, deploy. See SPEC §11.
