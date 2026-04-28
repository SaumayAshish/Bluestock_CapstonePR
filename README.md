# BlueStock Geography API

This workspace imports Indian village directory spreadsheets into MySQL,
normalizes the hierarchy, and exposes the data through a FastAPI REST API.

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

2. Start MySQL locally with Docker, or create the database manually.

   ```powershell
   docker compose up -d mysql
   ```

   Manual MySQL setup:

   ```sql
   CREATE DATABASE IF NOT EXISTS bluestock
     CHARACTER SET utf8mb4
     COLLATE utf8mb4_unicode_ci;

   CREATE USER IF NOT EXISTS 'bluestock'@'localhost' IDENTIFIED BY 'change-me';
   GRANT ALL PRIVILEGES ON bluestock.* TO 'bluestock'@'localhost';
   FLUSH PRIVILEGES;
   ```

3. Copy `.env.example` to `.env` and update the MySQL credentials.

4. Import the raw dataset.

   ```powershell
   python scripts\import_to_mysql.py --create-schema --replace
   ```

5. Normalize the imported rows into API tables.

   ```powershell
   python scripts\normalize_geography.py --create-schema --replace
   ```

6. Verify the normalized hierarchy.

   ```powershell
   python scripts\verify_geography.py
   ```

7. Create local API credentials.

   ```powershell
   python scripts\create_api_client.py --name "Local Development Client" --email dev@example.com --plan unlimited
   ```

8. Create the admin user and apply SaaS account schema updates.

   ```powershell
   python scripts\setup_saas.py
   ```

9. Start the API.

   ```powershell
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

## Data Model

The importer writes file-level metadata to `import_files` and spreadsheet rows to
`import_rows`. Each spreadsheet row is stored as MySQL `JSON` in `row_data`,
which keeps the pipeline tolerant of inconsistent sheet layouts across `.xls`
and `.ods` files.

The normalizer populates:

- `countries`
- `states`
- `districts`
- `sub_districts`
- `villages`

The API credential and analytics tables are:

- `api_clients`
- `api_keys`
- `api_usage_events`
- `admin_users`

Run `sql/mysql_schema.sql` manually if you prefer managing schema creation
outside the importer.

Run `sql/geography_schema.sql` manually if you prefer managing normalized API
schema creation outside the normalizer.

## API

Health:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Authenticated endpoints require:

- `X-API-Key`
- `X-API-Secret`

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

Interactive docs are available at:

```text
http://127.0.0.1:8000/docs
```

Dashboard pages:

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/admin`
- `http://127.0.0.1:8000/portal`

Default local admin credentials come from `.env`:

```text
ADMIN_EMAIL=admin@bluestock.local
ADMIN_PASSWORD=admin12345
```

Change these before using the app outside local development.
