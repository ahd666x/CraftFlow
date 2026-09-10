# Phase 3: V2 Schema Foundation

Date: 2026-09-08
Prerequisites: Decision Map (Phase 2) approved, V2 data verified zero
Status: Complete

## Scope

V2 schema fixes only. No V1 models, migrations, or data touched.

## Changes

### production/models.py — ProductionOperation V1 Compatibility
Added 7 fields to bridge V1 ProductionTask:
- part (FK to ProductPart)
- scanned_by (FK to User)
- completed_at (DateField, PersianDate-compatible)
- painting_stage (FK to PaintingProcessStage)
- assigned_worker (FK to User)
- order_item (FK to CustomerOrderItem)
- color_part (CharField)

### warehouse/models.py — Idempotency
- MaterialIssue: added idempotency_key (CharField, unique)
- MaterialConsumption: added idempotency_key (CharField, unique)

### warehouse/services.py — Idempotency Fix
- issue_material: checks idempotency_key directly (not via notes search)
- consume_material: checks idempotency_key directly

### reporting/models.py — Event & Barcode Traceability
BusinessEvent added:
- correlation_id (indexed)
- legacy_reference (indexed)
- legacy_app, legacy_model, legacy_id

Barcode added:
- legacy_entity_type
- legacy_entity_id

### inventory/models.py — Item Consumption Rate
- Item.consumption_per_unit (Decimal, default=1)

## Migrations

| File | App | Changes |
|------|-----|---------|
| 0003_item_consumption_per_unit.py | inventory | Add consumption_per_unit to Item |
| 0003_productionoperation_v1_compat.py | production | Add 7 V1 compat fields |
| 0002_materialissue_consumption_idempotency.py | warehouse | Add idempotency_key to MaterialIssue, MaterialConsumption |
| 0002_business_event_barcode_legacy.py | reporting | Add legacy fields to BusinessEvent, Barcode |

## Validation

- `python manage.py check` — 0 issues
- `python manage.py makemigrations --check --dry-run` — no changes detected
- `python manage.py test` — 59 tests, all OK

## Risks

- Low: All changes are additive (new nullable fields)
- Low: V2 data is zero, so no data migration needed
- Low: V1 models and migrations untouched

## Rollback

Delete the 4 new migration files and revert model changes. V1 unaffected.

## Commit

v2/phase-03-schema-foundation