# Phase 27: Controlled PostgreSQL Migration

Status: **Not Executed — Requires Staging Environment**

## Preconditions Not Met

- PostgreSQL server not available in this environment
- No staging database configured
- No user confirmation of migration time

## Required Steps (When Ready)

1. Provision PostgreSQL staging instance
2. `cp db.sqlite3 db.sqlite3.backup.$(date +%Y%m%d)`
3. `sqlite3 db.sqlite3 .dump > dump.sql`
4. `psql -U postgres -d craftflow_staging < dump.sql`
5. Run `python manage.py check` against staging
6. Run `python manage.py test` against staging
7. Record-count reconciliation per app
8. FK integrity check
9. Smoke test: QR scan, order, production, inventory, packaging
10. Production go/no-go recommendation

## Risk

- SQLite FKs are not enforced; PostgreSQL will reject invalid FKs
- `select_for_update` will now actually lock rows
- Case-sensitive unique constraints may conflict

## Recommendation

Defer until at least one V2 domain reaches Controlled Cutover.