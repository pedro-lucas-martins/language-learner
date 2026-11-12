# Architecture — current state

Describes what exists **now**. Target design lives in [`SPEC.md`](SPEC.md).

_Last updated: slice 3 (feedback, recast, regrade, flashcards and listen-and-repeat, backend and UI)._

## Overview

```
browser (React)  ──WebSocket /ws──▶  FastAPI  ──▶  Gemini (chat + summaries)
      │                                 │
      └── GET /me (Bearer token) ───────┴──▶  Postgres (users, sessions, messages, usage)
```

## A voice turn

1. `start_of_speech` (`mime`) → one binary frame with the whole utterance (≤ 2 MB) → `end_of_speech`.
2. Caps checked (daily LLM calls; daily STT seconds estimated from size). Gemini transcribes
   verbatim (`stt_service.py`, own model and thinking level), with the AI's last message as
   context for hard words; `usage_events` get tokens and audio seconds.
3. From here it is a text turn (below) whose input is the transcript.

The turn runs as an `asyncio` task. `user_started_speaking`, a new utterance or a typed message
cancels it (LLM and TTS); the server sends `interrupted` and keeps the partial reply in history.

## Interface language

`users.ui_lang` (default: `native_lang`) sets the UI strings, server messages and the language
of every explanation; `set_ui_lang` changes it from the header selector.

## Track 2: feedback (SPEC §5)

For every learner message with ≥ 3 words a background task (not cancelled by barge-in) calls
`GEMINI_FEEDBACK_MODEL` with a JSON schema: audio + transcript on voice turns (grammar and
pronunciation), text only for typed turns and regrades (grammar only). The result is validated,
filtered (`feedback.py`), stored on `messages.feedback` and sent as `feedback`. Explanations are
in the learner's native language. `regrade` edits a message's text and re-runs grammar.
`set_recast` toggles the pronunciation recast: when on, voice turns also send the audio to the
chat model with a recast rule.

## Flashcards and listen-and-repeat

Every feedback with mistakes adds cards (`flashcards.py`, deduplicated). REST under
`/flashcards` lists due cards and records SM-2 reviews (`sm2.py`). Over the WebSocket,
`speak_word` sends a word's audio (`message_id = word:<word>`, cached) and `pron_retry`
(a `start_of_speech` with `purpose: pron_retry`) returns `pron_result` judged from the audio.

## A text turn

1. The browser opens `/ws`. The server checks the `Origin` header by hand (CORS does not
   cover WebSockets) and closes with **4403** if it is not allowlisted.
2. The first message must be `{"type":"auth","token":…}` within 5 s, else close **4401**.
   The server sends `ready` (user info) and `usage`.
3. `user_text` → daily-cap check → the message is stored and echoed as `transcript`.
4. The system prompt is built (static persona + direction notes, level rules, `user_facts`,
   running summary) and sent with the pending + window turns and the new text.
5. Gemini streams the reply as `ai_text_delta`. The deltas also feed the sentence buffer;
   each complete sentence goes to the TTS chain in order. Every audio chunk is sent as
   `audio_meta` (`sentence`, `seq`, `mime`, `final`) followed by one binary frame. If all
   server voices fail, `tts_fallback` asks the browser to speak that sentence.
   Then `ai_text_done`, `metrics` (stt / first token / first audio / total ms) and `usage`.
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
| `app/models.py` | `users`, `chat_sessions`, `messages` (+ `feedback`), `usage_events`, `tts_cache`, `flashcards` |
| `app/protocol.py` | Pydantic models of the WebSocket protocol (text subset) |
| `app/i18n.py` | Server error messages in pt-BR and pl-PL |
| `app/routers/ws_chat.py` | `/ws`: origin check, auth, message loop |
| `app/routers/me.py` | `GET /me` with `Authorization: Bearer` |
| `app/services/auth.py` | Token generation, SHA-256 storage, `authenticate`, `create_user` |
| `app/services/llm.py` | `LlmProvider` interface, `GeminiProvider`, retry + model fallback, `FakeLlm` |
| `app/services/prompts.py` | System prompts per direction and level, summary prompt |
| `app/services/memory.py` | Pure sliding window + pending buffer + summary bookkeeping |
| `app/services/usage.py` | `usage_events` rows, daily call cap, monthly spend estimate |
| `app/services/conversation.py` | Per-socket orchestrator: turn tasks, barge-in, LLM → sentences → TTS, metrics |
| `app/services/stt_service.py` | Gemini speech-to-text: verbatim prompt, retry, audio seconds |
| `app/services/feedback.py` | Track 2 prompts per direction, JSON schema, validation and filters |
| `app/services/flashcards.py` | Cards from feedback (front/back, dedupe) |
| `app/services/sm2.py` | SM-2 scheduling (pure) |
| `app/routers/flashcards.py` | `GET /flashcards`, `POST /flashcards/{id}/review`, `DELETE /flashcards/{id}` |
| `app/services/sentence_buffer.py` | Splits the streamed reply into sentences (decimals, dates, abbreviations) |
| `app/services/tts/base.py` | `TtsProvider` interface, `TtsError`, first-byte/total timeouts, voice choice |
| `app/services/tts/google.py` | Google Chirp 3 HD via gRPC streaming, OGG_OPUS output |
| `app/services/tts/elevenlabs.py` | ElevenLabs streaming over HTTP (`httpx`), MP3 output |
| `app/services/tts/edge.py` | edge-tts, the free fallback (MP3) |
| `app/services/tts/chain.py` | Active provider → edge-tts → `TtsUnavailable` (browser speaks); retry once |
| `app/services/tts/cache.py` | `tts_cache` table access, sha256 key, LRU eviction by `TTS_CACHE_MAX_MB` |
| `alembic/` | Migrations `0001`–`0004` (initial, tts_cache, feedback + flashcards, ui_lang) |
| `scripts/create_user.py` | Creates a learner and prints the token once |
| `scripts/stt_eval.py` | Runs your recorded clips through the STT and compares with what you said |
| `scripts/tts_bench.py` | TTS benchmark: TTFA per provider × language, blind A/B page, asks before spending |

