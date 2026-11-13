# SPEC — AI Language Partner (pt-BR ⇄ pl-PL)

Source of truth for this project. Every agent reads this file before planning.
If code and this spec disagree, stop and ask the user which one is right.

---

## 1. Product

A voice-and-text conversation partner for exactly two languages: **Brazilian Portuguese (pt-BR)** and **Polish (pl-PL)**.
It is **bidirectional**: each user has a `native_lang` and a `target_lang`.

| Direction | Learner | AI speaks | Explanations (grammar, pronunciation) in |
|---|---|---|---|
| PT→PL | Brazilian learning Polish | pl-PL | pt-BR |
| PL→PT | Pole learning Portuguese | pt-BR | pl-PL |

Both directions are first-class: every feature (prompts, grammar and pronunciation rules, voices, UI strings) must exist for both. **Approved exception (2026-11-13):** conversation topics (§8) exist only for learners of Portuguese, the main learner being a Polish speaker.
The UI language — and the language of every explanation (grammar rules, contrast tips, pronunciation tips) — is `ui_lang`, which defaults to `native_lang` (simple i18n dictionary, two locales: `pt-BR`, `pl-PL`). A learner can change it in the app (`set_ui_lang`); contrast tips still compare with `native_lang`. This also lets a Portuguese speaker try the PL→PT direction while reading everything in Portuguese.

Core experience: **free talk** with a friendly native-speaker AI, adapted to the learner's CEFR level (A1–C1), plus:
- **Topic suggestions** when the learner gets stuck (zero LLM tokens).
- **Async grammar and pronunciation feedback** shown beside the conversation, never interrupting it.
- **Pronunciation recast in the conversation**: the AI naturally echoes a mispronounced word correctly (on by default, can be turned off).
- **Flashcards (SM-2)** generated from the learner's own mistakes.

### Hard constraint: small, predictable monthly cost
Paid services allowed: **Google Gemini API (paid tier)** and **one TTS provider** chosen by benchmark (§6): **Google Cloud Text-to-Speech (Chirp 3 HD)** or **ElevenLabs**. Everything else (hosting, DB, CI) stays on free tiers.
- Monthly budget is configurable (`MONTHLY_BUDGET_USD`, default 15). The backend tracks actual usage (Gemini tokens by type, TTS characters by provider) in Postgres and estimates spend using unit prices from config (`PRICE_*` env vars, never hardcoded).
- Per-user daily caps (LLM calls, STT audio seconds, TTS characters), configurable in `config.py`.
- When the active TTS provider's monthly character allowance (`TTS_MONTHLY_CHARS`, e.g. the free tier or the plan's included characters) reaches 95%, TTS switches automatically to the fallback chain (§6) and the UI shows it. This prevents overage charges. When the monthly USD budget is reached, every Gemini role — conversation, feedback **and STT** — switches to the cheapest configured model (`GEMINI_UTILITY_MODEL`) until the month ends, and the UI warns. Fixed subscriptions (e.g. a TTS plan) are not seen by the app: set `MONTHLY_BUDGET_USD` to the total budget minus them.
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
| LLM | Gemini API, paid tier (`google-genai` SDK) | Roles with separate env vars: `GEMINI_CHAT_MODEL` (conversation), `GEMINI_FEEDBACK_MODEL` (Track 2 grammar + pronunciation JSON and `pron_retry` judgments, §5), `GEMINI_UTILITY_MODEL` (summaries, user_facts; also the chat fallback and the cheapest model once over budget) and `GEMINI_STT_MODEL`. Chat and feedback receive audio on voice turns (§4.1, §5) |
| STT | Gemini audio understanding (`GEMINI_STT_MODEL`) | Single provider. Keep it in its own `stt_service.py` so it stays isolated from the chat logic |
| TTS | Selectable by env `TTS_PROVIDER` = `google` \| `elevenlabs`, each behind the same `TtsProvider` interface. Provisional default: `google` (Chirp 3 HD — its free tier of 1M characters/month covers the expected use). The final choice is made with `tts_bench.py` (§6) | Fallback chain: active provider → `edge-tts` → browser `speechSynthesis`. See §6 |

Model names, voice IDs and prices come ONLY from env/config, never hardcoded. Before choosing defaults, check the providers' current docs and pricing pages; record chosen names, prices and the date checked in `docs/DECISIONS.md`.
The Gemini paid tier is required (not free tier) because free-tier content may be used by Google to improve its products, and these conversations contain personal information.

---

