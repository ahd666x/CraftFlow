# Phase 45: API Boundary Design

Status: **Design Only — No Public API Created**

## Service Readiness

| Service | API-Ready | Notes |
|---------|-----------|-------|
| `LegacyProductionService` | Yes | `complete_task` is a clean mutation |
| `InventoryService` | Yes | All methods are atomic transactions |
| `WarehouseService` | Yes | Has idempotency key support |
| `ProductionService` | Yes | `complete_operation` with force flag |
| `VersionedBOMService` | Yes | Snapshot creation is read+write |
| `BarcodeResolver` | Yes | Pure read, no side effects |

## Current View Issues

- `product/views.py` contains business logic inline
- No serialization layer exists
- No pagination on list endpoints
- No idempotency on mutation endpoints

## Proposed Contract

- Authentication: session-based (existing)
- Authorization: per-role, per-object
- Errors: `{error, code, message, entity_id}`
- Pagination: `limit`/`offset`
- Idempotency: `Idempotency-Key` header
- Versioning: `/v2/` prefix only

## Forbidden

- Converting entire project to DRF
- Changing V1 URLs
- Publishing external endpoints

## No Changes Made