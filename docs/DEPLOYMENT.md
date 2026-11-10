# Deployment

Completed in slice 6. Notes collected so far:

- **Frontend → Vercel (Hobby, free).** Root directory `frontend/`. `vercel.json` already handles SPA rewrites and security headers. Set `VITE_API_URL` (https) and optionally `VITE_WS_URL` (wss) in the Vercel project.
- **Backend → Render free web service** (Docker, `backend/Dockerfile`). The free instance sleeps when idle; the first request after a pause takes about a minute. The container listens on `$PORT`.
- **Database → Supabase free Postgres.** Use the asyncpg connection string in `DATABASE_URL`. Free projects pause after inactivity.
- Backend env must set `APP_ENV=production`, `FRONTEND_URL` (the Vercel production URL) and `VERCEL_PREVIEW_REGEX`.
