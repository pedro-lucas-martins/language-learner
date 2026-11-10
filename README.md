# Language Learner — pt-BR ⇄ pl-PL conversation partner

A voice-and-text conversation partner for **Brazilian Portuguese** and **Polish**, in both directions:
Brazilians learning Polish and Poles learning Portuguese. You talk freely with a friendly AI native speaker
adapted to your CEFR level, while grammar feedback and flashcards built from your own mistakes appear on the side.

> Status: **slice 1 — text conversation** (login by token, streaming replies from Gemini, memory with running summary). See the build plan in [`docs/SPEC.md`](docs/SPEC.md) §11.

## Stack

| Layer | Tech |
|---|---|
| Frontend | React, Vite, TypeScript, Tailwind CSS — hosted on Vercel |
| Backend | Python, FastAPI, WebSockets — container on a free PaaS |
| Database | PostgreSQL (Supabase in production, Docker locally) |
| AI | Gemini API (conversation, grammar, pronunciation, speech-to-text); voices from Google Cloud TTS (Chirp 3 HD), ElevenLabs or Cartesia — chosen by our own benchmark |

## Run locally

Requirements: Docker, or Python 3.11+ and Node 22+.

```bash
cp .env.example .env          # fill in keys later; slice 0 runs without them
docker compose up --build
```

- Create a learner and copy the token it prints:
  `docker compose exec backend python -m scripts.create_user --name "Pedro" --native pt-BR`
- Frontend: http://localhost:5173 — paste the token
- Backend: http://localhost:8000/health

The AI replies need `GEMINI_API_KEY` and the model names in `.env` (see `docs/USER_ACTIONS.md`).

Without Docker:

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head              # needs DATABASE_URL pointing to a Postgres
python -m scripts.create_user --name "Pedro" --native pt-BR
uvicorn app.main:app --reload

# frontend (another terminal)
cd frontend
npm install
npm run dev
```

## Tests

```bash
cd backend && pytest -q && ruff check . && ruff format --check .
cd frontend && npm test && npm run build
```

CI runs the same commands on every push (`.github/workflows/ci.yml`).

## Docs

- [`docs/SPEC.md`](docs/SPEC.md) — product spec and build order (source of truth)
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — what exists today
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — technical decisions
- [`docs/USER_ACTIONS.md`](docs/USER_ACTIONS.md) — accounts, keys and commands you need to set up
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — deploy guide (completed in slice 6)
