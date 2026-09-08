# Phase 26: PostgreSQL Readiness Assessment

Status: **Planning Only — No Changes Made**

## 1. Current State

- Engine: SQLite3
- File: `db.sqlite3` (~6.4 MB)
- Django: 5.2.11
- `USE_TZ = True`, `TIME_ZONE = UTC`
- `DEFAULT_AUTO_FIELD = BigAutoField`

## 2. SQLite → PostgreSQL Behavioral Differences

| Area | SQLite | PostgreSQL |
|------|--------|------------|
| FK enforcement | Off by default | On by default |
| Transactions | Implicit | Explicit |
| `select_for_update` | No-op (ignored) | Real row locks |
| JSON field | Text-based | Native JSONB |
| Decimal precision | Arbitrary | Fixed numeric(p,s) |
| Case-sensitive unique | Collation-dependent | Configurable |
| Index types | Limited | GIN/GiST/BRIN |
| Full-text search | Built-in | Separate (tsvector) |

## 3. PersianDateField Compatibility

`PersianDateField` stores Gregorian dates in DB via `get_prep_value`.
PostgreSQL `DateField` is fully compatible. No migration risk.

## 4. Risks

1. **SQLite FKs not enforced** — existing data may violate FKs; PostgreSQL will reject.
2. **Case sensitivity** in unique constraints on CharFields.
3. **JSONField** — SQLite stores as text; PostgreSQL as JSONB. Django abstracts this.
4. **`select_for_update`** — currently no-op in SQLite; will lock in PostgreSQL. Test concurrent operations.
5. **Integer PK overflow** — SQLite uses 64-bit; PostgreSQL int8 is fine.

## 5. Migration Commands (Planned)

```bash
# Backup
cp db.sqlite3 db.sqlite3.backup.$(date +%Y%m%d)

# Dump
sqlite3 db.sqlite3 .dump > dump.sql

# Staging restore
psql -U postgres -d craftflow_staging < dump.sql
```

## 6. Recommendation

**Do not migrate yet.** V1 is operational and stable. PostgreSQL migration should happen
after at least one domain reaches Controlled Cutover, so we can validate V2 behavior
on the target database.