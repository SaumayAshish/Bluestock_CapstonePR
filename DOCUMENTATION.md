# BlueStock: Village-Level Geography API Platform
## Academic Project Documentation

---

# ABSTRACT

BlueStock is a comprehensive B2B SaaS platform that provides village-level geographical data APIs for India. The system addresses the challenge of accessing standardized, hierarchical location data through a production-ready API infrastructure. Built with a FastAPI backend serving a React-based admin dashboard and client portal, the platform implements multi-tenant authentication, API key management, Redis-based rate limiting, and real-time usage analytics. The database architecture normalizes raw census spreadsheet data into a five-tier hierarchy (Country → State → District → Sub-District → Village) with full-text search capabilities. The system supports multiple subscription tiers (Free, Premium, Pro, Unlimited) with configurable rate limits and daily quotas. Key features include automated data import from Excel/ODS formats, JWT-based authentication, comprehensive audit logging, and interactive analytics dashboards. This documentation details the complete system architecture, implementation modules, and technical decisions made during development.

---

# 1. PROJECT OVERVIEW

## 1.1 Introduction

BlueStock is a cloud-native API platform designed to deliver standardized village-level geographical data for India. The system transforms raw census data from government spreadsheets into a queryable REST API, serving B2B clients who require reliable location data for logistics, service delivery, and demographic analysis.

## 1.2 Project Scope

The project encompasses:

- **Data Pipeline**: Import and normalization of census spreadsheets (XLS, XLSX, ODS formats) into a PostgreSQL database
- **API Layer**: RESTful endpoints with authentication, rate limiting, and usage tracking
- **Admin Dashboard**: Operational console for client management, plan configuration, and platform analytics
- **Client Portal**: Self-service interface for API key lifecycle management and usage monitoring
- **Geography API**: Production endpoints for hierarchical location queries and autocomplete search

## 1.3 System Goals

1. Provide sub-second API response times for village lookups across India's 600,000+ villages
2. Enable self-service client onboarding with automated API credential generation
3. Implement granular rate limiting based on subscription tiers
4. Deliver real-time visibility into API usage patterns and system health
5. Maintain data integrity through referential constraints and validation checks

---

# 2. PROBLEM STATEMENT AND OBJECTIVES

## 2.1 Problem Statement

Access to standardized, machine-readable geographical data in India remains fragmented. Government census data is published in spreadsheet formats that are:

- **Inconsistent**: Varying formats across states and districts
- **Non-relational**: No built-in hierarchy enforcement or referential integrity
- **Difficult to query**: Manual lookup processes without API access
- **Unvalidated**: Duplicate entries, orphaned records, and coding errors

Organizations requiring village-level data for service delivery, logistics planning, or demographic analysis face significant engineering overhead in normalizing and maintaining this data independently.

## 2.2 Primary Objectives

1. **Data Normalization**: Develop an automated pipeline to import census spreadsheets and normalize them into a relational schema with enforced hierarchy (Country → State → District → Sub-District → Village).

2. **API Infrastructure**: Build a production-ready REST API with:
   - JWT-based authentication for admin and client roles
   - API key/secret credential model for programmatic access
   - Multi-tier rate limiting (burst + daily quotas)
   - Comprehensive request logging and analytics

3. **Client Management**: Implement a self-service portal for:
   - Business registration and account activation
   - API key creation, rotation, and revocation
   - Real-time usage dashboards with quota visibility

4. **Administrative Oversight**: Provide operational tools for:
   - Client approval workflows
   - Plan and status management
   - Platform-wide analytics and health monitoring

5. **Data Quality Assurance**: Create validation utilities to verify:
   - Referential integrity across hierarchy levels
   - Absence of duplicate codes within parent entities
   - Complete coverage of expected villages

## 2.3 Secondary Objectives

- Support multiple spreadsheet formats (XLS, XLSX, ODS) via pandas
- Enable incremental data updates without full re-imports
- Provide cached responses for frequently accessed endpoints
- Generate interactive data visualizations for usage patterns

---

# 3. WORKING MODULES AND IMPLEMENTED FEATURES

## 3.1 Data Import Module (`scripts/import_to_postgres.py`)

**Purpose**: Import raw census spreadsheets into staging tables for normalization.

**Features**:
- Scans dataset directory for supported file formats (.xls, .xlsx, .ods)
- Parses state metadata from filename pattern `Rdir_2011_{code}_{name}`
- Reads all sheets from each workbook using pandas
- Stores raw row data as JSONB with hash-based deduplication
- Batch inserts with configurable batch size (default: 1000 rows)
- Tracks import file metadata for audit purposes

