# Phase 2 Implementation Notes

## API Contract

Implemented in the current FastAPI backend:

- `GET /v1/search`
- `GET /v1/states`
- `GET /v1/states/{id}/districts`
- `GET /v1/districts/{id}/subdistricts`
- `GET /v1/subdistricts/{id}/villages`
- `GET /v1/autocomplete`

All `/v1` responses use the Phase 2 envelope:

```json
{
  "success": true,
  "count": 25,
  "data": [],
  "meta": {
    "requestId": "req_xxx",
    "responseTime": 47,
    "rateLimit": {
      "remaining": 4850,
      "limit": 5000,
      "reset": "2026-04-29T00:00:00Z"
    }
  }
}
```

Village search, autocomplete, and village listing endpoints return dropdown-ready rows:

```json
{
  "value": "village_id_525002",
  "label": "Manibeli",
  "fullAddress": "Manibeli, Akkalkuwa, Nandurbar, MAHARASHTRA, India",
  "hierarchy": {
    "village": "Manibeli",
    "subDistrict": "Akkalkuwa",
    "district": "Nandurbar",
    "state": "MAHARASHTRA",
    "country": "India"
  }
}
```

## Authentication And Security

- Read endpoints require `X-API-Key`.
- Write endpoints require both `X-API-Key` and `X-API-Secret`.
- New API credentials use the required formats:
  - `ak_[32 hex chars]`
  - `as_[32 hex chars]`
- Secrets are stored as hashes.
- API keys can be rotated and revoked from portal endpoints.
- Users can have up to five active API keys.
- API clients must be `active` before their keys can access `/v1` data.
- Security headers are attached to every response:
  - `X-Content-Type-Options`
  - `X-Frame-Options`
  - `X-XSS-Protection`
  - `Strict-Transport-Security`
  - `Content-Security-Policy`

## Rate Limits

Implemented as Redis-backed burst and daily counters with a local fallback:

| Plan | Daily Requests | Burst Per Minute |
| --- | ---: | ---: |
| Free | 5,000 | 100 |
| Premium | 50,000 | 500 |
| Pro | 300,000 | 2,000 |
| Unlimited | 1,000,000 | 5,000 |

Responses include:

- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`

Use a shared Redis provider such as Upstash in staging and production.

## Admin Features

Implemented backend endpoints:

- `GET /admin/summary`
- `GET /admin/analytics`
- `GET /admin/clients`
- `PATCH /admin/clients/{client_id}`
- `POST /admin/clients/{client_id}/approve`
- `POST /admin/clients/{client_id}/suspend`
- `GET /admin/villages`
- `GET /admin/api-logs`
- `GET /admin/api-logs/export.csv`

These endpoints support the dashboard data needed for:

- top states by village count
- API requests over time
- users by plan
- requests by endpoint
- hourly usage
- response-time trends
- user approval/suspension
- village master browsing
- API log monitoring and CSV export

## B2B Portal Features

Implemented backend endpoints:

- `POST /auth/register`
- `POST /auth/client-login`
- `GET /portal/me`
- `GET /portal/api-keys`
- `POST /portal/api-keys`
- `POST /portal/api-keys/{key_id}/rotate-secret`
- `DELETE /portal/api-keys/{key_id}`
- `GET /portal/usage`

Registration now creates `pending_approval` accounts. Admin approval is required before API key creation and API access.

## Frontend Dashboard

Implemented in `frontend/`:

- React 18 + TypeScript + Vite application shell.
- Admin dashboard wired to `/admin/login`, `/admin/summary`, `/admin/analytics`, and `/admin/clients`.
- B2B portal wired to `/auth/register`, `/auth/client-login`, `/portal/me`, `/portal/api-keys`, and `/portal/usage`.
- API key creation, secret rotation, and revocation controls.
- Recharts panels for request volume, plan mix, endpoint usage, response times, and top states.
- Zustand token storage and React Query server-state loading.

The older FastAPI-rendered `/admin` and `/portal` pages remain available as
lightweight fallback pages.

## Deployment Scaffolding

Implemented:

- `vercel.json` builds `frontend/` and routes backend requests to FastAPI.
- `api/index.py` exports the existing FastAPI app for Vercel's Python runtime.
- `docs/deployment.md` documents required Vercel, Neon, and Redis environment variables.

## Prisma / Node Transition

Placeholder integration point:

- `prisma/schema.prisma` maps the current PostgreSQL schema for a future Node service.
- The active backend remains FastAPI + `psycopg2`; Prisma is not used by runtime code.

## Not Yet Implemented

SMTP emails, payment/revenue metrics, and a separate demo client app remain future implementation work. The current backend is FastAPI with Neon-compatible PostgreSQL and Redis.
