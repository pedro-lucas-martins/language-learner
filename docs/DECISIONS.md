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
| `GEMINI_STT_MODEL` | `gemini-3.5-flash-lite` | US$ 0.30 in (audio) per 1M | 2026-11-12 |
| `TTS_PROVIDER` (after benchmark) | `google` | free tier 1M chars/month | 2026-11-12 |
| TTS model / plan | Chirp 3 HD, voices Kore (F) and Charon (M), OGG_OPUS | free tier (`TTS_MONTHLY_CHARS=1000000`, `PRICE_TTS_PER_1K_CHARS=0`) | 2026-11-12 |
