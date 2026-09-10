# V2 Data Migration Specification

Date: 2026-09-08
Source: docs/V1_TO_V2_DECISION_MAP.md
Status: Specification only. No migration executed.

## Preconditions

- V2 schema deployed and validated
- MigrationMap and MigrationRun tables available
- BarcodeResolver operational
- Feature flags defined (all default OFF)
- Backup confirmed

## Migration Order

### Phase 1: Master Data (no dependencies)
1. ProductCategory: product.ProductCategory -> products.ProductCategory
2. Product: product.Product -> products.Product
3. Customer: product.Customer -> customers.Customer
4. Material + RawMaterial -> inventory.Item (MERGE)

### Phase 2: BOM and Parts
5. Part: product.Part -> products.ProductPart
6. ProductBOM: product.ProductBOM -> bom.BOM (with revision A)

### Phase 3: Sales
7. Order: product.Order -> sales.CustomerOrder
8. OrderItem: product.OrderItem -> sales.CustomerOrderItem
9. Color: product.Color -> sales.OrderItemColor

### Phase 4: Production
10. ProductionTask: product.ProductionTask -> production.ProductionOperation
11. WorkerProfile: product.WorkerProfile -> accounts.Worker

### Phase 5: Inventory
12. StockMovement: inventory.StockMovement -> inventory.StockLedger
13. StockBalance: computed from StockLedger

### Phase 6: Packaging and Shipping
14. PackagingUnit: product.PackagingUnit -> packaging.Package
15. ShipmentLog: product.ShipmentLog -> shipping.Shipment

### Phase 7: Events and Audit
16. ProductionEvent: product.ProductionEvent -> reporting.BusinessEvent
17. ProductionLog: KEEP (no V2 equivalent)

## Field Mapping Rules

### Dates
- V1 PersianDateField stores as Gregorian in DB
- V2 uses standard DateField
- Rule: copy raw DB value directly
- No conversion needed
- Exception: completed_at in ProductionTask is PersianDateField; map to actual_end in ProductionOperation

### Status Mapping
| V1 Status | V2 Status | Rule |
|-----------|-----------|------|
| waiting | waiting | Direct |
| pending | ready | Direct |
| done | completed | Direct |
| draft | draft | Direct |
| planned | planned | Direct |
| producing | in_progress | Direct |
| completed | completed | Direct |
| cancelled | cancelled | Direct |

### Quantity Rules
- All quantities must be Decimal
- V1 PositiveIntegerField -> V2 PositiveIntegerField (counts)
- V1 DecimalField -> V2 DecimalField (weights/measures)
- consumption_per_unit: float -> Decimal

### ID Strategy
- V1 IDs preserved in MigrationMap.old_id
- V2 IDs are new auto-increment
- MigrationMap links old to new
- QR legacy codes use old_id; BarcodeResolver maps to new entity

### Ambiguous Data Handling
- If mapping is unclear: log warning, skip record, set MigrationMap.is_legacy=True
- Never guess
- Report ambiguous records in migration report

## Special Domains

### PersianDateField
- No conversion needed (stores as Gregorian)
- V2 DateField reads same value
- Risk: none

### QR Legacy Codes
- No QR regeneration
- BarcodeResolver handles /scan/{id}/ and /scan/packaging/{id}/
- MigrationMap.old_id preserves QR scanability
- QR codes continue to work via resolver

### PaintingScheduler
- No migration
- V1 scheduler remains source of truth
- V2 PaintingSchedule is separate
- No data movement between them

### Material/RawMaterial Merge
- product.Material.raw_material FK links to inventory.RawMaterial
- Merge rule: one inventory.Item per unique (name, category, unit)
- If Material has no RawMaterial: warning, create Item from Material only
- If RawMaterial has no Material: create Item from RawMaterial only
- Ambiguous: log warning, do not merge

### StockMovement to StockLedger
- Each StockMovement creates one StockLedger entry
- ledger_type mapping: purchase->receipt, consumption->consumption, adjustment->adjustment
- StockBalance computed from StockLedger aggregate
- No direct StockBalance migration (recompute from ledger)

## MigrationRun Tracking

Each migration execution creates a MigrationRun with:
- phase: domain name
- name: descriptive
- status: pending -> running -> completed/failed/partial
- records_processed, records_failed, records_skipped

## rollback

- Delete all V2 records created by a MigrationRun
- V1 records untouched
- MigrationRun records deleted
- MigrationMap records deleted for that run
- Database restored from pre-migration backup if needed