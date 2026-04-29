# BlueStock Technical Architecture

## 3. Technical Architecture

### 3.1 Technology Stack Decision Matrix

| Component | Implemented Technology | Status | Notes |
| --- | --- | --- | --- |
| Backend runtime | Python + FastAPI | Complete | The current codebase exposes REST endpoints from `app/main.py`. This differs from the earlier Node.js + Express proposal. |
| Database | PostgreSQL 16 / Neon-compatible PostgreSQL | Complete | `docker-compose.yml` provisions local PostgreSQL; `DATABASE_URL` can point to Neon. |
| ORM | Direct SQL via `psycopg2` | Complete | The project uses explicit PostgreSQL SQL for imports, normalization, authentication, and analytics queries. |
| Frontend framework | React 18 + TypeScript + Vite | Complete | `frontend/` contains the admin dashboard and B2B portal. FastAPI-rendered pages remain fallback pages. |
| Charting library | Recharts | Complete | Dashboard and portal analytics use reusable Recharts components. |
| Caching layer | Redis | Complete | Redis is used for response caching and distributed rate-limit counters when `REDIS_URL` is configured. |
| Rate limiting | Redis + database-backed usage fallback | Complete | Daily and burst limits are enforced per API key. |
| Authentication | API key/secret + HMAC JWT + PBKDF2 password hashes | Complete | API clients use `X-API-Key` and `X-API-Secret`; portal/admin sessions use JWT bearer tokens. |
| Hosting platform | Local Uvicorn/Docker + Vercel scaffold | Partial | `vercel.json` and `api/index.py` are present; provider credentials and projects are external. |

### 3.2 System Architecture Diagram

```text
+--------------------------------------------------------------------+
|                         CLIENT LAYER                               |
|  +------------+     +------------+     +-------------------------+  |
|  | Admin User |     | API Client |     | Client Portal User      |  |
|  | /admin     |     | HTTP       |     | /portal                 |  |
|  +-----+------+     +-----+------+     +------------+------------+  |
+--------|-----------------|--------------------------|---------------+
         |                 |                          |
         v                 v                          v
+--------------------------------------------------------------------+
|                         FASTAPI APP                                |
|  +--------------------------------------------------------------+  |
|  | Middleware                                                   |  |
|  | - CORS handling                                              |  |
|  | - usage logging                                              |  |
|  +--------------------------------------------------------------+  |
|  +--------------------------------------------------------------+  |
|  | Authentication                                               |  |
|  | - API key + secret validation                                |  |
|  | - JWT validation                                             |  |
|  | - PBKDF2 password hashing                                    |  |
|  | - plan-based rate limiting                                   |  |
|  +--------------------------------------------------------------+  |
|  +--------------------------------------------------------------+  |
|  | Routes                                                       |  |
|  | /v1/* geography API  /auth/*  /portal/*  /admin/*  /health   |  |
|  +--------------------------------------------------------------+  |
+--------------------------------------------------------------------+
         |
         v
+--------------------------------------------------------------------+
|                            DATA LAYER                              |
|  +--------------------------------------------------------------+  |
|  | PostgreSQL                                                   |  |
|  | - import_files      - import_rows                            |  |
|  | - countries         - states                                 |  |
|  | - districts         - sub_districts                          |  |
|  | - villages          - api_clients                            |  |
|  | - api_keys          - api_usage_events                       |  |
|  | - admin_users                                                |  |
|  +--------------------------------------------------------------+  |
+--------------------------------------------------------------------+
```

### 3.3 Data Flow Patterns

API request flow:

1. Client sends request with `X-API-Key` and `X-API-Secret`.
2. FastAPI validates the key and secret hashes against `api_keys`.
3. The client account is checked for active status.
4. Plan-based rate limiting is applied through Redis, with local fallback.
5. The request is routed to the geography handler.
6. PostgreSQL queries run against normalized geography tables.
7. Usage is logged to `api_usage_events`.
8. JSON response is returned to the client.

Portal/admin flow:

1. User logs in through `/auth/client-login` or `/admin/login`.
2. Password is verified with PBKDF2.
3. The API returns an HMAC-signed JWT.
4. Portal/admin endpoints validate the JWT bearer token.
5. Account, key, usage, and admin summary data are returned from PostgreSQL.

Data import flow:

1. `scripts/import_to_postgres.py` reads `.xls`, `.xlsx`, and `.ods` files from `dataset/`.
2. Rows are stored as JSON in `import_rows`, with file metadata in `import_files`.
3. `scripts/normalize_geography.py` creates/verifies the India country record.
4. States, districts, sub-districts, and villages are upserted into normalized tables.
5. `scripts/verify_geography.py` runs count, orphan, duplicate, and sample hierarchy checks.

## 4. Database Design

### 4.1 Normalization Strategy

The normalized API schema follows a 3NF hierarchy:

- `countries` owns `states`.
- `states` owns `districts`.
- `districts` owns `sub_districts`.
- `sub_districts` owns `villages`.
- `api_clients`, `api_keys`, `api_usage_events`, and `admin_users` support SaaS access and analytics.

### 4.2 Entity Relationship Summary