## 3. Users, access and security

- Small number of known users (personal project). No public sign-up.
- `users` table: `id, name, native_lang, target_lang, ui_lang (nullable → native_lang), level, user_facts (≤100 words), voice_id, recast_pronunciation (bool, default true), correct_in_chat (bool, default true), access_token_hash, created_at`.
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

Track 1 reply limits: 1–2 sentences + 1 short question, in `target_lang`.

**Correction in the conversation (default ON, per-user setting `users.correct_in_chat`):**
When the learner's message has a clear mistake, the reply starts by correcting **one** mistake (the most important) — saying the correct form naturally, the way a friendly native would — and then carries on with the conversation in the same reply. At A1/A2 it adds **one short sentence** in the learner's explanation language (`ui_lang`) saying why; from B1 up the correction stays in `target_lang` only. Never more than one correction per reply, no lists, no lecture; the full explanation stays in Track 2 (§5). If the setting is OFF, Track 1 never corrects or explains grammar.

**Pronunciation recast in conversation (default ON, per-user setting `users.recast_pronunciation`):**
For voice turns, Track 1 receives the user's **audio** together with the verbatim transcript (the chat model listens, it does not just read). When the user clearly mispronounces a word, the reply naturally reuses that word pronounced correctly — the way a native friend would echo it — at most once per reply, without saying "you pronounced it wrong" and without any explanation. Explanations belong to Track 2 only. If the setting is OFF, or the turn was typed, Track 1 gets text only and never recasts.

### 4.2 Memory window (fixes the context gap)
- Window = last `WINDOW_TURNS` turns (default 3 turns = 6 messages).
- **Invariant: every message is either inside the window or already folded into `running_summary`.**
- Implementation: when a turn falls out of the window, append it to a `pending_summary` buffer; when the buffer has ≥ `SUMMARY_BATCH_TURNS` turns (default 3), run an async task that merges `running_summary + pending` into a new summary of ≤40 words, then clears the buffer. Until merged, pending turns are still sent to the LLM (so nothing is ever dropped).
- Unit test this invariant explicitly.

### 4.3 user_facts
- ≤100 words, stored in `users.user_facts`, written in the learner's `ui_lang` (the language they read the app in).
- Updated by a background task at session end (WS close) using the session's summary + last turns. Must keep only durable facts (hobbies, job, goals, family context the user mentioned) and stay ≤100 words (enforce by truncation after the LLM call).
- Visible and editable by the user in the UI (desktop left panel / settings sheet on mobile).

---

## 5. Feedback track (Track 2): grammar + pronunciation

Runs asynchronously on each user utterance with ≥3 words, in parallel with Track 1. Uses the feedback model (`GEMINI_FEEDBACK_MODEL`; the utility model once the monthly budget is reached). It is **not** cancelled by barge-in: the learner's message was still said. Results are stored on the message (`messages.feedback`).
For voice turns it receives the **audio and the verbatim transcript** in one call and returns grammar and pronunciation feedback together. For typed turns (or after a `regrade`), it gets text only and returns grammar only.

Response schema (strict JSON, validated with Pydantic; on invalid JSON → ignore silently and log):
```json
{"ok": false,
 "errs": [{"e": "error substring", "c": "corrected form", "r": "short rule in native_lang", "p": "PT⇄PL contrast tip in native_lang"}],
 "pron": [{"w": "word (correct spelling)", "heard": "approximation of what was said", "tip": "practical articulation tip in native_lang", "sev": "major|minor"}]}
```
or exactly `{"ok": true}` when both lists would be empty. Max 3 grammar errors and 3 pronunciation issues, most important first.

Pronunciation rules for the prompt:
- Report only issues that change meaning or clearly mark a foreign accent (`major`), or recurring ones (`minor`). Ignore normal accent and fast-speech reductions. When unsure, do not report.
- Never report pronunciation for words the transcript shows were not said.
- This is a qualitative judgment by an LLM (no phoneme scores). Document it in `docs/ARCHITECTURE.md` as a known limitation and verify it with `stt_eval.py` clips containing deliberate mispronunciations.

Contrastive focus — grammar:
- **PT→PL**: 7 cases (mianownik … wołacz), verbal aspect (dokonany/niedokonany), no articles, gender of past tense, numerals with genitive.
- **PL→PT**: articles (o/a/um/uma), ser vs estar, pretérito perfeito vs imperfeito, subjuntivo, prepositions + contractions (no, na, do, da).

