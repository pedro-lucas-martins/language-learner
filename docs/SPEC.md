# SPEC — AI Language Partner (pt-BR ⇄ pl-PL)

Source of truth for this project. Every agent reads this file before planning.
If code and this spec disagree, stop and ask the user which one is right.

---

## 1. Product

A voice-and-text conversation partner for exactly two languages: **Brazilian Portuguese (pt-BR)** and **Polish (pl-PL)**.
It is **bidirectional**: each user has a `native_lang` and a `target_lang`.

| Direction | Learner | AI speaks | Grammar explanations in |
|---|---|---|---|
| PT→PL | Brazilian learning Polish | pl-PL | pt-BR |
| PL→PT | Pole learning Portuguese | pt-BR | pl-PL |

Both directions are first-class: every feature (prompts, topics, grammar rules, voices, UI strings) must exist for both.
The UI language follows `native_lang` (simple i18n dictionary, two locales: `pt-BR`, `pl-PL`).

Core experience: **free talk** with a friendly native-speaker AI, adapted to the learner's CEFR level (A1–C1), plus:
- **Topic suggestions** when the learner gets stuck (zero LLM tokens).
- **Async grammar feedback** shown beside the conversation, never interrupting it.
- **Flashcards (SM-2)** generated from the learner's own mistakes.

### Hard constraint: small, predictable monthly cost
Paid services allowed: **Google Gemini API (paid tier)** and **ElevenLabs (subscription plan)**. Everything else (hosting, DB, CI) stays on free tiers.
- Monthly budget is configurable (`MONTHLY_BUDGET_USD`, default 15). The backend tracks actual usage (Gemini tokens by type, ElevenLabs characters) in Postgres and estimates spend using unit prices from config (`PRICE_*` env vars, never hardcoded).
- Per-user daily caps (LLM calls, STT audio seconds, TTS characters), configurable in `config.py`.
- When the ElevenLabs monthly character allowance (`ELEVENLABS_MONTHLY_CHARS`) reaches 95%, TTS switches automatically to the free fallback chain (§6) and the UI shows it. When the monthly USD budget is reached, the LLM switches to the cheapest configured model and the UI warns.
- Every external call must handle HTTP 429 / quota / 5xx errors gracefully (one retry with backoff, then a typed `error` event or fallback). Never crash the WebSocket.
- No other paid service may be added without the user's explicit approval.

---

## 2. Stack

| Layer | Choice | Notes |
|---|---|---|
| Frontend | React + Vite + TypeScript + Tailwind | Hosted on Vercel Hobby (free) |
| Backend | Python 3.11+, FastAPI, WebSockets | Container on a free PaaS (Render free tier by default) |
| DB | PostgreSQL — Supabase free in prod, Docker locally | SQLAlchemy 2.0 async + Alembic migrations |
| Session state | In-process memory per WebSocket + persisted to Postgres | **No Redis.** Single backend instance is assumed |
| LLM | Gemini API, paid tier (`google-genai` SDK) | Two roles with separate env vars: `GEMINI_CHAT_MODEL` (conversation — stronger Flash-tier) and `GEMINI_UTILITY_MODEL` (grammar JSON, summaries, user_facts — Flash-Lite tier) |
| STT | Gemini audio understanding (`GEMINI_STT_MODEL`) | Single provider. Keep it in its own `stt_service.py` so it stays isolated from the chat logic |
| TTS | ElevenLabs streaming TTS (`ELEVENLABS_MODEL`, default a low-latency Flash model), behind a `TtsProvider` interface | Fallback chain: ElevenLabs → `edge-tts` → browser `speechSynthesis`. See §6 |

Model names, voice IDs and prices come ONLY from env/config, never hardcoded. Before choosing defaults, check the providers' current docs and pricing pages; record chosen names, prices and the date checked in `docs/DECISIONS.md`.
The Gemini paid tier is required (not free tier) because free-tier content may be used by Google to improve its products, and these conversations contain personal information.

---

## 3. Users, access and security