**Key Functions**:
- `read_workbook(path)`: Extracts all sheets and rows from spreadsheet files
- `row_hash(row_data)`: Generates SHA-256 hash for change detection
- `insert_rows(connection, rows, batch_size)`: Efficient batch insertion using `execute_values`

## 3.2 Geography Normalization Module (`scripts/normalize_geography.py`)

**Purpose**: Transform imported raw data into normalized API tables.

**Features**:
- Extracts unique states, districts, sub-districts, and villages from import_rows
- Builds hierarchical relationships via foreign key joins
- Generates search-optimized fields (search_name with lowercase normalization)
- Constructs display_name for villages with full hierarchical context
- Uses UPSERT semantics (ON CONFLICT DO UPDATE) for idempotent re-runs
- Selects one canonical row per state/district/sub-district/village code path
  before upsert so duplicate source rows do not trigger PostgreSQL cardinality
  errors
- Supports full dataset refresh with TRUNCATE CASCADE option

**Data Transformation Logic**:
- **States**: Extracted from rows where district code = '000', sub-district = '00000', village = '000000'
- **Districts**: Extracted where sub-district = '00000', village = '000000' (non-zero district code)
- **Sub-Districts**: Extracted where village = '000000' (non-zero sub-district code)
- **Villages**: All rows with non-zero village code; cleans parenthetical suffixes from names

## 3.3 Data Verification Module (`scripts/verify_geography.py`)

**Purpose**: Validate data integrity after normalization.

**Features**:
- Reports row counts for all hierarchy tables
- Checks for orphaned records (child without parent)
- Detects duplicate codes within scoping parent
- Displays sample hierarchy path for manual verification

**Validation Checks**:
- States without country reference
- Districts without state reference
- Sub-districts without district reference
- Villages without sub-district reference
- Duplicate state/district/sub-district/village codes

## 3.4 SaaS Setup Module (`scripts/setup_saas.py`)

**Purpose**: Initialize SaaS database schema and admin user.

**Features**:
- Executes SQL schema creation statements
- Adds optional columns for backward compatibility
- Creates initial admin user with hashed password
- Sets default status values for existing records

## 3.5 API Client Module (`scripts/create_api_client.py`)

**Purpose**: Create API client accounts with credentials.

**Features**:
- Creates api_clients record with specified plan
- Generates API key (ak_*) and secret (as_*) credentials
- Stores SHA-256 hashes of credentials (not plaintext)
- Returns plaintext credentials for one-time display

## 3.6 Demo Portal Seed Module (`scripts/seed_demo_portal.py`)

**Purpose**: Prepare a clean, approved B2B portal account for academic frontend demonstrations.

**Features**:
- Creates or updates `demo@bluestock.local` with password `Demo12345`
- Sets the demo account to `active` on the `unlimited` plan
- Creates one active API key and one revoked legacy key
- Seeds 14 days of realistic `api_usage_events`
- Populates endpoint mix data for search, autocomplete, villages, states, and districts
- Can be rerun to reset the demo account to a clean presentation state

## 3.7 FastAPI Backend (`app/main.py`)

**Purpose**: Serve REST API endpoints with authentication and rate limiting.

