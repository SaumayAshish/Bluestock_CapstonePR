# BlueStock Project - Abstract and Architecture
## For Evaluator Review

---

# ABSTRACT

**BlueStock** is a production-ready B2B SaaS platform that provides standardized, village-level geographical data APIs for India. The system addresses the fundamental challenge of accessing hierarchical location data (State → District → Sub-District → Village) through a secure, rate-limited REST API infrastructure.

The platform consists of three integrated components:

1. **Data Pipeline**: Automated import and normalization of government census spreadsheets (XLS/XLSX/ODS formats) into a PostgreSQL database with referential integrity enforcement across five hierarchy levels.

2. **FastAPI Backend**: A production REST API (~1,500 lines) implementing JWT-based authentication, dual-secret API key credentials, Redis-based rate limiting with multi-tier quotas (Free/Premium/Pro/Unlimited), comprehensive usage logging, and optional response caching.

3. **React Frontend**: Dual-dashboard architecture comprising an Admin Dashboard for client management and platform analytics, and a Client Portal for self-service API key lifecycle management and real-time usage monitoring.

Key technical achievements include:
- Support for India's 600,000+ villages with sub-second query response times
- Graceful degradation when Redis is unavailable (in-memory rate limiting fallback)
- Secure credential storage using PBKDF2 password hashing and SHA-256 API secret hashes
- Real-time analytics dashboards powered by TanStack Query and Recharts
- Comprehensive data validation utilities ensuring referential integrity

The system is deployment-ready with environment-based configuration, connection pooling, structured error responses, and security headers. All core features specified in the requirements are fully implemented and functional.

**Keywords**: SaaS Platform, REST API, FastAPI, React, PostgreSQL, Rate Limiting, JWT Authentication, Data Normalization, Geographic Information Systems

---

# SYSTEM ARCHITECTURE

## 1. High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                               │
│  ┌─────────────────────────────┐  ┌─────────────────────────────────┐  │
│  │     Admin Dashboard         │  │       Client Portal             │  │
│  │   (React + TypeScript)      │  │    (React + TypeScript)         │  │
│  │   - Client management       │  │    - API key management         │  │
│  │   - Platform analytics      │  │    - Usage monitoring           │  │
│  │   - Approval workflows      │  │    - Self-service registration  │  │
│  └──────────────┬──────────────┘  └───────────────┬─────────────────┘  │
│                 │                                   │                    │
│                 └───────────────┬───────────────────┘                    │
│                                 │                                        │
│                          ┌──────▼──────┐                                 │
│                          │  API Client │                                 │
│                          │  (TanStack  │                                 │
│                          │   Query)    │                                 │
│                          └──────┬──────┘                                 │
└─────────────────────────────────┼────────────────────────────────────────┘
                                  │ HTTP/HTTPS
