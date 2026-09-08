# Phase 36: Application Monitoring Design

Status: **Design Only — Not Implemented**

## Event/Error Taxonomy

| Category | Events |
|----------|--------|
| Migration | migration_started, migration_completed, migration_failed, migration_rolled_back |
| Inventory | negative_stock, reconciliation_mismatch, receive_failed, transfer_failed |
| QR | qr_resolve_failed, qr_scan_anonymous_mutation |
| Transaction | rollback_triggered, deadlock_detected |
| Scheduler | scheduler_failed, unscheduled_task |
| Shipment | shipment_failed, duplicate_shipment |
| Permission | unauthorized_access, privilege_escalation |
| Query | slow_query_threshold_exceeded |
| Exception | unhandled_exception |

## Alert Thresholds

- Migration failure: immediate
- Negative stock: immediate
- Inventory reconciliation mismatch > 5%: immediate
- QR resolve failure > 10%: high
- Transaction rollback: high
- Slow query > 2s: medium
- Unhandled exception: immediate

## Rules

- No customer data or secrets in logs
- Deduplicate repeated alerts
- Logging must never fail the workflow
- Start with local/staging-friendly implementation

## No Changes Made