**Implemented Endpoints**:

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/health` | GET | None | System health check |
| `/auth/register` | POST | None | Client registration |
| `/auth/client-login` | POST | None | Client authentication |
| `/admin/login` | POST | None | Admin authentication |
| `/portal/me` | GET | Client JWT | Current client profile |
| `/portal/api-keys` | GET | Client JWT | List API keys |
| `/portal/api-keys` | POST | Client JWT | Create API key |
| `/portal/api-keys/{id}/rotate-secret` | POST | Client JWT | Rotate API secret |
| `/portal/api-keys/{id}` | DELETE | Client JWT | Revoke API key |
| `/portal/usage` | GET | Client JWT | Usage analytics |
| `/admin/summary` | GET | Admin JWT | Platform summary |
| `/admin/clients` | GET | Admin JWT | Client list |
| `/admin/clients/{id}/approve` | POST | Admin JWT | Approve client |
| `/admin/clients/{id}/suspend` | POST | Admin JWT | Suspend client |
| `/admin/clients/{id}` | PATCH | Admin JWT | Update client |
| `/admin/analytics` | GET | Admin JWT | Platform analytics |
| `/admin/villages` | GET | Admin JWT | Village browser |
| `/admin/api-logs` | GET | Admin JWT | Usage logs |
| `/admin/api-logs/export.csv` | GET | Admin JWT | Export logs |
| `/v1/states` | GET | API Key | List states |
| `/v1/districts` | GET | API Key | List districts |
| `/v1/sub-districts` | GET | API Key | List sub-districts |
| `/v1/villages` | GET | API Key | List villages |
| `/v1/autocomplete` | GET | API Key | Village autocomplete |
| `/v1/search` | GET | API Key | Hierarchical search |

**Core Features**:
- **JWT Authentication**: HS256-signed tokens with role claims (admin/client)
- **PBKDF2 Password Hashing**: 120,000 iterations with random salt
- **API Key Authentication**: Dual-secret model (key + secret) for write operations
- **Rate Limiting**: Redis-based counters (fallback to in-memory deques)
- **Usage Logging**: All requests logged to api_usage_events table
- **Response Headers**: X-Request-ID, X-RateLimit-*, security headers
- **Error Handling**: Structured error responses with error codes
- **Caching**: Optional Redis caching for read-heavy endpoints

## 3.7 React Frontend (`frontend/`)

**Purpose**: Admin dashboard and client portal interfaces.

**Components**:
- `App.tsx`: Main shell with sidebar navigation
- `AdminDashboard.tsx`: Admin operations console
- `Portal.tsx`: Client self-service portal
- `Charts.tsx`: Recharts visualizations (area, bar, pie, line charts)
- `StatusPill.tsx`: Status indicator component
- `api/client.ts`: API client with TanStack Query integration
- `store/auth.ts`: Zustand-based authentication state

**Features**:
- Token persistence in localStorage
- Automatic query refetch on mutation
- Form-based authentication flows
- Interactive usage analytics dashboards
- API key credential display with copy-to-clipboard

---

# 4. FRONTEND MODULE EXPLANATION

## 4.1 Application Architecture

The frontend is built with **React 18**, **TypeScript**, and **Vite**, following a component-based architecture with centralized state management.

### 4.1.1 Entry Point (`main.tsx`)

```typescript
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>
);
```

The application initializes:
- A `QueryClient` instance for TanStack Query with retry=1 and no refetch on window focus
- React.StrictMode for development warnings
- QueryClientProvider context for global query state

### 4.1.2 Main App Component (`App.tsx`)

The root component manages:
- **View state**: Toggle between "admin" and "portal" views
- **Authentication**: Reads tokens from Zustand store
- **Health monitoring**: Queries `/health` endpoint for integration status
- **Navigation**: Sidebar with Admin Dashboard and B2B Portal options

Sidebar displays integration status:
- API connectivity status
- Redis connection status
- Feature completion indicators

### 4.1.3 Authentication Store (`store/auth.ts`)

Uses **Zustand** for lightweight state management:

```typescript
type AuthState = {
  adminToken: string;
  portalToken: string;
  setToken: (role: Role, token: string) => void;
  logout: (role: Role) => void;
};
```

Features:
- Persistent storage in localStorage
- Separate tokens for admin and portal roles
- Synchronized state updates across components

### 4.1.4 API Client (`api/client.ts`)

Type-safe API wrapper with:

```typescript
async function request<T>(path: string, options: RequestOptions = {}): Promise<T>
```

Features:
- Automatic JSON parsing based on Content-Type header
- Error extraction from response bodies
- Bearer token injection for authenticated requests
- TypeScript generics for return type safety

### 4.1.5 Admin Dashboard (`pages/AdminDashboard.tsx`)

**Authentication View**:
- Email/password form with default admin email pre-filled
- Error display for failed login attempts
- Token storage on successful authentication

**Dashboard View** (post-login):
- **Summary Metrics Grid**: Displays platform statistics (clients, API keys, requests, latency, geography counts)
- **Analytics Charts**:
  - Requests Over Time (30-day area chart)
  - Users By Plan (pie chart)
  - Top States By Village Count (horizontal bar chart)
  - Endpoint Usage (bar chart)
  - Response-Time Trends (line chart with avg/max)
- **Client Management Table**:
  - Client name, email, plan, status
  - API key count, total requests, average latency
  - Action buttons: Approve, Suspend

**Data Fetching**:
- Uses TanStack Query for all data fetching
- Manual refresh button to invalidate queries
- Mutations for client actions with automatic refetch

### 4.1.6 Client Portal (`pages/Portal.tsx`)

**Authentication View**:
- Segmented control for Login/Register toggle
- Demo login helper displaying the approved local demo credentials
- Registration form fields: Name, Business, Plan, GST, Phone, Email, Password
- Login form: Email, Password
- Friendly validation, approval, and request error display without raw JSON output

**Portal View** (post-login):
- **Account Metrics**:
  - Account name, status, daily limit, 24h requests
- Approval banner for newly registered accounts still awaiting admin approval
- **API Key Management**:
  - Create key button
  - Credential display box with copy-to-clipboard
  - Keys table: Name, Prefix, Status, Created, Last Used, Actions
  - Actions: Rotate secret, Revoke key
  - Success notices for create, rotate, and revoke actions
- **Usage Analytics**:
  - Daily usage area chart (14-day history)
  - Endpoint mix bar chart
  - Empty-state messaging for accounts with no usage yet

**Key Lifecycle**:
1. Create: Generates new key/secret pair, displays secret one-time
2. Rotate: Generates new secret for existing key
3. Revoke: Sets is_active=FALSE, preventing further use
4. Demo portal actions log lightweight usage events so 24h metrics and charts
   visibly update during the presentation

### 4.1.7 Chart Components (`components/Charts.tsx`)

Reusable chart components using **Recharts**:

- **RequestsArea**: Area chart for request volume over time
- **StateBar**: Horizontal bar chart for state-level aggregation
- **PlansPie**: Pie chart for plan distribution
- **ResponseTimeLine**: Dual-line chart for avg/max latency trends
- **EndpointBar**: Bar chart for endpoint usage distribution

All charts use:
- ResponsiveContainer for fluid layouts
- Consistent styling (colors, fonts, grid lines)
- Tooltip for data point inspection

### 4.1.8 Styling (`styles.css`)

CSS architecture:
- **CSS Variables**: Minimal; uses hardcoded design tokens
- **Utility Classes**: `.stack`, `.panel`, `.metric`, `.actions`
- **Component Classes**: `.app-shell`, `.sidebar`, `.login-card`
- **Responsive Design**: Single breakpoint at 860px for mobile

Color Palette:
- Primary: `#2563eb` (blue-600)
- Background: `#f8fafc` (slate-50)
- Sidebar: `#0f172a` (slate-900)
- Text: `#111827` (gray-900), `#64748b` (slate-500)

