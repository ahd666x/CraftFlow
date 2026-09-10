# V2 Target Blueprint

Date: 2026-09-08
Source: docs/V1_TO_V2_DECISION_MAP.md
Status: Target design only. No implementation.

## Architecture Principles

1. Business logic in Services, not Models or Views
2. Complex queries in Selectors, not Views
3. All quantities as Decimal
4. Inventory via StockLedger (immutable log) + StockBalance (cached aggregate)
5. All mutations transaction-safe with select_for_update
6. PersianDateField stores as Gregorian; V2 uses standard DateField
7. QR legacy codes preserved via BarcodeResolver
8. PaintingScheduler remains V1-only

## Target Domain Map

### Sales Domain
- **Source**: sales.CustomerOrder, sales.CustomerOrderItem, sales.OrderItemColor
- **Service**: sales/services.py OrderService
- **Replaces**: product.Order, product.OrderItem, product.Color
- **Fields mapped**: Order.number -> CustomerOrder.order_number, Order.created_at -> CustomerOrder.order_date
- **Missing**: CustomerOrder lacks PersianDateField; needs order_date as DateField

### Product Domain
- **Source**: products.Product, products.ProductCategory, products.ProductPart
- **Replaces**: product.Product, product.ProductCategory, product.Part
- **Status**: V2 models exist but lack Part fields (f3 barcode, routing_code, material FK)

### BOM Domain
- **Source**: bom.BOM, bom.BOMItem, bom.BOMItemMaterialRule
- **Replaces**: product.ProductBOM
- **Service**: bom/services.py VersionedBOMService
- **Status**: Versioned snapshots supported; color_material_map converted to rules

### Production Domain
- **Source**: production.ProductionOperation
- **Replaces**: product.ProductionTask
- **Missing fields**: part, scanned_by, completed_at (PersianDate), painting_stage, assigned_worker, order_item, color_part
- **Status**: Needs field additions before replacement possible

### Inventory Domain
- **Source**: inventory.Item, inventory.StockLedger, inventory.StockBalance, inventory.StockLocation, inventory.StockLot
- **Replaces**: inventory.RawMaterial, product.Material, inventory.StockMovement
- **Rule**: StockLedger is single mutation path; StockBalance is derived

### Warehouse Domain
- **Source**: warehouse.MaterialIssue, warehouse.MaterialConsumption, warehouse.MaterialReturn, warehouse.MaterialWaste
- **Replaces**: (none directly; V1 has no warehouse model)
- **Status**: New domain; needs idempotency_key

### Painting Domain
- **Source**: painting.PaintingProcess, painting.PaintingProcessStage, painting.PaintingAssignmentRule, painting.PaintingSchedule
- **Replaces**: product.PaintingProcess, product.PaintingStage, product.PaintingAssignmentRule
- **Status**: V2 duplicates V1; PaintingScheduler remains V1-only

### Packaging Domain
- **Source**: packaging.Package, packaging.PackageItem
- **Replaces**: product.PackagingUnit
- **Status**: Needs MigrationMap reference to PackagingUnit

### Shipping Domain
- **Source**: shipping.Shipment, shipping.ShipmentItem, shipping.ShipmentTracking
- **Replaces**: product.ShipmentLog
- **Status**: Needs MigrationMap reference

### Reporting Domain
- **Source**: reporting.BusinessEvent, reporting.AuditLog, reporting.MigrationMap, reporting.MigrationRun
- **Replaces**: product.ProductionEvent
- **Status**: BusinessEvent needs correlation field; AuditLog needs callers

## Service Layer Target

| Domain | Service | Methods | Status |
|--------|---------|---------|--------|
| Sales | OrderService | create_order, add_item, update_totals | Needs implementation |
| Inventory | InventoryService | receive_stock, reserve_stock, transfer_stock, adjust_stock | Exists, zero callers |
| Warehouse | WarehouseService | issue_material, consume_material | Exists, zero callers |
| Production | ProductionService | complete_operation, create_operations | Exists, zero callers |
| BOM | VersionedBOMService | build_snapshot, create_revision | Exists, zero callers |
| Painting | PaintingService | create_process, assign | Exists, zero callers |
| Reporting | (none) | EventService.record_event needed | Not created |

## Selector Layer Target

| Domain | Selector | Methods | Status |
|--------|----------|---------|--------|
| Inventory | InventorySelectors | get_stock_summary, get_low_stock | Exists, zero callers |
| Production | ProductionSelectors | get_production_queue, get_ready_ops | Exists, zero callers |
| Reporting | ReportingSelectors | get_business_events, get_migration_stats | Exists, zero callers |

## Migration Infrastructure

- **MigrationMap**: links V1 (old_app, old_model, old_id) to V2 (new_app, new_model, new_id)
- **MigrationRun**: tracks each migration execution with phase, status, counts
- **BarcodeResolver**: resolves legacy QR codes to V1 entities with optional V2 metadata

## Known Gaps

1. ProductionOperation missing 7 V1 fields
2. CustomerOrder missing PersianDateField
3. No EventService for BusinessEvent creation
4. No AuditLog callers
5. All V2 urls.py empty
6. No V2 views or templates
7. No feature flags