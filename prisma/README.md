# Prisma Schema Scaffold

Status: placeholder integration point.

The current application remains Python/FastAPI with direct SQL through
`psycopg2`. `schema.prisma` maps the existing PostgreSQL tables so a future
Node service can introduce Prisma without redesigning the Phase 1 data model.

Use it only if a Node transition is approved:

```powershell
npm install prisma @prisma/client
npx prisma generate --schema prisma/schema.prisma
```

Do not run `prisma migrate dev` against the current database unless the SQL
migrations in `sql/migrations/` have been reconciled with Prisma migrations.
