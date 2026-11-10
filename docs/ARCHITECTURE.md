# Architecture — current state

Describes what exists **now**. Target design lives in [`SPEC.md`](SPEC.md).

_Last updated: slice 0._

## Overview

```
frontend (Vite/React, :5173)  ──HTTP──▶  backend (FastAPI, :8000)  ──▶  Postgres (:5432, not used yet)
```

## Backend (`backend/`)

| File | Purpose |
|---|---|
| `app/main.py` | FastAPI app, REST CORS from the origin allowlist, `GET /health` |
| `app/config.py` | All settings from env (`.env` at repo root). Model names, voice IDs, prices, caps |
| `app/security.py` | `is_allowed_origin()` — shared by REST CORS and (from slice 1) the manual WebSocket Origin check |
| `tests/` | pytest: health, CORS, origin allowlist, voice-list parsing |

Origin policy: exact `FRONTEND_URL`; `http://localhost:5173` only when `APP_ENV=development`;
plus `VERCEL_PREVIEW_REGEX` (the project's own preview deployments, never `*.vercel.app`).

## Frontend (`frontend/`)

| File | Purpose |
|---|---|
| `src/config.ts` | `API_URL` / `WS_URL` from `VITE_API_URL` / `VITE_WS_URL`; WS URL derived from the API URL when unset |
| `src/App.tsx` | Placeholder screen that checks `/health` (replaced in slice 1) |
| `vercel.json` | SPA rewrite + security headers (microphone allowed for self only) |

## Local dev & CI

- `docker-compose.yml`: Postgres 16, backend with reload, frontend dev server.
- `.github/workflows/ci.yml`: backend (ruff check, ruff format --check, pytest) and frontend (vitest, tsc + vite build).

## Not built yet

Database models, auth, WebSocket, Gemini, ElevenLabs, grammar, topics, flashcards, responsive UI. See SPEC §11.