| Table | Purpose | Key Fields | Foreign Key To |
| --- | --- | --- | --- |
| `countries` | Root geography hierarchy | `id`, `code`, `name` | - |
| `states` | State-level geography | `id`, `country_id`, `code`, `name` | `countries.id` |
| `districts` | District-level geography | `id`, `state_id`, `code`, `name` | `states.id` |
| `sub_districts` | Block/Taluka-level geography | `id`, `district_id`, `code`, `name` | `districts.id` |
| `villages` | Village/area-level geography | `id`, `sub_district_id`, `code`, `name`, `display_name` | `sub_districts.id` |
| `api_clients` | B2B client accounts | `id`, `email`, `plan`, `password_hash` | - |
| `api_keys` | API credentials | `id`, `client_id`, `key_hash`, `secret_hash` | `api_clients.id` |
| `api_usage_events` | Usage analytics | `id`, `client_id`, `api_key_id`, `endpoint`, `latency_ms` | `api_clients.id`, `api_keys.id` |
| `admin_users` | Admin login accounts | `id`, `email`, `password_hash` | - |

### 4.3 Indexing Strategy

| Table | Indexed Columns | Purpose |
| --- | --- | --- |
| `states` | `code`, `(country_id, search_name)` | State lookup and listing |
| `districts` | `(state_id, code)`, `(state_id, search_name)` | State-scoped district joins |
| `sub_districts` | `(district_id, code)`, `(district_id, search_name)` | District-scoped sub-district joins |
| `villages` | `(sub_district_id, code)`, `(sub_district_id, search_name)`, `search_name`, trigram `search_name` | Hierarchical and search queries |
| `api_clients` | `email` | Login and uniqueness checks |
| `api_keys` | `key_hash`, `client_id` | Authentication lookups |
| `api_usage_events` | `(client_id, created_at)`, `(api_key_id, created_at)` | Time-series usage analytics |

### 4.4 Sample Data Relationship

```text
Country: India (code: IN)
  -> State: Maharashtra (code: 27)
      -> District: Nandurbar (code: 497)
          -> SubDistrict: Akkalkuwa (code: 03950)
              -> Village: Manibeli (code: 525002)
              -> Village: Dhankhedi (code: 525003)
              -> Village: Chimalkhadi (code: 525004)
              -> Village: Sinduri (code: 525005)
```

### 4.5 Future-Proofing Considerations

- `countries` keeps the hierarchy extensible beyond India.
- Original MDDS codes are preserved in `code` fields.
- Core tables include `created_at` timestamps.
- API keys can be deactivated without deleting credentials.
- Redis-backed rate limiting is ready for multi-instance deployment when `REDIS_URL` points to a shared Redis provider.

## 5. Data Import Strategy

### 5.1 Source Data Understanding

The import pipeline expects the MDDS village directory spreadsheet layout:

| Source Field | Stored Column |
| --- | --- |
| MDDS STC | `column_1` |
| STATE NAME | `column_2` |
| MDDS DTC | `column_3` |
| DISTRICT NAME | `column_4` |
| MDDS Sub_DT | `column_5` |
| SUB-DISTRICT NAME | `column_6` |
| MDDS PLCN | `column_7` |
| Area Name | `column_8` |

### 5.2 Data Volume Estimates

| Hierarchy Level | Estimated Count |
| --- | ---: |
| States/UTs | 36 |
| Districts | 700+ |
| Sub-districts | 6,000+ |
| Villages | 600,000+ |
| Total rows | ~600,000 |

### 5.3 Import Process Workflow

1. Start PostgreSQL and Redis with `docker compose up -d postgres redis` or provide `DATABASE_URL` and `REDIS_URL` in `.env`.
2. Import source spreadsheets:

   ```powershell
   python scripts\import_to_postgres.py --create-schema --replace
   ```

3. Normalize the imported rows:

   ```powershell
   python scripts\normalize_geography.py --create-schema --replace
   ```

   The normalizer selects one canonical source row per administrative code path
   before each upsert. This prevents duplicate spreadsheet rows from triggering
   PostgreSQL `ON CONFLICT` cardinality errors and keeps repeated imports
   idempotent.

4. Verify normalized data integrity:

   ```powershell
   python scripts\verify_geography.py
   ```

5. Create API/admin credentials:

   ```powershell
   python scripts\create_api_client.py --name "Local Development Client" --email dev@example.com --plan unlimited
   python scripts\setup_saas.py
   ```

6. Seed the approved B2B portal demo account and analytics:

   ```powershell
   python scripts\seed_demo_portal.py
   ```

   The demo seed creates `demo@bluestock.local` / `Demo12345`, active API keys,
   and 14 days of realistic usage events for portal chart demonstrations.

### 5.4 Error Handling Strategy

- Raw import is idempotent per file, sheet, and row number.
- Imported rows keep the original source row number for manual review.
- Normalization uses de-duplicated upserts to avoid duplicate hierarchy records
  and duplicate source-code conflicts.
- `scripts/verify_geography.py` reports orphaned rows, duplicate codes within parent scopes, and a known sample hierarchy check.
- Ambiguous or invalid source rows should be reviewed from `import_rows` using `source_row_number` and `row_data`.