- Small number of known users (personal project). No public sign-up.
- `users` table: `id, name, native_lang, target_lang, level, user_facts (≤100 words), voice_id, access_token_hash, created_at`.
- `usage_events` table: `user_id, kind (llm_in|llm_out|stt_audio_s|tts_chars), model, amount, created_at` — the single source for daily caps, monthly spend estimate and the usage HUD.
- A CLI script `backend/scripts/create_user.py` creates a user and prints a random access token once (store only the hash).
- Frontend: a login screen asking for the token; stored in `localStorage` (wrapped in try/catch).
- Every REST route and the WebSocket require the token (`Authorization: Bearer` for REST; first WS message `{"type":"auth","token":"..."}`, close with code 4401 if invalid within 5 s).
- **WebSocket Origin check is manual** (CORS middleware does not apply to WS): accept only `FRONTEND_URL`, `http://localhost:5173` (only when `APP_ENV=development`), and the project's own Vercel preview pattern from env `VERCEL_PREVIEW_REGEX` (e.g. `^https://language-learner(-[a-z0-9-]+)?\.vercel\.app$`). Never `.*\.vercel\.app`.
- REST CORS uses the same allowlist.
- Rate limit: per-user daily counters (LLM calls, STT seconds, TTS characters) stored in Postgres; reject with a typed error event when exceeded. This protects the paid API keys, not just quotas.
- Secrets only via env. `.env` is in `.gitignore` before the first commit.

---

## 4. Conversation engine

### 4.1 Prompt layout (order matters)
1. Static block: persona + pedagogy + direction-specific contrast notes (identical bytes for all users of the same direction).
2. Level block (A1/A2, B1/B2, C1 rules below).
3. `user_facts`.
4. `running_summary`.
5. Last N messages (window).

Put stable content first (helps any provider-side caching), but **do not claim or compute caching savings** anywhere.

Level rules:
- **A1/A2**: high-frequency vocabulary, present/simple past, sentences ≤12 words, end with one simple question.
- **B1/B2**: natural everyday speech, some idioms, open questions.
- **C1**: native register, idioms, slang, debate-style questions.

Track 1 reply limits: 1–2 sentences + 1 short question, in `target_lang` only. Never explain grammar in Track 1.

### 4.2 Memory window (fixes the context gap)
- Window = last `WINDOW_TURNS` turns (default 3 turns = 6 messages).
- **Invariant: every message is either inside the window or already folded into `running_summary`.**
- Implementation: when a turn falls out of the window, append it to a `pending_summary` buffer; when the buffer has ≥ `SUMMARY_BATCH_TURNS` turns (default 3), run an async task that merges `running_summary + pending` into a new summary of ≤40 words, then clears the buffer. Until merged, pending turns are still sent to the LLM (so nothing is ever dropped).
- Unit test this invariant explicitly.

### 4.3 user_facts
- ≤100 words, stored in `users.user_facts`, written in `native_lang`.
- Updated by a background task at session end (WS close) using the session's summary + last turns. Must keep only durable facts (hobbies, job, goals, family context the user mentioned) and stay ≤100 words (enforce by truncation after the LLM call).
- Visible and editable by the user in the UI (desktop left panel / settings sheet on mobile).

---

## 5. Grammar track (Track 2)

Runs asynchronously on each user utterance with ≥3 words, in parallel with Track 1. Uses the cheap model.

Response schema (strict JSON, validated with Pydantic; on invalid JSON → ignore silently and log):
```json
{"ok": false, "errs": [{"e": "error substring", "c": "corrected form", "r": "short rule in native_lang", "p": "PT⇄PL contrast tip in native_lang"}]}
```
or exactly `{"ok": true}`. Max 3 errors per utterance, most important first.

Contrastive focus:
- **PT→PL**: 7 cases (mianownik … wołacz), verbal aspect (dokonany/niedokonany), no articles, gender of past tense, numerals with genitive.
- **PL→PT**: articles (o/a/um/uma), ser vs estar, pretérito perfeito vs imperfeito, subjuntivo, prepositions + contractions (no, na, do, da).

### STT normalization problem
LLM-based speech-to-text (like Gemini) tends to "fix" learners' grammar, hiding mistakes. Mitigations (all required):
- Instruct the STT model to transcribe verbatim, keeping grammatical errors, hesitations and wrong word endings; never correct. Temperature 0, plain text output only.
- Ship `backend/scripts/stt_eval.py`: runs a folder of user-recorded test clips (deliberate errors, both languages) through the STT and prints each transcript next to the expected text, so the user can tune the STT prompt/model empirically.
- Show the transcript in the chat as editable: the user can tap it, fix what was actually said, and re-run the grammar check for that message (`{"type":"regrade", ...}`).
- Text input is always available as an alternative to voice.
- Document this as a known limitation in `docs/ARCHITECTURE.md`.

