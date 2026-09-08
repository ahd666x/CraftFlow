# Phase 28: Security and Authorization Audit

Status: **Audit Only — No Changes Made**

## Findings

### QR Scan Endpoints
- `scan_qr` and `scan_packaging_unit` accept mutations without explicit permission checks
- Risk: anonymous user could mark tasks done or pack/ship items

### Warehouse Operations
- `issue_material`, `complete_operation`, shipment, delete operations lack explicit permissions

### Secrets
- `SECRET_KEY` is hardcoded in settings.py
- `SCAN_BASE_URL` may be hardcoded in signals.py

### Audit Coverage
- `ProductionEvent` covers task completion
- `AuditLog` model exists in reporting but has no active callers
- Many mutations have no audit trail

## Required Fixes (Future)

1. Add `@login_required` and role checks to mutation endpoints
2. Move secrets to environment variables
3. Wire AuditLog to all sensitive mutations
4. Add CSRF protection verification for all POST endpoints

## No Changes Made This Phase