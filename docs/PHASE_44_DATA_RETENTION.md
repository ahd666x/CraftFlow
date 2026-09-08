# Phase 44: Historical Data Retention

Status: **Policy Defined — No Data Deleted**

## Retention Rules

| Data | Retention | Archive | Delete |
|------|-----------|---------|--------|
| Order | Permanent | After 7 years | No |
| ProductionTask | Permanent | After 7 years | No |
| StockMovement | Permanent | After 7 years | No |
| StockLedger | Permanent | After 7 years | No |
| BusinessEvent | Permanent | After 7 years | No |
| AuditLog | Permanent | After 7 years | No |
| QR media | 7 years | After 7 years | With approval |
| ShipmentLog | Permanent | After 7 years | No |
| MigrationRun | Permanent | After 7 years | No |

## Rules

- No data deleted without explicit user approval
- Archive preserves QR compatibility
- Reports must work on archived data
- Historical migrations never deleted

## No Changes Made