### Flashcards
- Each grammar error can become a flashcard (front: the wrong form in context; back: corrected form + rule). Auto-create on error; user can delete.
- SM-2 scheduling (`ease`, `interval`, `repetitions`, `due_at`). Pure function, unit-tested.

---

## 6. Voice pipeline

```
mic → (client VAD / push-to-talk) → audio blob over WS → STT → LLM stream
   → sentence buffer → TTS per sentence → audio chunks → client queue
```

- Client sends the full utterance as one binary message (MediaRecorder chunks concatenated client-side) followed by `{"type":"end_of_speech"}`. Do not assume partial WebM chunks are decodable on their own.
- MediaRecorder MIME: try `audio/webm;codecs=opus`, then `audio/mp4`, then `audio/aac`. Send the MIME in the `start_of_speech` event.
- `getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}})`.
- **While AI audio is playing, auto-VAD is paused** (prevents the app hearing itself on phone speakers). Push-to-talk still works and triggers barge-in.
- Sentence buffer: flush on `. ! ? …` or `\n` when buffer ≥15 chars; do not split on decimals (`3.5`), common abbreviations, or ordinal dots in Polish dates (`11.11.`). Unit-tested with both languages.
- TTS primary: ElevenLabs streaming endpoint, one request per buffered sentence, output format `mp3_44100_64` (or the lowest-latency mp3 format available), `language_code` set to the AI's language. Stream the returned audio chunks to the client as they arrive. Record in `docs/DECISIONS.md` that input-streaming over the ElevenLabs WebSocket (feeding LLM tokens directly) is a possible later optimization, not part of v1.
- Voices: a curated list in config, ≥2 voices per AI language (`ELEVENLABS_VOICES_PL`, `ELEVENLABS_VOICES_PT`, as `id:label` pairs). The user picks one in settings; stored on `users.voice_id`.
- TTS cache: table `tts_cache (hash, voice_id, model, mime, audio bytea, bytes, last_used_at)`, key = sha256(text + voice + model). Used for topic icebreakers and any repeated text. Capped by `TTS_CACHE_MAX_MB` with LRU eviction. Message replay on the client uses the audio it already received (keep blobs per message in memory) — never re-synthesize for replay or 0.8× speed (use `playbackRate`).
- `backend/scripts/precompute_topic_audio.py` synthesizes all topics for the default voices into the cache (run once by the user; prints the character count and estimated cost before asking for confirmation).
- Fallback chain: if ElevenLabs fails, times out (3 s to first byte), or the monthly allowance is at 95% → edge-tts voices from config (`pl-PL-ZofiaNeural`, `pl-PL-MarekNeural`, `pt-BR-FranciscaNeural`, `pt-BR-AntonioNeural`) → if that also fails, send `{"type":"tts_fallback","text":...}` and the client speaks it with `speechSynthesis`.
- Barge-in: `{"type":"user_started_speaking"}` cancels the LLM task and TTS tasks for the current turn; server replies `{"type":"interrupted"}`; client clears its audio queue.
- **Latency is measured, not promised**: record per-turn timings (stt_ms, llm_first_token_ms, first_audio_ms, total_ms) and send them in a `metrics` event. No hard latency target in code or docs; report observed medians.
- `unlockAudioContext()` on first user tap (iOS/Android autoplay rules). Audio elements use `playsInline`.

---

## 7. WebSocket protocol (contract — change only by editing this section first)

All JSON messages have a `type` field. Binary frames are audio only.

Client → server:
| type | payload |
|---|---|
| `auth` | `token` |
| `start_of_speech` | `mime` |
| *(binary)* | full utterance audio |
| `end_of_speech` | — |
| `user_text` | `text` |
| `user_started_speaking` | — |
| `suggest_topic` | — |
| `set_theme` | `theme` (free text, ≤40 chars) |
| `set_level` | `level` (A1…C1) |
| `regrade` | `message_id`, `text` |

Server → client:
| type | payload |
|---|---|
| `ready` | `user` (name, langs, level), `session_id` |
| `transcript` | `message_id`, `text` |
| `ai_text_delta` | `message_id`, `delta` |
| `ai_text_done` | `message_id`, `text` |
| *(binary)* | audio chunk, preceded by `audio_meta` |
| `audio_meta` | `message_id`, `seq`, `mime` |
| `tts_fallback` | `message_id`, `text`, `lang` |
| `grammar` | `message_id`, result per §5 |
| `topic` | `message_id`, `text` |
| `interrupted` | `message_id` |
| `metrics` | timings per §6 |
| `usage` | `month_usd_est`, `budget_usd`, `tts_chars_month`, `tts_chars_allowance`, `tts_provider_active` |
| `error` | `code` (`quota_exceeded`, `provider_unavailable`, `stt_failed`, `bad_request`), `message` (in native_lang) |

