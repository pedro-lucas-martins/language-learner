# Decisions (ADR log)

Short records: context → decision → consequence. Newest at the bottom.

## 001 — Python/FastAPI backend instead of NestJS (2026-11-10)
- **Context:** the author's main stack is NestJS/TypeScript, but this project depends on audio and AI SDKs (Gemini, ElevenLabs, edge-tts).
- **Decision:** FastAPI backend; frontend stays React/TypeScript.
- **Consequence:** two languages in the repo; WebSocket protocol types are mirrored manually between `app/protocol.py` and `frontend/src/protocol.ts` (SPEC §7).

## 002 — No Redis (2026-11-10)
- **Context:** a single backend instance serves a handful of users.
- **Decision:** session state lives in process memory per WebSocket and is persisted to Postgres.
- **Consequence:** the backend must not be scaled horizontally without revisiting this.

## 003 — Paid AI providers: Gemini (paid tier) + ElevenLabs (2026-11-10)
- **Context:** free tiers were considered; the author accepts a small monthly cost for better voices and privacy.
- **Decision:** Gemini paid tier for chat, grammar, summaries and STT (free-tier content may be used by Google to improve its products); ElevenLabs for TTS with an edge-tts → browser fallback chain. Whisper/Groq dropped.
- **Consequence:** every paid call is recorded in `usage_events`; budget and caps are enforced in the backend (SPEC §1, §3). Model names and prices are set in `.env` — record the chosen values and the date checked below when they are filled in.

## 004 — localhost origin only in development (2026-11-10)
- **Context:** SPEC listed `http://localhost:5173` as always allowed.
- **Decision:** allow it only when `APP_ENV=development`.
- **Consequence:** production accepts only the real frontend and its own Vercel previews. SPEC §3 updated.

## 005 — Pronunciation feedback with Gemini only, recast on by default (2026-11-10)
- **Context:** the author wants pronunciation corrected during the conversation. Azure Pronunciation Assessment supports pl-PL and pt-BR, but phoneme names and prosody are en-US only, and at ~26 h of learner audio per month (2 people × 2 h/day) it would add ~US$ 26–35/month.
- **Decision:** no Azure. Gemini receives the learner's audio in both tracks: Track 1 recasts a clearly mispronounced word naturally in its reply (setting, default ON); Track 2 returns explicit pronunciation items with tips, plus a listen-and-repeat drill.
- **Consequence:** pronunciation feedback is qualitative (no phoneme scores) and can miss or invent issues; mitigated by "report only when sure" prompting and `stt_eval.py` clips with deliberate mispronunciations. Extra cost is small (audio tokens on the chat call). Estimated total for 1 learner × 2 h/day: ~US$ 28–35/month (see the conversation estimate of 2026-11-10; recheck prices before relying on it).

## 006 — TTS provider chosen by our own benchmark (2026-11-10)
- **Context:** ElevenLabs Creator (~US$ 22/month for 1 learner × 2 h/day) was the cost driver. Google Cloud TTS Chirp 3 HD supports pl-PL and pt-BR with streaming, and its free tier (1M characters/month) covers the expected use, but a third-party benchmark (Coval, measured from us-east-1, language unknown) puts its time-to-first-audio at ~530 ms median vs ~200 ms for ElevenLabs Flash v2.5 and ~280 ms for Cartesia Sonic 3.6. No public data covers Polish/Portuguese or our backend region.
- **Decision:** three TTS adapters behind one interface (`TTS_PROVIDER` = `google` | `elevenlabs` | `cartesia`), provisional default `google`. `tts_bench.py` (SPEC §6) measures TTFA and saves blind A/B/C audio samples in both languages, using only free tiers. The provider is chosen from those results. edge-tts and the browser voice remain the fallback chain. Supersedes the ElevenLabs-only part of 003.
- **Consequence:** more adapter code in slice 2; `TTS_MONTHLY_CHARS` generalizes the per-provider allowance. Benchmark results (local and from the deployed region) are recorded below.

## 007 — Slice 1 implementation choices (2026-11-10)
- **Tokens:** 32 random bytes, stored as SHA-256 (no slow hash needed for full-entropy tokens). Created only by `scripts/create_user.py`; shown once.
- **Protocol:** added `user_updated` (server → client) so `set_level` has an explicit confirmation. SPEC §7 updated.
- **LLM fallback:** `GEMINI_CHAT_MODEL` → `GEMINI_UTILITY_MODEL`, one retry each for 429/5xx/timeouts; no retry after text was streamed. Over budget → utility model only.
- **Speed knob:** optional `GEMINI_THINKING_LEVEL` (empty = model default).
- **Tests:** SQLite + `FakeLlm` for speed and isolation; CI additionally applies the migrations to Postgres 16 and runs `alembic check`.