---

# 5. BACKEND / DATABASE ARCHITECTURE

## 5.1 Database Schema

### 5.1.1 Geography Tables

**countries**
```sql
CREATE TABLE countries (
  id SMALLSERIAL PRIMARY KEY,
  code CHAR(2) NOT NULL UNIQUE,
  name VARCHAR(128) NOT NULL UNIQUE,
  created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
```

**states**
```sql
CREATE TABLE states (
  id SERIAL PRIMARY KEY,
  country_id SMALLINT REFERENCES countries(id),
  code VARCHAR(8) NOT NULL UNIQUE,
  name VARCHAR(255) NOT NULL,
  search_name VARCHAR(255) NOT NULL,
  created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_states_country_name ON states(country_id, search_name);
```

**districts**
```sql
CREATE TABLE districts (
  id SERIAL PRIMARY KEY,
  state_id INTEGER REFERENCES states(id),
  code VARCHAR(8) NOT NULL,
  name VARCHAR(255) NOT NULL,
  search_name VARCHAR(255) NOT NULL,
  created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(state_id, code)
);
CREATE INDEX ix_districts_state_name ON districts(state_id, search_name);
```

**sub_districts**
```sql
CREATE TABLE sub_districts (
  id SERIAL PRIMARY KEY,
  district_id INTEGER REFERENCES districts(id),
  code VARCHAR(16) NOT NULL,
  name VARCHAR(255) NOT NULL,
  search_name VARCHAR(255) NOT NULL,
  created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(district_id, code)
);
CREATE INDEX ix_sub_districts_district_name ON sub_districts(district_id, search_name);
```

**villages**
```sql
CREATE TABLE villages (
  id BIGSERIAL PRIMARY KEY,
  sub_district_id INTEGER REFERENCES sub_districts(id),
  code VARCHAR(16) NOT NULL,
  name VARCHAR(255) NOT NULL,
  display_name VARCHAR(1024) NOT NULL,
  search_name VARCHAR(255) NOT NULL,
  created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(sub_district_id, code)
);
CREATE INDEX ix_villages_sub_district_name ON villages(sub_district_id, search_name);
CREATE INDEX ix_villages_search_name ON villages(search_name);
CREATE INDEX ix_villages_name_trgm ON villages USING GIN (search_name gin_trgm_ops);
```

### 5.1.2 SaaS Tables

**api_clients**
```sql
CREATE TABLE api_clients (
  id BIGSERIAL PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  email VARCHAR(255) NOT NULL UNIQUE,
  business_name VARCHAR(255),
  gst_number VARCHAR(32),
  phone VARCHAR(32),
  password_hash VARCHAR(255),
  plan VARCHAR(32) DEFAULT 'free',
  status VARCHAR(32) DEFAULT 'pending_approval',
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_api_clients_status_plan ON api_clients(status, plan);
```

