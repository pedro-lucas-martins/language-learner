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

## TTS benchmark results

| Run | Where | Provider | Lang | TTFA p50 | TTFA p90 | Notes |
|---|---|---|---|---|---|---|
| | | | | | | |

## Provider choices (fill in when keys are created)

| Setting | Value | Price checked | Date |
|---|---|---|---|
| `GEMINI_CHAT_MODEL` | | | |
| `GEMINI_UTILITY_MODEL` | | | |
| `GEMINI_STT_MODEL` | | | |
| `TTS_PROVIDER` (after benchmark) | | | |
| TTS model / plan | | | |