## 008 — Flash-Lite models for chat and utility (2026-11-12)
- **Context:** `gemini-3.8-flash` costs US$ 0.75/3.75 per 1M and doubles on 2027-01-01; the monthly budget is US$ 15.
- **Decision:** chat on `gemini-3.5-flash-lite` (stable price, single input rate incl. audio for slice 2); utility/fallback on `gemini-3.1-flash-lite`, a different model so the fallback still works when the chat model fails.
- **Consequence:** lower reply quality than Flash; revisit if corrections or Polish fluency feel weak. `GEMINI_THINKING_LEVEL` left empty until we confirm these models accept it.

## 009 — Cartesia dropped from the TTS benchmark (2026-11-12)
- **Context:** the author decided not to evaluate Cartesia.
- **Decision:** two TTS adapters only: `TTS_PROVIDER` = `google` | `elevenlabs`; the benchmark compares them blind as A/B. Amends 006.
- **Consequence:** less adapter code and one fewer account; Cartesia can be re-added later behind the same `TtsProvider` interface.

## 010 — Slice 2a: TTS adapters, formats and voices (2026-11-12)
- **Google audio format:** `StreamingSynthesize` rejects MP3 ("Unsupported audio encoding", tested 2026-11-12), so the Google adapter streams **OGG_OPUS** (`audio/ogg;codecs=opus`). ElevenLabs and edge-tts send MP3. The client must play both.
- **ElevenLabs on the Free plan cannot use Voice Library voices through the API** (HTTP 402 `paid_plan_required`). The benchmark uses premade multilingual voices (Sarah, George) with `language_code` set; native Polish/Brazilian voices need a paid plan.
- **Fallback:** the chain only switches provider before the first audio byte; a failure mid-sentence stops that sentence instead of repeating it with another voice. The fallback keeps the voice's position in the list (female → female when lists are ordered alike).
- **Usage:** one `tts_chars` row per request, written on the first audio byte (what providers bill). edge-tts rows use role `edge`, cost 0 and do not count toward the daily cap. Over 95% of `TTS_MONTHLY_CHARS` **or** the daily cap → free fallback.
- **Input streaming** (feeding LLM tokens into a provider WebSocket) is left for later, per SPEC §6: one request per sentence in v1.
- **Consequence:** the 3 s first-byte timeout can trip on a cold connection right after startup (the first sentence then uses edge-tts).

## 011 — Google Chirp 3 HD chosen as the TTS provider (2026-11-12)
- **Context:** local benchmark (run 1 below): ElevenLabs Flash v2.5 is ~3× faster (TTFA p50 ~280 ms vs ~400 ms; p90 ~0.3 s vs ~1.3 s; full sentence ~0.37 s vs ~1.2 s). But its Free plan (~10k credits/month) was almost used up by the benchmark alone and does not allow native library voices through the API; daily use would need a paid plan. In the blind listening test the author preferred Google (Kore).
- **Decision:** `TTS_PROVIDER=google` on the free tier. ElevenLabs stays as a selectable adapter.
- **Consequence:** zero TTS cost within 1M characters/month; with sentence-by-sentence playback the first sentence starts ~1 s after its text is ready (more at p90). Re-run the benchmark from the deployed region in slice 6.

## 012 — Slice 2b: voice turn on the backend (2026-11-12)
- **Playback unit = sentence.** `audio_meta` gains `sentence` and `final`; the server holds back one chunk so the last chunk of each sentence carries `final=true`. `tts_fallback` gains `sentence` so the browser keeps the order. SPEC §7 updated.
- **Typed turns are spoken too**, through the same TTS path.
- **Barge-in:** every turn is an `asyncio` task. `user_started_speaking`, a new utterance or a new typed message cancels it (LLM and TTS) and the server sends `interrupted`. The text produced so far is kept in the history (persisted and added to the memory window), since the learner saw it.
- **STT:** `gemini-3.5-flash-lite`, verbatim prompt, temperature 0, inline audio, MIME without codec parameters. Audio seconds come from Gemini's audio token count (32/s); before the call a size estimate enforces `DAILY_STT_SECONDS_PER_USER`. STT tokens are priced with `PRICE_STT_AUDIO_INPUT_PER_M` (input) and the utility output price.
- **First check (2026-11-12, synthetic clips with deliberate errors):** errors kept ("dwa kot", "jedna pies", "eu gosta", "de a praia"), but "minha amigo" came back as "meu amigo" — the normalization problem from SPEC §5 is real; the editable transcript (slice 3) remains necessary.
- **Observed latency, warm, local Docker, Polish ~5 s utterance:** STT ~1.6–2.1 s, first LLM token ~2.6–3.0 s, first audio ~3.5–3.6 s, total ~4.6–5.6 s after `end_of_speech`. First turn after startup ~5.9 s. Not a target, just a measurement.
- **`DEV_EXTRA_ORIGINS`:** exact extra origins accepted only in development, for the HTTPS LAN address used to test on a phone (slice 2c).
- **Utterance size:** one binary message of at most 2 MB.

