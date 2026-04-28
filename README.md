# BlueStock Geography API

BlueStock imports Indian village directory spreadsheets into PostgreSQL,
normalizes the administrative hierarchy, and exposes authenticated FastAPI
endpoints for village search and autocomplete.

Architecture and import-design details are documented in
`docs/technical_architecture.md`.

Phase 2 API/dashboard implementation notes are documented in
`docs/phase2_implementation.md`.

## Setup

1. Create a virtual environment and install dependencies.

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. Start PostgreSQL and Redis locally.

   ```powershell
   docker compose up -d postgres redis
   ```

3. Copy `.env.example` to `.env` and update `DATABASE_URL`, `REDIS_URL`, and secrets.

4. Import the raw dataset.

   ```powershell
   python scripts\import_to_postgres.py --create-schema --replace
   ```

5. Normalize the imported rows into API tables.

   ```powershell
   python scripts\normalize_geography.py --create-schema --replace
   ```

6. Verify the normalized hierarchy.

   ```powershell
   python scripts\verify_geography.py
   ```

7. Create the admin user and a local API client.

   ```powershell
   python scripts\setup_saas.py
   python scripts\create_api_client.py --name "Local Development Client" --email dev@example.com --plan unlimited
   ```

8. Start the API.

   ```powershell
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

## Data Model

Raw spreadsheet rows are stored in:

- `import_files`
- `import_rows`

The normalized hierarchy is:

- `countries`
- `states`
- `districts`
- `sub_districts`
- `villages`

SaaS/authentication tables are:

- `api_clients`
- `api_keys`
- `api_usage_events`
- `admin_users`
- `user_state_access`

Run `sql/postgres_schema.sql` manually if you prefer managing schema creation
outside the importer. `sql/migrations/001_initial_postgres.sql` is the initial
Phase 1/2 migration entry.

## API

Health:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Authenticated `/v1` read endpoints require `X-API-Key`. Write endpoints require
both `X-API-Key` and `X-API-Secret`.

Endpoints:

- `POST /auth/register`
- `POST /auth/client-login`
- `POST /admin/login`
- `GET /admin/summary`
- `GET /admin/analytics`
- `GET /admin/clients`
- `PATCH /admin/clients/{client_id}`
- `POST /admin/clients/{client_id}/approve`
- `POST /admin/clients/{client_id}/suspend`
- `GET /admin/usage`
- `GET /admin/villages?state_id=27&limit=500`
- `GET /admin/api-logs`
- `GET /admin/api-logs/export.csv`
- `GET /portal/me`
- `GET /portal/api-keys`
- `POST /portal/api-keys`
- `POST /portal/api-keys/{key_id}/rotate-secret`
- `DELETE /portal/api-keys/{key_id}`
- `GET /portal/usage`
- `GET /v1/states`
- `GET /v1/states/{id}/districts`
- `GET /v1/districts?state_code=27`
- `GET /v1/districts/{id}/subdistricts`
- `GET /v1/sub-districts?district_id=1`
- `GET /v1/villages?sub_district_id=1&q=ram&limit=50`
- `GET /v1/subdistricts/{id}/villages?page=1&limit=50`
- `GET /v1/autocomplete?q=ram&limit=20`
- `GET /v1/search?q=ram&limit=20`

Interactive docs are available at `http://127.0.0.1:8000/docs`.