**api_keys**
```sql
CREATE TABLE api_keys (
  id BIGSERIAL PRIMARY KEY,
  client_id BIGINT REFERENCES api_clients(id),
  name VARCHAR(120) DEFAULT 'Default',
  key_prefix VARCHAR(16) NOT NULL,
  key_hash CHAR(64) NOT NULL UNIQUE,
  secret_hash CHAR(64) NOT NULL,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
  last_used_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ
);
CREATE INDEX ix_api_keys_client ON api_keys(client_id);
```

**api_usage_events**
```sql
CREATE TABLE api_usage_events (
  id BIGSERIAL PRIMARY KEY,
  client_id BIGINT REFERENCES api_clients(id),
  api_key_id BIGINT REFERENCES api_keys(id),
  endpoint VARCHAR(255) NOT NULL,
  status_code SMALLINT NOT NULL,
  latency_ms INTEGER NOT NULL,
  ip_address VARCHAR(64),
  created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_api_usage_client_time ON api_usage_events(client_id, created_at);
CREATE INDEX ix_api_usage_key_time ON api_usage_events(api_key_id, created_at);
CREATE INDEX ix_api_usage_endpoint_time ON api_usage_events(endpoint, created_at);
```

**admin_users**
```sql
CREATE TABLE admin_users (
  id BIGSERIAL PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  email VARCHAR(255) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
```

### 5.1.3 Import Tracking Tables

**import_files**
```sql
CREATE TABLE import_files (
  id BIGSERIAL PRIMARY KEY,
  file_name VARCHAR(255) NOT NULL,
  file_path VARCHAR(768) NOT NULL UNIQUE,
  state_code VARCHAR(8),
  state_name VARCHAR(255),
  file_extension VARCHAR(16),
  imported_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
```

**import_rows**
```sql
CREATE TABLE import_rows (
  id BIGSERIAL PRIMARY KEY,
  import_file_id BIGINT REFERENCES import_files(id) ON DELETE CASCADE,
  sheet_name VARCHAR(255) NOT NULL,
  source_row_number INTEGER NOT NULL,
  row_hash CHAR(64) NOT NULL,
  row_data JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(import_file_id, sheet_name, source_row_number)
);
CREATE INDEX ix_import_rows_hash ON import_rows(row_hash);
```

## 5.2 Connection Pooling

The backend uses **psycopg2 connection pools**:

```python
connection_pool = pool.SimpleConnectionPool(
    minconn=1,
    maxconn=int(os.getenv("POSTGRES_POOL_SIZE", "10")),
    dsn=database_url(),
)
```

Features:
- Configurable pool size via environment variable
- Automatic connection reuse via context manager
- Thread-safe connection acquisition

## 5.3 Caching Layer

Optional **Redis caching** for read-heavy endpoints:

```python
def cache_get(key: str) -> Any | None:
    client = get_redis_client()
    if not client:
        return None
    value = client.get(key)
    return json.loads(value) if value else None

def cache_set(key: str, value: Any, ttl_seconds: int = 300) -> None:
    client = get_redis_client()
    if not client:
        return
    client.setex(key, ttl_seconds, json.dumps(value, default=str))
```

Cache keys:
- `v1:states`: Full state list (1 hour TTL)
- `v1:districts:{state_id}`: Districts by state (30 min TTL)
- `v1:villages:{sub_district_id}:{q}:{limit}:{offset}`: Paginated villages (10 min TTL)

Fallback: If Redis is unavailable, caching is silently skipped.

## 5.4 Rate Limiting

### 5.4.1 Plan Configuration

```python
PLAN_LIMITS = {
    "free": {"daily": 5000, "burst": 100},
    "premium": {"daily": 50000, "burst": 500},
    "pro": {"daily": 300000, "burst": 2000},
    "unlimited": {"daily": 1000000, "burst": 5000},
}
```

### 5.4.2 Redis-Based Rate Limiting

```python
minute_key = f"rate:minute:{client['api_key_id']}:{int(now // 60)}"
daily_key = f"rate:day:{client['api_key_id']}:{utcnow().date().isoformat()}"

minute_count = redis_conn.incr(minute_key)
daily_count = redis_conn.incr(daily_key)

if minute_count > limits["burst"]:
    raise HTTPException(status_code=429, detail="Rate limit exceeded")
if daily_count > limits["daily"]:
    raise HTTPException(status_code=429, detail="Daily quota exceeded")
```

### 5.4.3 In-Memory Fallback

```python
window = rate_windows[int(client["api_key_id"])]
while window and now - window[0] >= 60:
    window.popleft()
if len(window) >= limit:
    raise HTTPException(status_code=429, detail="Rate limit exceeded")
window.append(now)
```

## 5.5 Authentication Flow

### 5.5.1 Password Hashing

```python
def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    iterations = 120000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"
```

### 5.5.2 JWT Token Structure

