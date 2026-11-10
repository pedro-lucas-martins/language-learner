---
description: Build one slice of the project from docs/SPEC.md (plan → approve → implement → test → docs → commit → report)
---

# /fatia — build one slice

The user calls this as `/fatia N` (N = slice number from `docs/SPEC.md` §11), optionally followed by extra notes.

1. Read `docs/SPEC.md` (whole file), `docs/ARCHITECTURE.md` and `docs/DECISIONS.md`. Run `git log --oneline -15` and `git status` to understand the current state.
2. Verify the previous slice is healthy: run the backend tests and the frontend typecheck/build. If anything fails, stop and report it instead of starting slice N.
3. Write an Implementation Plan artifact for slice N only:
   - files to create/modify,
   - the tests you will write,
   - which SPEC sections it implements,
   - anything ambiguous in the SPEC, as explicit questions.
   If the plan touches more than ~15 files, split it into numbered sub-steps.
4. Wait for the user to approve the plan (or a sub-step). Do not edit files before approval.
5. Implement the approved sub-step. Keep changes inside its scope.
6. Run tests, linters (`ruff`, `tsc --noEmit`) and the build. Fix failures.
7. Update `docs/ARCHITECTURE.md`, `docs/USER_ACTIONS.md` and, if a decision was made, `docs/DECISIONS.md`.
8. `git status` → check no secrets are staged → commit with a Conventional Commit message.
9. Write the report in Brazilian Portuguese using the format from the project rules (O que foi feito / Como testar / Limitações conhecidas / 🔔 O que você precisa fazer agora).
10. If more sub-steps remain, present the next one and wait for approval.
