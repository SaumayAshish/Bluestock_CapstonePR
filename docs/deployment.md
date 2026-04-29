# Deployment Scaffolding

Status: scaffolded, requires provider credentials.

## Vercel

`vercel.json` builds the React app from `frontend/` and routes API traffic to
`api/index.py`, which exports the existing FastAPI app from `app.main`.
`.python-version` pins Vercel's Python runtime target to Python 3.12.

Configured routes:

- Frontend static app: `frontend/dist`
- FastAPI function: `api/index.py`
- API rewrites: `/auth/*`, `/admin/*`, `/portal/*`, `/v1/*`, `/health`, `/docs`

Local production build:

```powershell
cd frontend
npm ci
npm run build
```

Local demo data seed:

```powershell
python scripts\setup_saas.py
python scripts\seed_demo_portal.py
```

The demo seed creates an approved portal account
`demo@bluestock.local` / `Demo12345` with active API keys and populated usage
analytics for academic frontend demonstrations. The seed is intended for local
or staging demo environments only, not production.

## Neon

Set `DATABASE_URL` in Vercel to the Neon pooled PostgreSQL connection string.
Use the unpooled URL only for migration or administrative tooling that requires
a direct connection.

Required Vercel environment variables:

- `DATABASE_URL`
- `REDIS_URL`
- `APP_JWT_SECRET`
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`
- `POSTGRES_POOL_SIZE`
- `VITE_API_BASE_URL`

For same-origin Vercel deployments, `VITE_API_BASE_URL` can be blank. For a
split frontend/API deployment, set it to the API origin.

## Redis

Status: backend complete, deployment value required.

The FastAPI backend already uses Redis for:

- response caching through `cache_get` and `cache_set`
- distributed per-minute rate limiting
- distributed daily quota counters

If `REDIS_URL` is missing or unavailable, the backend falls back to local
in-memory burst limiting and database-backed daily quota checks. Production
should use shared Redis so all serverless instances share rate-limit state.

## Complete vs Placeholder

Complete:

- React/Vite frontend scaffold
- Admin dashboard screens wired to current backend endpoints
- B2B portal screens wired to current backend endpoints
- API key create, rotate, revoke controls
- Approved demo client seeding and usage analytics seed data
- Recharts analytics components
- Vercel build/routing scaffold
- Redis-backed backend integration points

Placeholder:

- Prisma is a mapped schema for a possible Node transition, not the active data
  layer.
- Provider resources such as Neon project, Vercel project, and Redis instance
  must be created outside the repository.