```python
def create_token(subject: str, role: str, expires_hours: int = 12) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": subject,
        "role": role,
        "exp": (datetime.now(timezone.utc) + timedelta(hours=expires_hours)).timestamp(),
    }
    # HS256 signature
```

Token format: `header.payload.signature` (base64url encoded)

### 5.5.3 API Key Authentication

```python
def authenticated_client(request, x_api_key, x_api_secret):
    key_hash = sha256(x_api_key)
    require_secret = request.method not in {"GET", "HEAD", "OPTIONS"}

    # Verify key hash and optional secret
    client = fetch_one("""
        SELECT ak.id, c.id, c.plan, c.status
        FROM api_keys ak
        JOIN api_clients c ON c.id = ak.client_id
        WHERE ak.key_hash = %s AND ak.is_active = TRUE AND c.status = 'active'
    """, (key_hash,))
```

---

# 6. CODE LOGIC AND SYSTEM DESIGN

## 6.1 Data Import Pipeline

### 6.1.1 Workflow

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Spreadsheet    │────▶│  import_rows     │────▶│  Normalized     │
│  (XLS/XLSX/ODS) │     │  (JSONB staging) │     │  API Tables     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

### 6.1.2 Row Hashing for Deduplication

```python
def row_hash(row_data: dict) -> str:
    payload = json.dumps(row_data, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

Purpose: Detect changes in source data for incremental updates.

### 6.1.3 Batch Insertion

```python
def insert_rows(connection, rows: list[tuple], batch_size: int) -> int:
    sql = """
        INSERT INTO import_rows
          (import_file_id, sheet_name, source_row_number, row_hash, row_data)
        VALUES %s
        ON CONFLICT (import_file_id, sheet_name, source_row_number) DO UPDATE SET
          row_hash = EXCLUDED.row_hash,
          row_data = EXCLUDED.row_data
    """
    for batch in batched(rows, batch_size):
        execute_values(cursor, sql, batch)
```

Uses psycopg2's `execute_values` for efficient batch inserts.

## 6.2 Geography Normalization Logic

### 6.2.1 Hierarchy Extraction

The normalization SQL uses pattern matching on census codes:

- **State level**: District=000, SubDistrict=00000, Village=000000
- **District level**: State≠000, District≠000, SubDistrict=00000, Village=000000
- **Sub-District level**: Village=000000 (non-zero higher levels)
- **Village level**: All codes non-zero

### 6.2.2 Name Cleaning

```sql
TRIM(REGEXP_REPLACE(village_name, '[[:space:]]*\([0-9]+\)[[:space:]]*$', ''))
```

Removes parenthetical census codes from village names.

### 6.2.3 Display Name Construction

```sql
CONCAT(village_name, ', ', sub_district_name, ', ', district_name, ', ', state_name, ', India')
```

Creates human-readable full addresses for dropdown displays.

## 6.3 Rate Limiting Decision Tree

```
Request arrives
    │
    ▼
Is Redis available?
    ├── Yes ──▶ Check Redis counters (minute + daily)
    │           ├── Exceeded? ──▶ 429 Too Many Requests
    │           └── OK ──▶ Increment counters, proceed
    │
    └── No ───▶ Check in-memory deque
                ├── Window full? ──▶ 429 Too Many Requests
                └── OK ──▶ Append timestamp, check daily quota
