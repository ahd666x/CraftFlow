# Phase 11: V1-V2 Reconciliation

## Summary

Added `craftflow_reconcile_v2` management command that compares V1 (`product` app) and V2 (decomposed apps) entity counts, MigrationMap anchors, and BusinessEvent/AuditLog coverage.

## V1 → V2 Entity Mapping

| V1 (product app) | V2 (decomposed app) | Migration Type |
|---|---|---|
| `Customer` | `customers.Customer` | `customer` |
| `Product` | `products.Product` | `product` |
| `ProductCategory` | `products.ProductCategory` | `product_category` |
| `ProductBOM` | `bom.BOM` | `bom` |
| `OrderItem` (Part) | `bom.BOMItem` | `bom_item` |
| `Order` | `sales.CustomerOrder` | `order` |
| `OrderItem` | `sales.CustomerOrderItem` | `order_item` |
| `ProductionTask` | `production.ProductionOrder` | `task` |
| `Material` | `inventory.RawMaterial` | `material` |
| `Material` | `inventory.Item` | `item` |
| `PaintingProcess` | `painting.PaintingSchedule` | `painting_process` |
| `PaintingStage` | `painting.PaintingProcessStage` | `painting_stage` |
| `ProductionEvent` | `reporting.BusinessEvent` | `production_event` |
| `ShipmentLog` | `shipping.Shipment` | `shipment_log` |

## Reconciliation Command

```bash
python manage.py craftflow_reconcile_v2
python manage.py craftflow_reconcile_v2 --json
```

### Text Output
Human-readable table comparing V1 and V2 counts, migration map coverage,
and business event migration status.

### JSON Output
Machine-readable report with:
- `entity_comparisons`: List of entity count comparisons (V1 vs V2)
- `migration_map_types_found`: Migration types present in MigrationMap
- `migration_map_types_missing`: Expected migration types not yet mapped
- `business_event_migration`: V1 event count vs V2 legacy-tagged event count
- `audit_log_count`: Total AuditLog entries
- `summary`: Aggregate reconciliation statistics

## Tests (8 tests, all passing)

- `test_reconcile_json_output` - Verifies JSON report structure
- `test_customer_reconciliation` - Customer count comparison (1 vs 1)
- `test_product_reconciliation` - Product count comparison (1 vs 1)
- `test_order_reconciliation` - Order count comparison (1 vs 1)
- `test_task_reconciliation` - ProductionTask comparison (1 V1 vs 0 V2, mismatch)
- `test_mismatch_detection` - Mismatch flag is raised when counts differ
- `test_migration_map_types` - MigrationMap type tracking
- `test_text_output` - Human-readable text output format

## Known Gaps (Pre-Migration)

When run against a database where V2 migration has not been executed:
- All `migration_map_types_missing` entries are untracked
- `business_event_migration.v2_events_tagged_legacy` is 0
- Entity counts may differ between V1 and V2 until migration is run

Run `python manage.py craftflow_migrate_v2` to populate V2 data from V1.