## 013 — Slice 2c: voice in the browser (2026-11-12)
- **Playback:** one reused `<audio>` element, unlocked with a silent WAV on the first tap/key (iOS/Android autoplay). Sentences are played in arrival order, which is sentence order because the server synthesizes them sequentially. Received audio is kept per message (last 40) for ▶ and 0.8× replay (`playbackRate`); `tts_fallback` sentences use `speechSynthesis`. An undecodable sentence is skipped.
- **VAD by volume** (user's choice): RMS every 40 ms; threshold = max(0.015, 3 × noise floor). The first 500 ms calibrate the noise floor; while recording it adapts very slowly, so a hum that starts mid-utterance ends it after ~15 s instead of 30. Recording starts on the first loud block (keeps the first syllable); < 250 ms of loud audio is discarded; 900 ms of silence ends the utterance. Paused while the AI speaks and for 400 ms after.
- **Mic button:** a press shorter than 300 ms toggles hands-free mode, a longer press is push-to-talk. Any press interrupts the AI (barge-in): the client stops playback at once and drops late frames of that reply.
- **Phone testing:** `npm run dev:lan` serves HTTPS with a self-signed certificate (`@vitejs/plugin-basic-ssl`) and proxies `/ws`, `/me`, `/health` to the backend, so the page and the API share one origin. The LAN origin must be in `DEV_EXTRA_ORIGINS`.
- **Observed in the browser (desktop Chrome engine, local):** typed turn, warm: first voice 2.6 s, total 4.6 s; first turn after a restart 7.9 s.

## 014 — Slice 3a: Track 2 feedback on the backend (2026-11-12)
- **Own model variable:** `GEMINI_FEEDBACK_MODEL` (`gemini-3.5-flash-lite`, chosen by the author) for Track 2 and `pron_retry`; the utility model keeps summaries and is used for feedback once over budget. Usage rows use role `feedback` with `PRICE_FEEDBACK_*`. SPEC §2/§5 updated.
- **Structured output:** the call sends `response_json_schema`. Without it the model once returned malformed JSON (an extra `]`) and the correction was lost. Pydantic still validates every item.
- **Explanation language:** the prompt states twice that `r`, `p` and `tip` are in the native language, with a style example in that language. Without this the rule once came back in English.
- **Anti-hallucination filters:** a grammar item whose `e` is not in the message, or whose correction equals the original, is dropped; a pronunciation item for a word not in the transcript, or "heard" exactly as written, is dropped. Max 3 + 3.
- **Track 2 is not cancelled by barge-in** and is stored on `messages.feedback`. Regrade only for the learner's own messages of the current session.
- **Recast:** voice turns with the setting on send the audio to the chat model plus a recast rule; typed turns never do.
- **Real check (2026-11-12, synthetic clips):** grammar correct in both directions (PT→PL: dwa koty, jeden pies, do sklepu — explained in Portuguese; PL→PT: gosto, da praia, fui — explained in Polish). **Pronunciation is unreliable**: on a native TTS voice the model still invented issues (e.g. an "ł" tip for "sklep"). Known limitation; tune with real clips via `stt_eval.py`, consider a stronger model for pronunciation later.
- **Test fix found here:** ending a read-only DB session without committing kept SQLite locked for seconds on WebSocket close; regrade now always ends its transaction.

## 015 — Slice 3b: flashcards, listen and repeat (2026-11-12)
- **Flashcards over REST**, not the WebSocket: they are reviewed outside a conversation and fit plain request/response. Same Bearer auth as `/me`; a learner only reaches their own cards (404 otherwise). SPEC §5 updated with the table and routes.
- **SM-2 with a short relearn step:** a failed card (grade < 3) is due again in 10 minutes instead of tomorrow. UI buttons map to grades 1/3/4/5.
- **Cards are created from every non-ok feedback**, deduplicated by `(user, kind, front)`; the grammar front marks the mistake in context with «».
- **`speak_word`** goes through the normal TTS chain and cache: repeating a word costs nothing (verified: one `tts_chars` row for two plays). **`pron_retry`** is judged directly from the audio by the feedback model (no STT step), with structured output; its audio seconds count toward the daily STT cap.
- **Real check (2026-11-12, synthetic clips):** "também" said by a Polish edge-tts voice → `better: false` with a tip about the nasal ending, in Polish; by a Brazilian voice → `better: true`.
- **Test harness:** the server closes a session after the client disconnects; the test clients now wait for that before stopping their event loop, and a thread hitting a closed loop is now a test error (it was an intermittent warning).

## 016 — Slice 3c: corrections panel and review UI (2026-11-12)
- **Panel:** tabs Corrections / Flashcards; a fixed side column from 1024 px, a bottom sheet with a badge below that (chosen by the author). The badge counts feedback with mistakes not yet seen; on desktop the panel is always visible, so nothing is counted. Full responsive shell stays in slice 5.
- **Transcript editing:** tapping one of the learner's messages opens an inline editor; saving updates it locally and sends `regrade` (grammar only).
- **Word audio:** ▶ replays `word:<w>` audio already received, or sends `speak_word`; 0.8× is enabled once the audio is on the client (`playbackRate`, no new synthesis). 🎙 records while held (hands-free VAD paused) and sends `pron_retry` with the message or card id; the verdict shows under the word.
- **Recast switch** in the header sends `set_recast`.
- **Flashcards UI** uses the REST client (`api.ts`): due cards, show answer, grades Again/Hard/Good/Easy = 1/3/4/5, delete. The LAN proxy also forwards `/flashcards`.

## 017 — Interface and explanation language per user (2026-11-12)
- **Context:** the author (a Portuguese speaker) wants to try the PL→PT direction, but its learner's UI and explanations were in Polish.
- **Decision:** `users.ui_lang` (nullable → `native_lang`), changed in the app with `set_ui_lang` or at creation with `create_user.py --ui-lang`. It drives the UI strings, server messages and the language of `r`, `p` and `tip`; contrast tips still compare with `native_lang`. SPEC §1, §3, §7 updated; migration `0004`.
- **Consequence:** "Aluno PL" (learns Portuguese) now reads everything in Portuguese.

## 018 — Better STT for learners' accents (2026-11-12)
- **Context:** the author reported the app did not understand their Polish. Their transcripts showed it ("Mam na imię Pedro" → "Na imieniem, Pedro" / "Ja kocham na imię").
- **Measured** on 6 Polish sentences with beginner mistakes read by a Brazilian voice (edge-tts), WER vs. what was said:

  | STT | WER | median time |
  |---|---|---|
  | 3.5-flash-lite (before) | 68% | 1.9 s |
  | 3.5-flash-lite + context | 36% | 1.4 s |
  | 3.8-flash | 14% | 4.2 s |
  | 3.8-flash + context | 17% | 5.4 s |
  | 3.8-flash, thinking LOW | 18% | 3.0 s |
  | **3.8-flash, thinking LOW + context** | **13%** | **2.8 s** |

  (`MINIMAL` thinking is rejected by 3.8-flash.)
- **Decision:** `GEMINI_STT_MODEL=gemini-3.8-flash`, new `GEMINI_STT_THINKING_LEVEL=LOW`, and the STT prompt gets the AI's last message as context ("use it only to recognise hard words; keep every mistake"). New `PRICE_STT_OUTPUT_PER_M`.
- **Consequence:** ~1 s more per voice turn and ~2.5× the STT price (still cents per day); the price doubles on 2027-01-01. The stronger model still "fixes" some mistakes (e.g. "dwa kot" → "dwa koty"), so the editable transcript remains necessary.
- **Also seen:** the feedback model once suggested "dwie koty" (wrong; "dwa koty"). Feedback stays on `gemini-3.5-flash-lite` for now; moving it to a stronger model is the next lever if wrong corrections repeat.

## 019 — Light, minimal look and a "thinking" indicator (2026-11-12)
- **Context:** the author found the UI unattractive and wanted it lighter and more minimal, with a sign that the AI is working.
- **Decision:** light theme by default (zinc neutrals, one indigo accent in `@theme`), dark only when chosen in the settings menu (class-based `dark` variant, remembered in `localStorage`; applied before the first paint). Reusable building blocks are Tailwind v4 `@utility` classes in `index.css` (`@layer components` cannot be composed with `@apply` in v4). Level, interface language, pronunciation echo, theme and logout moved into one ⚙ menu; the input is a single rounded bar with mic and send icons; inline SVG icons, no icon library.
- **Thinking indicator:** the reducer tracks `phase` (`transcribing` after a voice message is sent, `thinking` after the transcript, `idle` once the reply starts streaming or on error). Animated dots "Transcrevendo…" on the learner's side and "Pensando…" on the AI's side; respects `prefers-reduced-motion`.
- **Consequence:** SPEC §9 still asks for light/dark — both exist, light is the default. The full responsive shell remains slice 5.

## 020 — Active TTS switched to ElevenLabs (2026-11-12)
- **Context:** after hearing it in the app, the author chose to keep the ElevenLabs voice (supersedes the choice in 011).
- **Decision:** `TTS_PROVIDER=elevenlabs`, Flash v2.5, premade voices Sarah/George (the Free plan cannot use native library voices through the API). `TTS_MONTHLY_CHARS=10000` (the Free allowance), so at 95% the app moves to edge-tts by itself and never needs a paid overage.
- **Consequence:** on the Free plan only a few replies per month use ElevenLabs (≈8,800 of 10,000 characters were spent on 2026-11-12, mostly by the benchmark); after that edge-tts speaks until the allowance resets. Regular daily use needs a paid ElevenLabs plan — then raise `TTS_MONTHLY_CHARS` to the plan's characters, set `PRICE_TTS_PER_1K_CHARS`, and native voices become available. Google stays configured as an alternative (`TTS_PROVIDER=google`).

## 021 — STT back to Flash-Lite for speed (2026-11-12)
- **Context:** the author found the transcription too slow with `gemini-3.8-flash` (~2.4 s warm).
- **Measured** (same 6 accented clips, warm, with the matching question as context): 3.8-flash LOW 9% WER / 2.4 s; 3.6-flash LOW 13% / 2.5 s; **3.5-flash-lite LOW 19% / 1.4 s**; 3.1-flash-lite 18% / 1.5 s. The dedicated `gemini-3.5-transcribe` (v1beta, `audio_transcription` parts, VERBATIM mode, `language_codes`) did badly on accented learner speech (77% WER, once Chinese output), was not faster (1.8 s) and is limited to 10 requests/min on Tier 1 — rejected.
- **Decision (author's choice: speed):** `GEMINI_STT_MODEL=gemini-3.5-flash-lite`, `GEMINI_STT_THINKING_LEVEL=LOW` (LOW also helps this model: 36% → 19% with context).
- **Consequence:** ~1 s faster per voice turn and 2.5× cheaper STT. Flash-Lite depends much more on the context: in a check where the clips did not answer the AI's last message, transcripts were poor ("Mas na i mi, Pedro."), while 3.8-flash stays ~14% without context. The editable transcript covers mistakes; revisit (3.6-flash is the middle ground) if wrong transcripts become frequent.

## TTS benchmark results

| Run | Where | Provider | Lang | TTFA p50 | TTFA p90 | Notes |
|---|---|---|---|---|---|---|
| 1 (2026-11-12, runs=2) | Local (Brazil) | google (Kore) | pl-PL | 411 ms | 1326 ms | 60 items, 0 errors; total p50 1207 ms |
| 1 | Local (Brazil) | google (Kore) | pt-BR | 391 ms | 1212 ms | total p50 1159 ms |
| 1 | Local (Brazil) | elevenlabs (Sarah, Flash v2.5) | pl-PL | 281 ms | 325 ms | total p50 381 ms |
| 1 | Local (Brazil) | elevenlabs (Sarah, Flash v2.5) | pt-BR | 278 ms | 294 ms | total p50 369 ms |

## Provider choices (fill in when keys are created)

| Setting | Value | Price checked | Date |
|---|---|---|---|
| `GEMINI_CHAT_MODEL` | `gemini-3.5-flash-lite` | US$ 0.30 in (text/audio) / 2.50 out per 1M | 2026-11-12 |
| `GEMINI_UTILITY_MODEL` | `gemini-3.1-flash-lite` | US$ 0.25 in (0.50 audio) / 1.50 out per 1M | 2026-11-12 |
| `GEMINI_STT_MODEL` | `gemini-3.5-flash-lite` (thinking LOW), see 021 | US$ 0.30 in / 2.50 out per 1M | 2026-11-12 |
| `GEMINI_FEEDBACK_MODEL` | `gemini-3.5-flash-lite` | US$ 0.30 in (text/audio) / 2.50 out per 1M | 2026-11-12 |
| `TTS_PROVIDER` (after benchmark) | `elevenlabs` (was `google`, see 020) | Free plan, 10,000 chars/month | 2026-11-12 |
| TTS model / plan | Chirp 3 HD, voices Kore (F) and Charon (M), OGG_OPUS | free tier (`TTS_MONTHLY_CHARS=1000000`, `PRICE_TTS_PER_1K_CHARS=0`) | 2026-11-12 |
