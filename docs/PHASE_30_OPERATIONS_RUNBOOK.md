# Phase 30: Operational Resilience Runbook

Status: **Documented — Not Tested**

## Database Backup

```bash
cp db.sqlite3 backups/db.sqlite3.$(date +%Y%m%d-%H%M%S)
```

## Media Backup

```bash
tar -czf backups/media.$(date +%Y%m%d).tar.gz /root/selvi/selvi/media
```

## Restore Procedure

1. Stop application
2. Restore latest backup
3. Verify record counts
4. Restart application
5. Run smoke tests

## Migration Rollback

- All V2 migrations are additive; rollback = drop V2 tables
- Never drop V1 tables or historical migrations

## Feature Flag Rollback

- All V2 features behind feature flags
- Default: OFF
- Flip flag to OFF for immediate rollback

## QR Compatibility Validation

- Legacy QR patterns: `/scan/{id}/`, `/scan/packaging_unit/{id}/`
- `BarcodeResolver` handles both
- No QR regeneration ever

## Inventory Reconciliation After Recovery

- V1: `RawMaterial.current_stock` from `StockMovement` aggregate
- V2: `StockBalance` from `StockLedger`
- Both must be checked after restore

## Health Check

```bash
python manage.py check
python manage.py migrate --check
```

## Deployment Checklist

- [ ] Backup database
- [ ] Backup media
- [ ] Run tests
- [ ] Verify migrations
- [ ] Confirm feature flags OFF
- [ ] Deploy
- [ ] Run smoke tests