```

## 6.4 Usage Logging Middleware

```python
@app.middleware("http")
async def usage_logging(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        latency_ms = int((time.perf_counter() - start) * 1000)
        log_usage(client, request.url.path, response, latency_ms, ip_address)
```

Logs every authenticated request with:
- Client ID and API key ID
- Endpoint path
- Response status code
- Latency in milliseconds
- Client IP address (masked in admin views)

## 6.5 Response Standardization

All API responses follow a consistent structure:

```python
def api_success(request, response, data, count=None):
    return {
        "success": True,
        "count": count or len(data) if isinstance(data, list) else 1,
        "data": data,
        "meta": {
            "requestId": request_id,
            "responseTime": latency_ms,
            "rateLimit": {
                "remaining": remaining,
                "limit": daily_limit,
                "reset": reset_iso,
            },
        },
    }
```

Error responses:

```python
def api_error(request, status_code, code, message):
    return {
        "success": False,
        "error": {"code": code, "message": message},
        "meta": {
            "requestId": request_id,
            "responseTime": latency_ms,
        },
    }
```

---

# 7. TECHNOLOGIES USED

## 7.1 Backend Technologies

| Technology | Version | Purpose |
|------------|---------|---------|
| Python | 3.x | Primary language |
| FastAPI | 0.115.6 | Web framework |
| Uvicorn | 0.34.0 | ASGI server |
| Pydantic | 2.10.4 | Data validation |
| psycopg2-binary | 2.9.10 | PostgreSQL driver |
| Redis | 5.2.1 | Rate limiting cache |
| python-dotenv | 1.0.1 | Environment configuration |
| pandas | 2.2.3 | Spreadsheet processing |
| xlrd | 2.0.1 | Excel file parsing |
| odfpy | 1.4.1 | ODS file parsing |
| email-validator | 2.2.0 | Email validation |

## 7.2 Frontend Technologies

| Technology | Version | Purpose |
|------------|---------|---------|
| React | 18.3.1 | UI framework |
| TypeScript | 5.6.3 | Type safety |
| Vite | 5.4.10 | Build tool |
| TanStack Query | 5.59.16 | Data fetching |
| Zustand | 5.0.1 | State management |
| Recharts | 2.13.3 | Data visualization |
| Lucide React | 0.468.0 | Icon library |

## 7.3 Database & Infrastructure

| Technology | Purpose |
|------------|---------|
| PostgreSQL | Primary database |
| Redis | Rate limiting cache |
| Prisma | Optional ORM for future expansion |

## 7.4 Development Tools

| Tool | Purpose |
|------|---------|
| Git | Version control |
| npm | Package management |
| Bash scripts | Data import automation |

---

# 8. CHALLENGES FACED

## 8.1 Data Quality Challenges

**Problem**: Census spreadsheet data contained inconsistencies:
- Village names with parenthetical suffixes (e.g., "Ramnagar (123)")
- Inconsistent capitalization and whitespace
- Orphaned records referencing non-existent parent entities

**Solution**: 
- Implemented regex-based name cleaning during normalization
- Added search_name field with lowercase normalization
- Created verification script to detect orphans and duplicates
- Used UPSERT semantics to handle re-runs gracefully

## 8.2 Rate Limiting Without Redis

**Problem**: Redis may not be available in all deployment environments.

**Solution**: 
- Implemented dual-mode rate limiting:
  - Redis-based counters when available
  - In-memory deques as fallback
- Graceful degradation without errors
- Consistent 429 responses regardless of backend

## 8.3 API Key Security

**Problem**: Storing API secrets securely while enabling verification.

**Solution**: 
- Store only SHA-256 hashes of API key and secret
- Display plaintext credentials only once at creation
- Require secret only for write operations (GET is key-only)
- Key prefix stored in plaintext for identification

## 8.4 Large Dataset Performance

**Problem**: Importing 600,000+ villages efficiently.

**Solution**: 
- Batch inserts with configurable batch size
- psycopg2's execute_values for bulk operations
- JSONB storage for raw import data
- Indexes on foreign keys and search fields

## 8.5 Frontend State Synchronization

**Problem**: Keeping UI state consistent after mutations.

**Solution**: 
- TanStack Query's invalidation API
- Automatic refetch after successful mutations
- Optimistic UI updates where appropriate

---

# 9. PENDING WORK / FUTURE IMPROVEMENTS

## 9.1 Geography API Enhancements

- [ ] Add PIN code integration if source data becomes available
- [ ] Implement fuzzy search for typo tolerance
- [ ] Add GeoJSON output format for map integrations
- [ ] Support batch lookups (multiple IDs in single request)

## 9.2 SaaS Platform Features

- [ ] Email verification for new client registrations
- [ ] Password reset flow via email
- [ ] Two-factor authentication for admin accounts
- [ ] API key expiration with automatic renewal reminders
- [ ] Usage alerts when approaching quota limits

## 9.3 Analytics Improvements

- [ ] Real-time dashboard with WebSocket updates
- [ ] Custom date range selectors for analytics
- [ ] Export analytics to CSV/PDF
- [ ] Cohort analysis for client retention
- [ ] Geographic heat maps of API usage

## 9.4 Infrastructure

- [ ] Docker Compose configuration for local development
- [ ] Kubernetes manifests for production deployment
- [ ] CI/CD pipeline with automated testing
- [ ] Database migration system (Alembic)
- [ ] Health check endpoints for load balancers

## 9.5 Documentation

- [ ] Interactive API documentation (OpenAPI/Swagger)
- [ ] Client SDK libraries (Python, JavaScript, Java)
- [ ] Rate limit best practices guide
- [ ] Data dictionary for geography schema

---

# 10. CONCLUSION

BlueStock successfully delivers a production-ready B2B SaaS platform for village-level geographical data access. The system addresses the core challenges of data normalization, API infrastructure, and client management through a well-architected combination of FastAPI, PostgreSQL, Redis, and React.

## Key Achievements

1. **Data Pipeline**: Automated import and normalization of census spreadsheets into a relational schema with 5-tier hierarchy enforcement.

2. **API Platform**: Full-featured REST API with JWT authentication, API key management, multi-tier rate limiting, and comprehensive usage logging.

3. **Client Experience**: Self-service portal for API key lifecycle management with real-time usage visibility.

4. **Operational Tools**: Admin dashboard for client approvals, plan management, and platform analytics.

5. **Data Quality**: Verification utilities ensuring referential integrity and absence of duplicates.

## Technical Highlights

- **Scalability**: Redis-based rate limiting with in-memory fallback
- **Security**: PBKDF2 password hashing, SHA-256 credential storage, JWT tokens
- **Performance**: Connection pooling, query caching, batch operations
- **Observability**: Request ID tracing, latency tracking, structured logging

## Lessons Learned

1. **Data cleaning is iterative**: Initial imports revealed edge cases requiring regex refinement.
2. **Graceful degradation matters**: Redis fallback ensures functionality in resource-constrained environments.
3. **Type safety pays off**: TypeScript caught numerous bugs during frontend development.
4. **Testing data pipelines is hard**: Verification scripts became essential for confidence in normalization.

The platform is positioned for production deployment with clear pathways for feature expansion and scaling.

---

# APPENDIX A: QUICK START GUIDE

## Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL 14+
- Redis (optional)

## Backend Setup

```bash
# Install Python dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your DATABASE_URL and other settings

# Create database schema
python scripts/setup_saas.py

# Import geography data
python scripts/import_to_postgres.py --dataset-dir ./dataset --create-schema --replace

# Normalize geography
python scripts/normalize_geography.py --create-schema --replace

# Verify data
python scripts/verify_geography.py

# Seed approved B2B portal demo account and analytics
python scripts/seed_demo_portal.py

# Start server
uvicorn app.main:app --reload --port 8000
```

Demo portal login for presentations:

- Email: `demo@bluestock.local`
- Password: `Demo12345`

## Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

## Create Test Client

```bash
python scripts/create_api_client.py --name "Test Client" --email "test@example.com" --plan "unlimited"
```

---

# APPENDIX B: API REFERENCE SUMMARY

## Authentication Endpoints

| Endpoint | Method | Body | Response |
|----------|--------|------|----------|
| `/auth/register` | POST | `{name, email, password, business_name, plan, gst_number, phone}` | `{token, status, client_id}` |
| `/auth/client-login` | POST | `{email, password}` | `{token}` |
| `/admin/login` | POST | `{email, password}` | `{token}` |

## Portal Endpoints (Client JWT)

| Endpoint | Method | Response |
|----------|--------|----------|
| `/portal/me` | GET | `{client, plan_limits, usage}` |
| `/portal/api-keys` | GET | `[{id, name, key_prefix, is_active, created_at, last_used_at}]` |
| `/portal/api-keys` | POST | `{api_key, api_secret}` |
| `/portal/api-keys/{id}/rotate-secret` | POST | `{api_secret}` |
| `/portal/api-keys/{id}` | DELETE | `{revoked: true}` |
| `/portal/usage` | GET | `{daily, endpoints}` |

## Admin Endpoints (Admin JWT)

| Endpoint | Method | Response |
|----------|--------|----------|
| `/admin/summary` | GET | `{summary, plans}` |
| `/admin/clients` | GET | `[{id, name, email, plan, status, api_keys, total_requests}]` |
| `/admin/clients/{id}/approve` | POST | `{approved: true}` |
| `/admin/clients/{id}/suspend` | POST | `{suspended: true}` |
| `/admin/clients/{id}` | PATCH | `{updated: true}` |
| `/admin/analytics` | GET | `{top_states, requests_30d, plans, endpoints, hourly, response_times}` |
| `/admin/api-logs` | GET | `[{created_at, api_key, client_name, endpoint, response_time_ms, status_code}]` |

## Geography Endpoints (API Key)

| Endpoint | Method | Query Params | Response |
|----------|--------|--------------|----------|
| `/v1/states` | GET | - | `[{id, code, name}]` |
| `/v1/districts` | GET | `state_id`, `state_code` | `[{id, code, name, state_id, state_name}]` |
| `/v1/sub-districts` | GET | `district_id`, `district_code` | `[{id, code, name, district_id, state_id}]` |
| `/v1/villages` | GET | `sub_district_id`, `q`, `limit`, `offset` | `[{value, label, fullAddress, hierarchy}]` |
| `/v1/autocomplete` | GET | `q`, `state_id`, `limit` | `[{value, label, fullAddress, hierarchy}]` |
| `/v1/search` | GET | `q`, `state`, `district`, `subDistrict`, `limit` | `[{value, label, fullAddress, hierarchy}]` |

---

*Document generated for academic submission purposes.*
*BlueStock Project - Version 1.0*