**LLM fallback:** each model gets one retry for transient errors; then the next model in the
chain (`GEMINI_CHAT_MODEL` → `GEMINI_UTILITY_MODEL`). When the monthly budget is reached
only the utility model is used. Once text has been streamed, errors are not retried.

**TTS chain:** the provider in `TTS_PROVIDER` is tried first (one retry for 429/5xx/timeout,
3 s to first byte); before any audio is sent it can fall back to edge-tts; if that fails too the
caller must ask the browser to speak (`TtsUnavailable`). Over 95% of `TTS_MONTHLY_CHARS` or over
the daily character cap, edge-tts is used directly. A `tts_chars` row is written per request.
The conversation calls it once per sentence.

**Caps:** one `llm_in` row is written per LLM call; `DAILY_LLM_CALLS_PER_USER` counts them.
The spend estimate multiplies summed usage by the `PRICE_*` settings.

## Frontend (`frontend/`)

| Path | Purpose |
|---|---|
| `src/protocol.ts` | Protocol types mirroring `app/protocol.py`, safe frame parser |
| `src/i18n.ts` | UI strings in pt-BR and pl-PL (same keys enforced by a test) |
| `src/storage.ts` | Token in `localStorage`, every access wrapped in try/catch |
| `src/chat/state.ts` | Pure reducer for connection, messages, streaming, errors, usage |
| `src/chat/useChatSocket.ts` | Owns the WebSocket, auth, commands, reconnect; binary frames → voice layer |
| `src/chat/useVoice.ts` | Mic (hands-free VAD / push-to-talk), barge-in, playback, replay |
| `src/audio/recorder.ts` | MediaRecorder (webm/opus → mp4 → aac), one blob per utterance |
| `src/audio/vad.ts` | Volume VAD: pure detector (calibration, silence, discard) + mic monitor |
| `src/audio/assembler.ts` | Joins `audio_meta` + binary frames into complete sentences |
| `src/audio/player.ts` | Sentence queue on one `<audio>`, autoplay unlock, replay 1×/0.8×, speechSynthesis fallback |
| `src/api.ts` | REST client: due flashcards, review (grade names → SM-2), delete |
| `src/chat/corrections.ts` | Pure helpers: corrections list (newest first), «marked» card fronts |
| `src/components/FeedbackPanel.tsx` | Tabs Corrections / Flashcards (side column ≥ 1024 px, sheet below) |
| `src/components/CorrectionItem.tsx` | One message's grammar and pronunciation feedback |
| `src/components/WordPractice.tsx` | ▶ 1× / 0.8× and 🎙 hold-to-retry for one word, with the verdict |
| `src/components/FlashcardReview.tsx` | Review due cards: flip, grade, delete |
| `src/index.css` | Theme tokens (`@theme`), building blocks (`@utility`), thinking-dots animation |
| `src/theme.ts` | Light (default) / dark theme, remembered per browser |
| `src/components/SettingsMenu.tsx` | ⚙ menu: level, interface language, pronunciation echo, theme, logout |
| `src/components/ThinkingBubble.tsx` | "Transcribing…" / "Thinking…" indicator |
| `src/components/icons.tsx` | Inline line icons |
| `src/components/MicButton.tsx` | Tap = hands-free on/off, hold = push-to-talk |
| `src/components/LoginScreen.tsx` | Token login (language guessed from the browser) |
| `src/components/ChatScreen.tsx` | Chat, mic, replay, editable transcripts, recast switch, panel/sheet, metrics |

## Tests

- Backend (pytest, SQLite + `FakeLlm`, never a real provider): memory invariant over random
  sequences, prompts in both directions, retry/fallback rules, usage and caps, auth, `/me`,
  and end-to-end WebSocket tests (origin, auth, streaming, persistence, summary, level,
  errors, daily cap, provider down, missing configuration).
- CI also applies the migrations to a real Postgres and runs `alembic check`.
- Frontend (vitest): reducer (incl. metrics, interrupted, feedback, unseen badge, edits,
  pron results), corrections helpers, REST client (mocked fetch), frame parser, i18n key parity,
  language detection, sentence assembler, VAD decisions, recorder MIME choice.
- `npm run dev:lan`: HTTPS + proxy for testing on a phone (see `docs/USER_ACTIONS.md`).

## Known limitations

- **STT normalization:** LLM-based STT may "fix" the learner's grammar (seen: "minha amigo" →
  "meu amigo"). The prompt asks for verbatim output; the editable transcript arrives in slice 3.
- **Pronunciation feedback is a qualitative LLM judgment** (no phoneme scores). It can miss
  issues or invent them, even on native audio. Grammar feedback is much more reliable.
- **Volume VAD** can be fooled by loud background noise; push-to-talk always works.
- **iOS:** Google's audio is Ogg/Opus; older iOS versions may not decode it (the sentence is
  skipped). Check on the real phone.
- **Latency** is measured per turn (`metrics`), not promised. Warm local numbers are in
  `docs/DECISIONS.md` (012).

## Not built yet

Feedback track, pronunciation, topics, flashcards, user_facts updates,
responsive layouts, deploy. See SPEC §11.
