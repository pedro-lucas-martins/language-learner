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

## Provider choices (fill in when keys are created)

| Setting | Value | Price checked | Date |
|---|---|---|---|
| `GEMINI_CHAT_MODEL` | | | |
| `GEMINI_UTILITY_MODEL` | | | |
| `GEMINI_STT_MODEL` | | | |
| `ELEVENLABS_MODEL` | | | |
| ElevenLabs plan | | | |
