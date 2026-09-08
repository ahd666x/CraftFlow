# Phase 51: Production Rollout Plan

Date: 2026-09-08
Status: **Planned — Not Executed**

## Domain Readiness

| Domain | Go-Live Status | Rollout Possible |
|--------|---------------|-----------------|
| Sales | No-Go | No |
| Production | No-Go | No |
| Inventory | No-Go | No |
| Warehouse | No-Go | No |
| Painting | No-Go | No |
| Quality | No-Go | No |
| Packaging | No-Go | No |
| Shipping | No-Go | No |
| Reporting | No-Go | No |
| Barcode | Go with Conditions | Yes (metadata only) |

## Barcode Domain Rollout Plan

### Version
- Commit: current HEAD (uncommitted changes)
- Files: `reporting/barcode_resolver.py`, `reporting/models.py`

### Migrations
- None required (additive only)

### Feature Flag
- `V2_BARCODE_RESOLVER_METADATA` — default OFF

### Downtime
- None (read-only resolver)

### Backup Prerequisite
- `cp db.sqlite3 db.sqlite3.backup.$(date +%Y%m%d)`

### Owner
- Production team

### Success Criteria
- `BarcodeResolver.resolve()` returns correct entity for all legacy QR patterns
- Zero mutations performed
- All existing tests pass

### Monitoring
- QR resolve success rate
- Unknown QR count

### Rollback
- Remove `reporting/barcode_resolver.py` import; no data changes

### Approval
- Required: Production team lead

## Minute-by-Minute Runbook (When Approved)

1. **T-0**: Backup database
2. **T-0**: Confirm feature flag `V2_BARCODE_RESOLVER_METADATA` is OFF
3. **T-0**: Run `python manage.py test`
4. **T+1**: Deploy code
5. **T+2**: Run `python manage.py check`
6. **T+3**: Run smoke test — QR resolution
7. **T+5**: Enable feature flag
8. **T+10**: Monitor QR resolve success rate
9. **T+30**: Confirm no errors in logs
10. **T+60**: Sign-off

## No Deploy Performed