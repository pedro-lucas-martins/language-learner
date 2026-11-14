# Deployment (slice 6)

All on free plans. The owner creates the accounts and types every secret into the dashboards;
secrets never go into the repository.

| Part | Service | Region | Free-plan limits |
|---|---|---|---|
| Site | Vercel (Hobby) | global CDN | none that matter here |
| API + WebSocket | Render free web service (Docker) | Frankfurt | sleeps after 15 min idle; ~1 min to wake |
| Database | Supabase free Postgres | eu-central-1 (Frankfurt) | pauses after 7 days without use; 500 MB |

While Render wakes up, the site shows "O servidor está acordando… pode levar até 1 minuto" and keeps
reconnecting by itself (backoff 1 s → 10 s, 10 tries). The login screen already calls `/health`, so the
server starts waking while the learner types the token.

## 1. Supabase (database)

1. supabase.com → **New project** → region **Central EU (Frankfurt)**. Save the database password in a
   password manager.
2. **Connect** → **Session pooler** (IPv4, port 5432) → copy the URI.
3. Turn it into the app's form: replace `postgresql://` with `postgresql+asyncpg://` and append
   `?ssl=require`:

   ```
   postgresql+asyncpg://postgres.<ref>:<password>@aws-0-eu-central-1.pooler.supabase.com:5432/postgres?ssl=require
   ```

   `app/database.py` already sets `statement_cache_size=0` and `pool_pre_ping`, which the pooler needs.
4. Save it locally in **`.env.production`** at the repository root (ignored by git):

   ```
   DATABASE_URL=postgresql+asyncpg://...
   TTS_PROVIDER=google
   TTS_FALLBACK_PROVIDER=
   ```

5. Apply the migrations from your computer (values in the environment win over `.env`):

   ```bash
   cd backend && set -a && . ../.env.production && set +a && .venv/bin/alembic upgrade head
   ```

   The container also runs `alembic upgrade head` on every start, so later migrations apply by themselves.

## 2. Render (backend)

1. render.com → sign in with GitHub → grant access to the private `language-learner` repository.
2. **New → Blueprint** → pick the repository. Render reads `render.yaml` (Docker, `rootDir: backend`,
   free, Frankfurt, health check `/health`, `APP_ENV=production`, models, prices and caps).
3. Fill in the secrets it asks for (`sync: false`):

   | Key | Value |
   |---|---|
   | `DATABASE_URL` | the asyncpg URI from step 1 |
   | `GEMINI_API_KEY` | Google AI Studio key |
   | `ELEVENLABS_API_KEY` | ElevenLabs key (can stay empty while Google speaks) |
   | `FRONTEND_URL` | leave a placeholder now (`https://example.com`), fix it in step 4 |
   | `VERCEL_PREVIEW_REGEX` | leave empty now, fix it in step 4 |

4. Service → **Environment → Secret Files** → add a file named **`gcp.json`** with the content of the Google
   service-account key (Cloud Text-to-Speech). It is mounted at `/etc/secrets/gcp.json`, which is what
   `GOOGLE_APPLICATION_CREDENTIALS` points to.
5. Deploy. Check `https://<service>.onrender.com/health` → `{"status":"ok","env":"production"}`.
   `/docs`, `/redoc` and `/openapi.json` return 404 in production.

### Voice provider in production

`render.yaml` starts with **Google Chirp3 HD** (`TTS_PROVIDER=google`, 1 M free characters a month), because
the ElevenLabs free quota is almost used up and a fresh database would not know that. After subscribing to
ElevenLabs Starter, change in Render: `TTS_PROVIDER=elevenlabs`, `TTS_MONTHLY_CHARS=150000`,
`TTS_FALLBACK_PROVIDER=google`, `TTS_FALLBACK_MONTHLY_CHARS=1000000`, and fill `ELEVENLABS_API_KEY`.

## 3. Vercel (frontend)

1. vercel.com → sign in with GitHub → **Add New → Project** → the repository.
2. **Root Directory: `frontend`**. Framework: Vite (detected). `vercel.json` already has the SPA rewrites and
   the security headers.
3. Environment variable: `VITE_API_URL=https://<service>.onrender.com`. `VITE_WS_URL` is derived
   (`https` → `wss`); set it only if the WebSocket lives elsewhere.
4. Deploy and note the production URL, e.g. `https://language-learner.vercel.app`.

## 4. Allowed origins (back on Render)

- `FRONTEND_URL` = the Vercel production URL (no trailing slash).
- `VERCEL_PREVIEW_REGEX` = previews of this project only, e.g.
  `^https://language-learner(-[a-z0-9-]+)?\.vercel\.app$` (anchored; adjust to the project's name).

Render redeploys after saving. Any other origin is refused by CORS and the WebSocket closes with 4403.

## 5. Users (from your computer, against the production database)

```bash
cd backend && set -a && . ../.env.production && set +a
.venv/bin/python -m scripts.create_user --name "Aluno" --native pl-PL --level A2
```

The token is printed once: save it in a password manager and send it to the learner by a private channel.
Repeat for a second user (SPEC §11: "a second user can log in").

## 6. Topic audio (optional, costs Google TTS characters, inside the free tier)

```bash
cd backend && set -a && . ../.env.production && set +a
.venv/bin/python -m scripts.precompute_topic_audio
```

It asks for confirmation and skips topics already cached.

## Checklist after deploy

- [ ] The site opens over HTTPS.
- [ ] Login with the learner's token; a typed message gets a reply with voice.
- [ ] A second user can log in.
- [ ] `/docs` → 404.
- [ ] Another origin is refused: `curl -i -H "Origin: https://evil.example" https://<service>.onrender.com/health`
      has no `access-control-allow-origin` header.
- [ ] After 15+ minutes idle, opening the site shows the "waking up" message and then connects.
