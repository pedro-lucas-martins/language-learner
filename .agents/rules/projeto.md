# Project rules — AI Language Partner (pt-BR ⇄ pl-PL)

These rules apply to every agent session in this workspace.

## 1. Source of truth
- Read `docs/SPEC.md` before planning any task. It defines the product, the stack, the WebSocket protocol and the slice order.
- If the user's request, the code and `docs/SPEC.md` disagree, STOP and ask which is correct. Do not silently pick one.
- To change the WebSocket protocol (SPEC §7), update SPEC §7 first, then backend `app/protocol.py`, then `frontend/src/protocol.ts`, in the same commit.
- Record every non-obvious technical decision in `docs/DECISIONS.md` (short ADR: context, decision, consequence).

## 2. Scope discipline
- Work on ONE slice at a time (SPEC §11). Do not implement features from later slices "while you're at it".
- Always use Planning mode for a slice: produce an Implementation Plan artifact and wait for the user's approval before editing files.
- Keep each plan small enough to review: if a slice needs more than ~15 files, split it into sub-steps and ask the user to approve each.
- Never use `TODO`, `pass`, `...`, mock responses or placeholder logic to make something "look done". If something cannot be finished, say so in the report and leave it out.

## 3. Cost discipline
- Paid services allowed: Gemini API (paid tier) and one TTS provider among Google Cloud TTS (Chirp 3 HD), ElevenLabs and Cartesia (SPEC §2, §6). Hosting, DB and CI stay on free tiers. Never add another paid service without the user's explicit approval.
- Every call to Gemini or a TTS provider must record a row in `usage_events` (SPEC §3) — no untracked paid calls, including in scripts.
- Every call to an external API must: have a timeout, handle 429/quota/5xx with one retry + backoff, then fall back (TTS) or emit a typed `error` event. Never crash the WebSocket.
- Tests must NEVER call real paid APIs. Scripts that spend money or free-tier quota (`precompute_topic_audio.py`, `stt_eval.py`, `tts_bench.py`) must print the estimated cost and ask for confirmation before running.
- Model names, voice IDs, prices and limits come from `config.py` (env vars), never hardcoded in services.
- Never synthesize the same text twice: use the TTS cache and client-side replay (SPEC §6).

## 4. Code standards
- Backend: Python 3.11+, FastAPI, SQLAlchemy 2.0 async, Pydantic v2, type hints everywhere, `ruff` clean.
- Frontend: React + Vite + TypeScript strict, Tailwind. No `any` without a comment explaining why.
- Comments and identifiers in English. User-facing strings ONLY via the i18n dictionaries (`pt-BR`, `pl-PL`) — both locales must be filled in the same change.
- Bidirectional by default: any feature touching language (prompts, topics, grammar rules, voices, UI text) must support both directions PT→PL and PL→PT in the same change.
- Secrets only from env. Never print, log or commit secrets or tokens.

## 5. Tests
- Pure logic must have unit tests (pytest / vitest): sentence buffer, memory window invariant, SM-2, grammar JSON validation, topic picker, origin check.
- External APIs are mocked in tests. No test may call a real provider.
- Run the tests before every commit. If tests fail, fix them or report — never commit red.

## 6. Git
- The repo must have `.gitignore` (including `.env`, `node_modules`, `__pycache__`, `.venv`, `dist`) BEFORE the first `git add`.
- Commit at the end of each approved sub-step with Conventional Commits (`feat(scope):`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`).
- Never `git push`, never force-push, never rewrite history, never change branches unless the user asks.
- Before committing, run `git status` and make sure no secret or large binary is staged.

## 7. Docs
- After each slice, update `docs/ARCHITECTURE.md` (what exists now, not a changelog), and `docs/USER_ACTIONS.md` (accounts, keys, commands the user must run).
- `docs/DEPLOYMENT.md` is written in slice 6 but notes may be added earlier.

## 8. Report format (end of every slice or sub-step)
Write the report in Brazilian Portuguese:
1. **O que foi feito** — 3 to 6 bullets.
2. **Como testar** — exact commands and what the user should see.
3. **Limitações conhecidas** — honest list.
4. **🔔 O que você precisa fazer agora** — manual actions (keys, accounts, migrations). Write "Nada" if none.
