# V1 to V2 Decision Map

Date: 2026-09-08
Source: docs/V2_DEEP_AUDIT.md
Status: Decision map only. No code changes.

## Legend

- **KEEP**: V1 remains source of truth. V2 not ready.
- **REFACTOR**: V1 stays but extract to service layer.
- **REPLACE**: V2 model ready to take over.
- **MERGE**: Multiple V1 models combine into one V2 model.
- **MIGRATE**: Data migration planned with MigrationMap.
- **DEPRECATE**: V1 retained read-only, V2 is source.

## Decision Table

| V1 Model | Decision | V2 Target | Source of Truth | ID Strategy |
|----------|----------|-----------|-----------------|-------------|
| Customer | KEEP | customers.Customer | V1 (product.Customer) | MigrationMap |
| ProductCategory | KEEP | products.ProductCategory | V1 (product.ProductCategory) | MigrationMap |
| Product | KEEP | products.Product | V1 (product.Product) | MigrationMap |
| Material | MERGE | inventory.Item | V1 (product.Material) | MigrationMap |
| RawMaterial | MERGE | inventory.Item | V1 (inventory.RawMaterial) | MigrationMap |
| Part | KEEP | products.ProductPart | V1 (product.Part) | MigrationMap |
| ProductBOM | REPLACE | bom.BOM | V1 (product.ProductBOM) | MigrationMap |
| Order | REPLACE | sales.CustomerOrder | V1 (product.Order) | MigrationMap |
| OrderItem | REPLACE | sales.CustomerOrderItem | V1 (product.OrderItem) | MigrationMap |
| ProductionTask | REPLACE | production.ProductionOperation | V1 (product.ProductionTask) | MigrationMap |
| WorkerProfile | REPLACE | accounts.Worker | V1 (product.WorkerProfile) | MigrationMap |
| StockMovement | REPLACE | inventory.StockLedger | V1 (inventory.StockMovement) | MigrationMap |
| ProductionLog | KEEP | (none) | V1 (product.ProductionLog) | N/A |
| ProductionEvent | REPLACE | reporting.BusinessEvent | V1 (product.ProductionEvent) | MigrationMap |
| PackagingUnit | REPLACE | packaging.Package | V1 (product.PackagingUnit) | MigrationMap |
| ShipmentLog | REPLACE | shipping.Shipment | V1 (product.ShipmentLog) | MigrationMap |
| PaintingProcess | REPLACE | painting.PaintingProcess | V1 (product.PaintingProcess) | MigrationMap |
| PaintingStage | REPLACE | painting.PaintingProcessStage | V1 (product.PaintingStage) | MigrationMap |
| PaintingAssignmentRule | REPLACE | painting.PaintingAssignmentRule | V1 (product.PaintingAssignmentRule) | MigrationMap |

## Special Handling

### PersianDateField
- V1 stores as Gregorian via get_prep_value
- V2 uses standard DateField
- Migration: direct copy, no conversion needed
- Rule: preserve original Gregorian value

### QR Legacy Codes
- OrderItem QR: /scan/{id}/
- PackagingUnit QR: /scan/packaging/{id}/
- BarcodeResolver handles both read-only
- No QR regeneration
- Migration: MigrationMap links old ID to new entity

### PaintingScheduler
- V1 truth in product/utils.py
- V2 PaintingSchedule is separate
- No algorithm migration
- V1 scheduler continues as source of truth

### Material/RawMaterial Merge
- product.Material + inventory.RawMaterial -> inventory.Item
- Material.raw_material FK links to RawMaterial
- Merge rule: one Item per unique (name, category, unit)
- Ambiguous: log warning, do not guess

### ProductionTask Status Mapping
- V1: waiting -> pending -> done
- V2: waiting -> ready -> in_progress -> completed
- Rule: waiting->waiting, pending->ready, done->completed

### StockMovement to StockLedger
- V1: aggregate-based (RawMaterial.current_stock)
- V2: ledger-based (StockLedger + StockBalance)
- Rule: each StockMovement creates one StockLedger entry
- Balance computed from ledger, not stored independently

## rollback

All decisions are reversible:
- KEEP: no action needed
- REPLACE: V1 remains until cutover
- MERGE: V1 models retained
- MigrationMap allows reverse lookup