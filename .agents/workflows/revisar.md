---
description: Independent review of the last slice against docs/SPEC.md — read-only, reports findings, changes nothing
---

# /revisar — review a finished slice

Run this in a NEW agent conversation (not the one that wrote the code), so the review is independent.

1. Read `docs/SPEC.md` and `.agents/rules/projeto.md`.
2. Run `git log --oneline -20` and identify the commits of the slice the user names (or the latest slice).
3. Read the diff of those commits (`git diff <first>^..<last>`).
4. Do NOT edit any file. Check and report:
   - SPEC sections claimed vs actually implemented (missing items, extra scope).
   - Both directions (PT→PL and PL→PT) covered wherever language is involved; both i18n locales filled.
   - External API calls: timeout, 429 handling, typed `error` event or fallback, model names from config.
   - Cost: every Gemini/ElevenLabs call records `usage_events`; no paid call inside tests; no re-synthesis of text that is cached or already on the client.
   - Security: token check on REST and WS, manual WS Origin check, no secrets in code or logs.
   - Memory invariant (SPEC §4.2) still holds, if touched.
   - Tests: do they test real behavior or just mocks returning what the test expects?
   - Placeholder logic, dead code, `TODO`, `any` without justification.
5. Run the test suite and the frontend build; include the results.
6. Report in Brazilian Portuguese, ordered by severity: **Crítico**, **Importante**, **Menor**. For each item: file:line, what is wrong, suggested fix.
