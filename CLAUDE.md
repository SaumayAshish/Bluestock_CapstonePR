# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BlueStock is a B2B SaaS platform providing village-level India geography API data. The system consists of:
- **FastAPI backend** (`app/main.py`) - PostgreSQL + Redis-backed API with rate limiting, JWT auth, and usage analytics
- **React + Vite frontend** (`frontend/`) - Admin dashboard and client portal with TanStack Query, Zustand, and Recharts
- **Prisma schema** (`prisma/schema.prisma`) - Optional Node.js ORM layer for future expansion

## Commands

### Backend (FastAPI)
```bash
# Run backend server
uvicorn app.main:app --reload --port 8000

# Setup database schema and admin user
python scripts/setup_saas.py

# Create new API client
python scripts/create_api_client.py
```

### Frontend (React + Vite)
```bash
cd frontend

# Development server (proxies /v1, /admin, /auth, /portal to backend :8000)
npm run dev

# Build for production
npm run build

# Type check
npx tsc --noEmit

# Lint
npm run lint
```

### Database
```bash
# Apply Prisma schema (if using Node.js services)
npx prisma migrate dev

# Generate Prisma client
npx prisma generate
```

## Architecture

### Backend Structure
- `app/main.py` - Single-file FastAPI application (~1500 lines)
  - JWT-based authentication for admin and client roles
  - Redis rate limiting (fallback to in-memory deques)
  - API usage logging to `api_usage_events` table
  - Plan-based quotas: free/premium/pro/unlimited tiers

### API Endpoints
- `/auth/*` - Client registration/login
- `/admin/*` - Admin dashboard (client management, analytics, usage logs)
- `/portal/*` - Client portal (API key management, usage stats)
- `/v1/*` - Geography API (states, districts, sub-districts, villages, autocomplete)
- `/health` - Health check

### Frontend Structure
- `frontend/src/App.tsx` - Main shell with sidebar navigation
- `frontend/src/pages/AdminDashboard.tsx` - Admin dashboard components
- `frontend/src/pages/Portal.tsx` - Client portal
- `frontend/src/store/auth.ts` - Zustand auth store
- `frontend/src/api/client.ts` - API client with TanStack Query
- `frontend/src/components/Charts.tsx` - Recharts visualizations

### Database Schema
- **Geography hierarchy**: Country → State → District → SubDistrict → Village
- **SaaS tables**: `api_clients`, `api_keys`, `api_usage_events`, `admin_users`
- **Import tracking**: `import_files`, `import_rows` for data ingestion

### Key Configuration
- Environment: `.env` (see `.env.example`)
- PostgreSQL connection via `DATABASE_URL`
- Redis connection via `REDIS_URL` (optional, falls back to memory)
- JWT secret via `APP_JWT_SECRET`
- Frontend proxies API calls to backend via Vite config

## Development Notes

- Backend runs on port 8000, frontend on 5173
- Vite proxy forwards `/admin`, `/auth`, `/portal`, `/v1`, `/health` to backend
- Default admin: `admin@bluestock.local` / configured via `ADMIN_PASSWORD`
- Rate limits enforced per API key with Redis counters or in-memory deques