Define these as Pydantic models (backend) and TypeScript types (frontend) generated or mirrored in `frontend/src/protocol.ts`.

---

## 8. Topics (zero tokens)

- `backend/app/data/topics.json`: for **each** target language (pl-PL, pt-BR) × **each** level (A1…C1): ≥15 icebreaker questions → ≥150 total. Each item: `id, lang, level, theme, text`.
- Written by a native-quality standard; the agent must flag in its report that a native speaker should review them.
- `suggest_topic` picks an unused (this session) topic matching the user's target language and level, adds it to history as an AI message, synthesizes it via TTS. No LLM call.
- `set_theme` adds a one-line steering note to the prompt (after the level block) until changed.

---

## 9. UI

Responsive PWA, `h-[100dvh]`, light/dark.
- **Phone (<768px)**: top bar (direction badge, level pill, quota pill), transcript in the center (48px touch targets: replay audio, 0.8× speed, blur text), bottom dock with mic button (tap = auto-VAD toggle, hold = push-to-talk, `touch-action: none`) and "💡 Puxar assunto / 💡 Podsuń temat", bottom sheet with tabs Gramática/Flashcards and a badge when new errors arrive.
- **Tablet (768–1024px)**: 60/40 split — conversation | grammar + flashcards.
- **Desktop (>1024px)**: 3 columns — profile/facts/level/theme | conversation | grammar + metrics HUD.
- Usage HUD shows: estimated spend this month vs budget, ElevenLabs characters used vs allowance, which TTS provider is active, today's usage vs daily caps, last-turn timings. Values are estimates from configured prices — label them as such.
- `manifest.json` + icons. Service worker not required.

---

## 10. Repository layout

```
/
├── .agents/rules/          # agent rules (do not delete)
├── .agents/workflows/      # agent workflows
├── docs/ SPEC.md ARCHITECTURE.md DEPLOYMENT.md USER_ACTIONS.md DECISIONS.md
├── docker-compose.yml      # postgres + backend + frontend for local dev
├── .env.example  .gitignore  README.md
├── .github/workflows/ci.yml   # backend pytest + frontend typecheck/build (free on GitHub)
├── backend/  Dockerfile render.yaml pyproject.toml|requirements.txt alembic/ scripts/ tests/
│   └── app/ main.py config.py database.py protocol.py models/ services/ routers/ data/topics.json
└── frontend/ vercel.json public/manifest.json src/ (protocol.ts, i18n/, hooks/, components/)
```

---

## 11. Slices (build order)

Each slice must end runnable and tested. Never start the next slice with the current one broken.

| # | Slice | Done when |
|---|---|---|
| 0 | Scaffold, git, docs skeleton, docker-compose (Postgres), CI, health endpoint, empty Vite app | `docker compose up` works; CI green |
| 1 | Users + token auth, WS protocol (text only), LLM provider abstraction + fallback, memory window + summary, persistence, minimal text chat UI, i18n both locales | Text conversation works locally in both directions; memory invariant tests pass |
| 2 | Voice: Gemini STT + `stt_eval.py`, sentence buffer, ElevenLabs TTS + fallback chain + cache, usage tracking, audio hooks, VAD/PTT, barge-in, metrics | Voice conversation works on desktop Chrome and on a phone over LAN/HTTPS tunnel; forcing ElevenLabs to fail falls back cleanly (tested) |
| 3 | Grammar track, editable transcript + regrade, flashcards + SM-2, review UI | Errors show in panel; cards reviewable; SM-2 tests pass |
| 4 | Topics JSON (≥150), suggest_topic, theme, user_facts update + edit UI, `precompute_topic_audio.py` | Suggest works with 0 LLM calls and 0 new TTS characters when cached (asserted in test) |
| 5 | Responsive shell (phone/tablet/desktop), bottom sheet, PWA manifest, quota/metrics HUD, polish | Manual checklist in docs passes on 3 viewport sizes |
| 6 | Deploy: Vercel + Render + Supabase, docs/DEPLOYMENT.md, USER_ACTIONS.md complete | App reachable over HTTPS; second user can log in |