┌─────────────────────────────────▼────────────────────────────────────────┐
│                         APPLICATION LAYER                                │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │                    FastAPI Backend (app/main.py)                   │  │
│  │  ┌──────────────────────────────────────────────────────────────┐  │  │
│  │  │  Authentication Middleware                                   │  │  │
│  │  │  - JWT validation (admin/client roles)                       │  │  │
│  │  │  - API key/secret verification                               │  │  │
│  │  │  - PBKDF2 password hashing                                   │  │  │
│  │  └──────────────────────────────────────────────────────────────┘  │  │
│  │  ┌──────────────────────────────────────────────────────────────┐  │  │
│  │  │  Rate Limiting Layer                                         │  │  │
│  │  │  - Redis counters (primary)                                  │  │  │
│  │  │  - In-memory deques (fallback)                               │  │  │
│  │  │  - Plan-based quotas (burst + daily)                         │  │  │
│  │  └──────────────────────────────────────────────────────────────┘  │  │
│  │  ┌──────────────────────────────────────────────────────────────┐  │  │
│  │  │  Request Handlers                                            │  │  │
│  │  │  - /auth/*    (registration, login)                          │  │  │
│  │  │  - /admin/*   (client management, analytics)                 │  │  │
│  │  │  - /portal/*  (API keys, usage)                              │  │  │
│  │  │  - /v1/*      (geography API)                                │  │  │
│  │  └──────────────────────────────────────────────────────────────┘  │  │
│  │  ┌──────────────────────────────────────────────────────────────┐  │  │
│  │  │  Usage Logging Middleware                                    │  │  │
│  │  │  - Logs all requests to api_usage_events                     │  │  │
│  │  │  - Tracks latency, status code, IP address                   │  │  │
│  │  └──────────────────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │ psycopg2
┌─────────────────────────────────▼────────────────────────────────────────┐
│                          DATA LAYER                                      │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │                      PostgreSQL Database                           │  │
│  │                                                                    │  │
│  │  Geography Schema:                                                 │  │
│  │  ┌──────────┐    ┌─────────┐    ┌───────────┐    ┌─────────────┐  │  │
│  │  │ countries│───▶│ states  │───▶│ districts │───▶│sub_districts│  │  │
│  │  └──────────┘    └─────────┘    └───────────┘    └──────┬──────┘  │  │
│  │                                                         │           │  │
│  │                                                         ▼           │  │
│  │                                                   ┌───────────┐     │  │
│  │                                                   │ villages  │     │  │
│  │                                                   └───────────┘     │  │
│  │                                                                    │  │
│  │  SaaS Schema:                                                      │  │
│  │  ┌──────────────┐    ┌───────────┐    ┌───────────────────┐        │  │
│  │  │ admin_users  │    │api_clients│───▶│    api_keys       │        │  │
│  │  └──────────────┘    └─────────────┘    └────────┬──────────┘        │  │
│  │                                                  │                   │  │
│  │                                                  ▼                   │  │
│  │                                          ┌────────────────┐          │  │
│  │                                          │api_usage_events│          │  │
│  │                                          └────────────────┘          │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │                         Redis (Optional)                           │  │
│  │  - Rate limit counters (minute/hour/daily)                         │  │
│  │  - API response cache (TTL-based)                                  │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│                      DATA IMPORT PIPELINE                                │
│                                                                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐               │
│  │  Spreadsheets│───▶│ import_rows  │───▶│  Normalized  │               │
│  │  (XLS/ODS)   │    │  (JSONB)     │    │  API Tables  │               │
│  └──────────────┘    └──────────────┘    └──────────────┘               │
│        │                   │                    │                        │
│        ▼                   ▼                    ▼                        │
│   pandas reads      Raw data stored     Transform SQL                   │
│   all sheets        with row hashes     extracts unique                  │
│                     for deduplication   entities by code                 │
│                                                      patterns            │
└──────────────────────────────────────────────────────────────────────────┘
```

## 2. Component Description

### 2.1 Frontend Components

| Component | File | Responsibility |
|-----------|------|----------------|
| App Shell | `frontend/src/App.tsx` | Main layout, sidebar navigation, view routing |
| Admin Dashboard | `frontend/src/pages/AdminDashboard.tsx` | Platform metrics, client management, analytics |
| Client Portal | `frontend/src/pages/Portal.tsx` | Registration, login, API key management, usage |
| Charts | `frontend/src/components/Charts.tsx` | Recharts visualizations (area, bar, pie, line) |
| API Client | `frontend/src/api/client.ts` | Type-safe fetch wrapper with TanStack Query |
| Auth Store | `frontend/src/store/auth.ts` | Zustand-based token management |

### 2.2 Backend Components

| Component | File | Responsibility |
|-----------|------|----------------|
| Main Application | `app/main.py` | FastAPI app, all route handlers, middleware |
| API Entry Point | `api/index.py` | WSGI entry point for deployment |

### 2.3 Data Pipeline Scripts

| Script | Purpose |
|--------|---------|
| `scripts/import_to_postgres.py` | Import spreadsheets into staging tables |
| `scripts/normalize_geography.py` | Transform raw data into normalized schema |
| `scripts/verify_geography.py` | Validate referential integrity |
| `scripts/setup_saas.py` | Initialize SaaS schema and admin user |
| `scripts/create_api_client.py` | Create API client with credentials |

### 2.4 Database Schema

| Table | Records | Purpose |
|-------|---------|---------|
| countries | 1 (India) | Root of hierarchy |
| states | ~36 | States and Union Territories |
| districts | ~700 | Districts within states |
| sub_districts | ~5,000 | Sub-districts (tehsils/talukas) |
| villages | ~600,000 | Village-level entities |
| api_clients | Variable | Registered B2B clients |
| api_keys | Variable | API credentials per client |
| api_usage_events | Variable | Request audit log |
| admin_users | Variable | Platform administrators |
| import_files | Variable | Imported spreadsheet metadata |
| import_rows | Variable | Raw staging data |

## 3. Data Flow Diagrams

### 3.1 Client Registration and API Access Flow

```
┌─────────┐                                              ┌─────────┐
│ Client  │                                              │ Backend │
│ Browser │                                              │         │
└────┬────┘                                              └────┬────┘
     │                                                         │
     │  POST /auth/register                                    │
     │  {name, email, password, plan}                          │
     │────────────────────────────────────────────────────────▶│
     │                                                         │ Hash password
     │                                                         │ Create client
     │                                                         │ Generate JWT
     │  {token, status: "pending_approval"}                    │
     │◀────────────────────────────────────────────────────────│
     │                                                         │
     │  [After admin approval]                                 │
     │                                                         │
     │  POST /portal/api-keys  (with JWT)                      │
     │────────────────────────────────────────────────────────▶│
     │                                                         │ Generate key/secret
     │                                                         │ Store hashes
     │  {api_key: "ak_...", api_secret: "as_..."}              │
     │◀────────────────────────────────────────────────────────│
     │                                                         │
     │  Store credentials securely                             │
     │                                                         │
     │  GET /v1/states  (with X-API-Key, X-API-Secret)         │
     │────────────────────────────────────────────────────────▶│
     │                                                         │ Verify key hash
     │                                                         │ Check rate limit
     │                                                         │ Log usage event
     │  {success: true, data: [...], meta: {...}}              │
     │◀────────────────────────────────────────────────────────│
```

### 3.2 Admin Approval Flow

```
┌─────────┐                                              ┌─────────┐
│ Admin   │                                              │ Backend │
│ Browser │                                              │         │
└────┬────┘                                              └────┬────┘
     │                                                         │
     │  POST /admin/login                                      │
     │  {email, password}                                      │
     │────────────────────────────────────────────────────────▶│
     │                                                         │ Verify password
     │                                                         │ Generate admin JWT
     │  {token}                                                │
     │◀────────────────────────────────────────────────────────│
     │                                                         │
     │  GET /admin/clients  (with admin JWT)                   │
     │────────────────────────────────────────────────────────▶│
     │                                                         │
     │  [{id, name, email, plan, status, ...}]                 │
     │◀────────────────────────────────────────────────────────│
     │                                                         │
     │  POST /admin/clients/{id}/approve                       │
     │────────────────────────────────────────────────────────▶│
     │                                                         │ Set status=active
     │  {approved: true}                                       │
     │◀────────────────────────────────────────────────────────│
```

### 3.3 Data Import Pipeline Flow

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────┐
│  Excel/ODS  │────▶│  import_rows │────▶│  Transform  │────▶│  API     │
│  Files      │     │  (staging)   │     │  SQL        │     │  Tables  │
└─────────────┘     └──────────────┘     └─────────────┘     └──────────┘
      │                    │                    │                  │
      │                    │                    │                  │
  1. pandas           2. JSONB            3. INSERT            4. Query
     reads               storage              DISTINCT             endpoints
     all sheets          with hash            by code              return
                         for idempotent       patterns             normalized
                         re-runs                                   data
```

## 4. Security Architecture

### 4.1 Authentication Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    Authentication Stack                      │
│                                                              │
│  Layer 1: Admin/Client Portal                                │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Email/Password ──▶ PBKDF2 (120k iterations) ──▶ JWT  │  │
│  │  Token expiry: 12 hours                                │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
│  Layer 2: API Access                                         │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  API Key (ak_*) + Secret (as_*) ──▶ SHA-256 hashes   │  │
│  │  Secret required only for write operations            │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
│  Layer 3: Rate Limiting                                      │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Per-API-key counters in Redis                        │  │
│  │  Burst limit: 100-5000 requests/minute (by plan)      │  │
│  │  Daily quota: 5,000-1,000,000 (by plan)               │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Data Security Measures

| Aspect | Implementation |
|--------|----------------|
| Password Storage | PBKDF2-SHA256 with 120,000 iterations and random 16-byte salt |
| API Credentials | SHA-256 hashes stored; plaintext shown only once |
| JWT Signing | HS256 with configurable secret |
| Database Access | Parameterized queries (no SQL injection) |
| Response Headers | X-Content-Type-Options, X-Frame-Options, Strict-Transport-Security |
| IP Address Logging | Masked in admin views (first 7 chars only) |

## 5. Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Production Deployment                        │
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │   Vercel    │    │   Neon      │    │   Upstash   │         │
│  │   (Frontend)│    │ (PostgreSQL)│    │   (Redis)   │         │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘         │
│         │                  │                  │                 │
│         └──────────────────┼──────────────────┘                 │
│                            │                                     │
│                   ┌────────▼────────┐                           │
│                   │   FastAPI       │                           │
│                   │   (Railway/     │                           │
│                   │    Render)      │                           │
│                   └─────────────────┘                           │
│                                                                  │
│  Environment Variables:                                          │
│  - DATABASE_URL (Neon connection string)                         │
│  - REDIS_URL (Upstash connection string)                         │
│  - APP_JWT_SECRET (random 32+ characters)                        │
│  - ADMIN_EMAIL, ADMIN_PASSWORD                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 6. Technology Stack Summary

| Layer | Technology | Rationale |
|-------|------------|-----------|
| Frontend Framework | React 18 + TypeScript | Type safety, component reusability |
| State Management | Zustand + TanStack Query | Lightweight, server-state focused |
| Build Tool | Vite | Fast HMR, optimized production builds |
| Visualization | Recharts | Declarative charts, React-native |
| Backend Framework | FastAPI | Async support, automatic OpenAPI docs |
| Database | PostgreSQL | ACID compliance, JSONB flexibility, GIN indexes |
| ORM | psycopg2 (raw SQL) | Full control over queries for optimization |
| Cache | Redis | Sub-millisecond counters for rate limiting |
| Password Hashing | PBKDF2-SHA256 | Industry standard, configurable iterations |
| Token Format | JWT | Stateless, widely supported |

---

# EVALUATION CHECKLIST

## Implemented Features

- [x] Census spreadsheet import (XLS/XLSX/ODS)
- [x] Geography normalization (5-tier hierarchy)
- [x] Data validation utilities
- [x] FastAPI backend with all endpoints
- [x] JWT authentication (admin + client)
- [x] API key/secret credential model
- [x] Multi-tier rate limiting (Redis + fallback)
- [x] Usage logging and analytics
- [x] Admin dashboard with client management
- [x] Client portal with API key lifecycle
- [x] Real-time usage dashboards
- [x] Response caching (optional Redis)
- [x] Connection pooling
- [x] Security headers
- [x] Structured error responses

## Code Quality Indicators

- [x] Type hints throughout backend
- [x] TypeScript strict mode frontend
- [x] Consistent code style
- [x] Error handling with appropriate status codes
- [x] Idempotent data import (UPSERT semantics)
- [x] Referential integrity constraints
- [x] Index optimization for query patterns

---

*This document provides a high-level overview suitable for evaluator review.*
*For detailed implementation information, refer to DOCUMENTATION.md.*