Contrastive focus — pronunciation:
- **PT→PL** (Brazilian speaking Polish): sz / ś / s, cz / ć / c, rz-ż / ź / z, dz-dż-dź, ł (≈ English w, not l), nasal ą / ę (and their denasalization before stops), y vs i, stress on the penultimate syllable, no vowel added after final consonants ("Polski" not "Polsqui"), no vowel reduction.
- **PL→PT** (Pole speaking Portuguese): nasal vowels and diphthongs (ão, õe, ãe, em/im final), open vs closed é/ê and ó/ô, lh and nh, r / rr and the soft r between vowels, final unstressed -e ≈ i and -o ≈ u, t/d before i (tchi, dji), s/z between vowels, word stress (avó vs avô).

### Practice: listen and repeat
- Each pronunciation item in the panel has: ▶ listen (correct word via the user's TTS voice, normal and 0.8× via `playbackRate`; cached per §6), and 🎙 try again.
- "Try again" records only that word/phrase and sends `pron_retry` (§7). The feedback model judges that single attempt against the target word and returns `pron_result` with `better: bool` and a short tip. Recorded in `usage_events` like any other call.

### STT normalization problem
LLM-based speech-to-text (like Gemini) tends to "fix" learners' grammar, hiding mistakes. Mitigations (all required):
- Instruct the STT model to transcribe verbatim, keeping grammatical errors, hesitations and wrong word endings; never correct. Temperature 0, plain text output only.
- Ship `backend/scripts/stt_eval.py`: runs a folder of user-recorded test clips (deliberate errors, both languages) through the STT and the feedback track, printing each transcript and the pronunciation items next to the expected text and the expected mispronunciations, so the user can tune prompts/models empirically.
- Show the transcript in the chat as editable: the user can tap it, fix what was actually said, and re-run the grammar check for that message (`{"type":"regrade", ...}`).
- Text input is always available as an alternative to voice.
- Document this as a known limitation in `docs/ARCHITECTURE.md`.

### Flashcards
- Each error becomes a flashcard automatically; the user can delete it. `flashcards.kind` is `grammar` or `pronunciation`.
  - Grammar card: front = the wrong form in context; back = corrected form + rule.
  - Pronunciation card: front = the word (with ▶ listen); back = tip. Reviewing it offers the same "try again" recording as the panel.
- SM-2 scheduling (`ease`, `interval`, `repetitions`, `due_at`). Pure function, unit-tested. A failed review (grade < 3) brings the card back after 10 minutes, not the next day.
- Table `flashcards (id, user_id, kind, front, back, word, lang, source_message_id, ease, interval_days, repetitions, due_at, created_at)`, unique per `(user_id, kind, front)`. A grammar card's front is the message with the wrong part marked «like this».
- REST (Bearer token, §3): `GET /flashcards?due=true|false&limit=`, `POST /flashcards/{id}/review` `{grade: 0–5}`, `DELETE /flashcards/{id}`. A learner only sees and changes their own cards.

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
- **TTS providers** (`TtsProvider` interface: `synthesize_stream(text, lang, voice_id, speaking_rate) -> async iterator of audio chunks`, plus `name`, `voices(lang)`):
  - `google` — Google Cloud Text-to-Speech, Chirp 3 HD voices, **streaming synthesis** (gRPC `StreamingSynthesize`), auth via service account (`GOOGLE_APPLICATION_CREDENTIALS`). Supports native `speaking_rate` (used for the 0.8× "slow" listen in §5).
  - `elevenlabs` — streaming endpoint, low-latency Flash model (`ELEVENLABS_MODEL`), `language_code` set to the AI's language.
  - Every adapter: one request per buffered sentence, mp3 (or the lowest-latency compressed format the provider offers; record it in `audio_meta.mime`), chunks forwarded to the client as they arrive, 3 s timeout to first byte, `usage_events` row per request.
  - Input-streaming (feeding LLM tokens straight into a provider WebSocket) is a possible later optimization, not part of v1 — record this in `docs/DECISIONS.md`.
- Voices: a curated list per provider and language in config (`GOOGLE_TTS_VOICES_PL/PT`, `ELEVENLABS_VOICES_PL/PT`, as `id:label` pairs, ≥2 per language). The user picks one in settings; stored on `users.voice_id`. If the stored id is not in the active provider's list for that language, use the first voice of the list.
- TTS cache: table `tts_cache (hash, provider, voice_id, model, mime, audio bytea, bytes, last_used_at)`, key = sha256(provider + voice + model + rate + text). Used for topic icebreakers, words in the pronunciation panel and any repeated text. Capped by `TTS_CACHE_MAX_MB` with LRU eviction. Message replay on the client uses the audio it already received (keep blobs per message in memory) — never re-synthesize for replay; replay at 0.8× uses `playbackRate`.
- `backend/scripts/precompute_topic_audio.py` synthesizes all topics for the default voices into the cache (run once by the user; prints the character count and estimated cost before asking for confirmation).
- Fallback chain: if the active provider fails, times out, or `TTS_MONTHLY_CHARS` is at 95% → the optional backup provider `TTS_FALLBACK_PROVIDER` (e.g. `google`, skipped when it has no credentials or is at 95% of `TTS_FALLBACK_MONTHLY_CHARS`) → edge-tts voices from config (`pl-PL-ZofiaNeural`, `pl-PL-MarekNeural`, `pt-BR-FranciscaNeural`, `pt-BR-AntonioNeural`) → if that also fails, send `{"type":"tts_fallback","text":...}` and the client speaks it with `speechSynthesis`.

### TTS benchmark (`backend/scripts/tts_bench.py`)
Purpose: choose the TTS provider with our own data, using only free tiers.
- Corpus `backend/scripts/tts_bench_corpus.json`: 20 sentences in pl-PL and 20 in pt-BR, shaped like real Track 1 replies (1–2 sentences + a question, 60–180 chars, A1 to C1), plus 10 single words from the pronunciation focus lists (§5).
- For each configured provider (skips any without credentials), each language and one voice per language: synthesize every item in streaming mode, `RUNS` times (default 3), with one warm-up request first (connection reuse like in production).
- Measure per request: time to first audio byte (TTFA), total synthesis time, audio duration, characters.
- Report (stdout + `bench_results/<timestamp>/report.md` + `results.csv`): median and P90 TTFA, median total time, per provider × language; characters consumed per provider (to check it stays inside the free tier before running — print the planned total and ask for confirmation).
- Save one audio file per item per provider (`bench_results/<timestamp>/audio/<provider>/<lang>/<id>.mp3`) and an `index.html` that plays the same sentence from each provider side by side, so the user can judge naturalness and pronunciation by ear. Provider names are hidden behind letters (A/B) by default, with the mapping at the bottom, for a blind comparison.
- Run it twice: locally (Brazil) and from the deployed backend region (slice 6), because latency depends on where the backend runs. Results go to `docs/DECISIONS.md`.
- `bench_results/` is git-ignored.
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
| `start_of_speech` | `mime`, `purpose` (`utterance` \| `pron_retry`), `target_word` (only for `pron_retry`), `message_id` (only for `pron_retry`) |
| *(binary)* | full utterance audio |
| `end_of_speech` | — |
| `user_text` | `text` |
| `user_started_speaking` | — |
| `suggest_topic` | — |
| `set_theme` | `theme` (free text, ≤40 chars; empty clears it) |
| `set_facts` | `text` (≤100 words) — the learner's edited `user_facts` (§4.3) |
| `set_level` | `level` (A1…C1) |
| `regrade` | `message_id`, `text` (grammar only — no audio) |
| `set_recast` | `enabled` (bool) — pronunciation recast in Track 1 (§4.1) |
| `set_ui_lang` | `ui_lang` (`pt-BR` \| `pl-PL`) — interface and explanation language (§1) |
| `set_correction` | `enabled` (bool) — correction in the conversation (§4.1) |
| `speak_word` | `word` — returns cached TTS audio for the panel's ▶ button |

Server → client:
| type | payload |
|---|---|
| `ready` | `user` (name, `native_lang`, `target_lang`, `ui_lang`, level, voice, `recast_pronunciation`, `correct_in_chat`, `user_facts`), `session_id` |
| `user_updated` | `user` (same shape as in `ready`) — after `set_level` or other settings changes |
| `transcript` | `message_id`, `text` |
| `ai_text_delta` | `message_id`, `delta` |
| `ai_text_done` | `message_id`, `text` |
| *(binary)* | audio chunk, always preceded by exactly one `audio_meta` (for `speak_word`, `message_id` = `word:<word>`) |
| `audio_meta` | `message_id`, `seq` (chunk counter per message), `sentence` (0-based index of the sentence in the reply), `mime`, `final` (true on the last chunk of that sentence — the client plays a sentence once it is complete) |
| `tts_fallback` | `message_id`, `sentence`, `text`, `lang` — the browser speaks this sentence with `speechSynthesis`, in sentence order |
| `feedback` | `message_id` (the learner's message), `source` (`audio` \| `text`), `ok`, `errs`, `pron` — per §5; `pron` is empty for `text` |
| `pron_result` | `message_id`, `word`, `better` (bool), `tip` |
| `topic` | `message_id`, `text` — an AI message with no LLM call; its audio follows as usual (`audio_meta` + binary or `tts_fallback`) |
| `interrupted` | `message_id` |
| `metrics` | `message_id`, `stt_ms` (null for typed turns), `llm_first_token_ms`, `first_audio_ms` (null if no server audio), `total_ms` — measured from `end_of_speech` / `user_text` (§6) |
| `usage` | `month_usd_est`, `budget_usd`, `tts_chars_month`, `tts_chars_allowance`, `tts_provider_active` (the provider that will actually speak), `llm_calls_today`, `llm_calls_cap`, `stt_seconds_today`, `stt_seconds_cap`, `tts_chars_today`, `tts_chars_cap` (caps: 0 = no cap) |
| `error` | `code` (`quota_exceeded`, `provider_unavailable`, `stt_failed`, `bad_request`), `message` (in native_lang) |

Define these as Pydantic models (backend) and TypeScript types (frontend) generated or mirrored in `frontend/src/protocol.ts`.

---

## 8. Topics (zero tokens)

- `backend/app/data/topics.json`: icebreaker questions for learners of **pt-BR only** (approved exception, §1): ≥25 per level (A1…C1) → ≥125. Each item: `id, lang, level, theme, text`. For learners of Polish, `suggest_topic` answers with an `error` (`bad_request`) and the UI hides the button.
- Written by a native-quality standard; the agent must flag in its report that a native speaker should review them.
- `suggest_topic` picks an unused (this session) topic matching the user's target language and level, adds it to history as an AI message, synthesizes it via TTS. No LLM call.
- `set_theme` adds a one-line steering note to the prompt (after the level block) until changed.

---

## 9. UI

Responsive PWA, `h-[100dvh]`, light/dark.
- **Phone (<768px)**: top bar (direction badge, level pill, quota pill), transcript in the center (48px touch targets: replay audio, 0.8× speed, blur text), bottom dock with mic button (tap = auto-VAD toggle, hold = push-to-talk, `touch-action: none`) and "💡 Puxar assunto / 💡 Podsuń temat", bottom sheet with tabs Correções/Flashcards (UI strings localized: pt-BR and pl-PL) and a badge when new errors arrive. Corrections list shows grammar and pronunciation items, each pronunciation item with ▶ listen and 🎙 try again (§5).
- **Tablet (768–1024px)**: 60/40 split — conversation | grammar + flashcards.
- **Desktop (>1024px)**: 3 columns — profile/facts/level/theme | conversation | grammar + metrics HUD.
- Usage HUD shows: estimated spend this month vs budget, TTS characters used vs allowance (active provider), which TTS provider is active, today's usage vs daily caps, last-turn timings. Values are estimates from configured prices — label them as such.
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
| 2 | Voice: Gemini STT + `stt_eval.py`, sentence buffer, TTS adapters (Google Chirp 3 HD, ElevenLabs) + `tts_bench.py` + fallback chain + cache, usage tracking, audio hooks, VAD/PTT, barge-in, metrics | Voice conversation works on desktop Chrome and on a phone over LAN/HTTPS tunnel; each provider can be selected by env; forcing the active provider to fail falls back cleanly (tested); benchmark report produced |
| 3 | Feedback track (grammar + pronunciation from audio), pronunciation recast in Track 1 + setting, listen-and-repeat (`speak_word`, `pron_retry`), editable transcript + regrade, flashcards (grammar + pronunciation) + SM-2, review UI | Both kinds of feedback show in panel for both directions; recast can be toggled; cards reviewable; SM-2 and schema-validation tests pass |
| 4 | Topics JSON (≥150), suggest_topic, theme, user_facts update + edit UI, `precompute_topic_audio.py` | Suggest works with 0 LLM calls and 0 new TTS characters when cached (asserted in test) |
| 5 | Responsive shell (phone/tablet/desktop), bottom sheet, PWA manifest, quota/metrics HUD, polish | Manual checklist in docs passes on 3 viewport sizes |
| 6 | Deploy: Vercel + Render + Supabase, docs/DEPLOYMENT.md, USER_ACTIONS.md complete | App reachable over HTTPS; second user can log in |
