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

## Not Yet Implemented

The repo still uses FastAPI-rendered dashboard pages. The requested React 18 + TypeScript + Vite + Tailwind + Recharts + Zustand + React Query frontend is not present yet. The backend endpoints now expose the data needed to build that frontend in a later phase.

Prisma, SMTP emails, payment/revenue metrics, and a separate demo client app remain future implementation work. The current backend is FastAPI with Neon-compatible PostgreSQL and Redis.
