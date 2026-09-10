# Phase 13: Data-State Audit

## Executive Summary

**V2 schema has NOT been applied to the production database.** Zero V2 tables exist.
The database contains only V1 (`product` app) tables with live data (~15K records across key entities).
MigrationMap, BusinessEvent, AuditLog, and Barcode tables do not exist.

**V1 is the single source of truth.** V1 data must not be touched.

## Step A — Current Data State

### V1 Tables (product app) — Applied & Live

| Table | Rows | Notes |
|---|---|---|
| `product_customer` | 307 | Active customer records |
| `product_product` | 84 | Products |
| `product_productcategory` | 7 | Product categories |
| `product_productbom` | 786 | BOM tree (self-referential, Product→Part) |
| `product_part` | 2078 | Parts (leaf nodes of BOM) |
| `product_order` | 185 | Orders: 32 completed, 137 producing, 8 draft, 8 planned |
| `product_orderitem` | 395 | Order line items |
| `product_productiontask` | 13,068 | Production tasks: 6053 done, 3047 pending, 3968 waiting |
| `product_productionlog` | 1679 | Production execution logs |
| `product_material` | 12 | Raw materials |
| `product_color` | 757 | Colors |
| `product_packagingunit` | 523 | Packaging units |
| `product_workerprofile` | 15 | Worker profiles |
| `product_shipmentlog` | 267 | Shipment records |
| `product_paintingprocess` | 3 | Painting processes |
| `product_paintingstage` | 15 | Painting stages |
| `product_paintingassignmentrule` | 7 | Assignment rules |
| `product_holiday` | 0 | Holiday calendar (empty) |

### Missing V1 Tables (Pending Migrations)

| Missing Table | Migration That Creates It | Cause |
|---|---|---|
| `product_productionevent` | `product.0015_productionevent` | Event logging table for V1 ProductionEvents |

Product app pending migrations: 0006 through 0017 (11 pending).
These are V1 schema evolution migrations, not V2 migrations.

### V2 Tables — **NONE EXIST**

All V2 apps have pending `0001_initial` (or later) migrations that have **not been applied**:

```
bom, customers, inventory, packaging, painting, planning,
production, products, quality, reporting, sales, shipping, warehouse
```

**No V2 records exist.** All V2 model queries return `no such table: <table>`.

### MigrationMap Status

The `reporting_migrationmap` table **does not exist** in the database.
- 0 MigrationMap entries
- 0 legacy references
- Migration map types found: `[]` (empty)
- All 14 expected migration types missing (customer, order, order_item, product, etc.)

### BusinessEvent / AuditLog Status

Neither `reporting_businessevent` nor `reporting_auditlog` nor `reporting_barcode` tables exist.
- 0 BusinessEvents (V1 or V2)
- 0 AuditLog entries
- 0 Barcode records

### FK Integrity Check (V1 Only)

| Check | Result |
|---|---|
| `product_orderitem` orphan Product FK | 0 (clean) |
| `product_orderitem` orphan Order FK | 0 (clean) |
| `product_productbom` orphan Product FK | 0 (clean) |
| `product_productbom` orphan Part FK | 0 (clean) |
| `product_shipmentlog` orphan Order FK | Could not check (column name differs from expected) |
| `product_productiontask` orphan Product FK | Could not check (column name differs from expected) |

### Duplicate Detection (V1)

- Customer model does not have an `email` field (fields: address, id, name, phone, user, user_id)
- No duplicate name/phone combinations checked (manual review needed before V2 migration)
- No duplicate detection issues on FK fields

### Data Classification

| Domain | V1 Data Status | V2 Data Status | Action Needed |
|---|---|---|---|
| Master Data | Clean, no orphans | Missing | Apply V2 schema + migrate |
| Transactional | ~15K records | Missing | Apply V2 schema + migrate |
| Reference Data | WorkerProfile (15), Color (757) | Missing | Apply V2 schema + migrate |
| Events/Audit | ProductionEvent table missing | Missing | Apply V2 schema + migrate |

## V2 Model Structure (from codebase, not yet in DB)

### Customers
- `customers.Customer` - FK: user, group; Fields: name, phone, address, address_type, status, ...
- `customers.CustomerAddress` - FK: customer; Fields: address, city, postal_code, ...
- `customers.CustomerGroup` - Fields: name, description

### Products
- `products.Product` - FK: category; Fields: name, code, unit, uom, is_active, ...
- `products.ProductPart` - Fields: name, code, unit_price, ...
- `products.ProductCategory` - Fields: name, description
- `products.ProductRevision` - FK: product; Fields: revision_number, description

### Inventory
- `inventory.UOM` - Fields: code, name (e.g., "piece", "kg", "liter")
- `inventory.UOMConversion` - FK: from_uom, to_uom; Fields: multiplier
- `inventory.ItemCategory` - Fields: name, description
- `inventory.Item` - FK: category, uom, supplier; Fields: code, name, unit_price
- `inventory.ItemSupplier` - FK: item, supplier
- `inventory.RawMaterialCategory` - Fields: name, description
- `inventory.RawMaterial` - FK: category, uom, supplier; Fields: code, name, unit_price
- `inventory.StockLocation` - Fields: name, code, location_type, parent
- `inventory.StockLot` - FK: item; Fields: lot_number, quantity, ...
- `inventory.StockBalance` - FK: item, location (unique together)
- `inventory.StockLedger` - FK: item, location, lot; Fields: quantity, transaction_type, reference
- `inventory.StockReservation` - FK: item, source_order_item; Fields: reserved_qty
- `inventory.PurchaseOrder` - FK: supplier; Fields: order_number, status, ...
- `inventory.PurchaseOrderItem` - FK: purchase_order, item; Fields: quantity, unit_price, ...

### BOM
- `bom.BOM` - FK: product, parent (self-referential); Fields: version, is_active
- `bom.BOMItem` - FK: bom; Fields: part, quantity, uom
- `bom.BOMItemMaterialRule` - FK: bom_item; Fields: material, consumption_rate

### Production
- `production.ProductionOrder` - FK: product; Fields: order_number, status, start_date, due_date, ...
- `production.ProductionOrderItem` - FK: production_order; Fields: part, quantity, ...
- `production.ProductionOperation` - FK: production_order_item; Fields: operation, status, assigned_worker, ...
- `production.ProductionBatch`, `OperationAssignment`, `OperationExecution`
- `production.WIPUnit`, `WIPTransfer`

### Sales
- `sales.CustomerOrder` - FK: customer; Fields: order_number, status, total_amount, ...
- `sales.CustomerOrderItem` - FK: customer_order, product; Fields: quantity, unit_price, ...
- `sales.OrderItemColor` - FK: customer_order_item, color; Fields: quantity

### Planning
- `planning.WorkCenter`, `Resource`, `Skill`
- `planning.Routing` - Fields: name, description
- `planning.RoutingOperation` - FK: routing; Fields: operation, work_center, ...
- `planning.RoutingDependency` - FK: routing_operation
- `planning.ProductionPart` - FK: product, part

### Quality
- `quality.QualityInspection` - FK: production_order_item, inspector
- `quality.QualityDefect` - FK: inspection; Fields: defect_code, description, quantity
- `quality.ReworkOrder`, `ReworkOrderItem`

### Shipping
- `shipping.Shipment` - FK: created_by (user); Fields: tracking_number, status, shipped_date, ...
- `shipping.ShipmentItem` - FK: shipment, order_item
- `shipping.ShipmentTracking` - FK: shipment

### Packaging
- `packaging.Package` - Fields: tracking_number, status, ...
- `packaging.PackageItem` - FK: package; Fields: customer_order_item, quantity
- `packaging.PackagingSpecification` - FK: product_part

### Painting
- `painting.PaintingProcess` - Fields: name, description
- `painting.PaintingProcessStage` - FK: process; Fields: stage_number, name, duration
- `painting.PaintingAssignmentRule` - Fields: process, stage, rule_type, ...
- `painting.PaintingSchedule` - Fields: scheduled_date, status, ...
- `painting.PaintingScheduleItem` - FK: schedule; Fields: production_order, stage

### Warehouse
- `warehouse.MaterialRequirement` - FK: production_order_item, material; Fields: quantity
- `warehouse.MaterialRequest` - Fields: status, requested_by
- `warehouse.MaterialRequestItem` - FK: request, material; Fields: quantity
- `warehouse.MaterialIssue` - Fields: issue_date, issued_by
- `warehouse.MaterialIssueItem` - FK: issue, material, source_lot; Fields: issued_quantity
- `warehouse.MaterialConsumption` - FK: issue_item, operation; Fields: consumed_quantity
- `warehouse.MaterialReturn`
- `warehouse.MaterialWaste`

## Key Schema Differences (V1 → V2)

| V1 (product) | V2 (decomposed) | Key Difference |
|---|---|---|
| `Customer` (id, name, phone, address) | `customers.Customer` + `CustomerAddress` | Address split into separate model |
| `ProductBOM` (self-referential Part) | `bom.BOM` + `bom.BOMItem` | Split into BOM container + items |
| `Part` | `products.ProductPart` + `inventory.Item` | Part maps to ProductPart or Item depending on usage |
| `Material` | `inventory.RawMaterial` + `inventory.Item` | Material maps to RawMaterial |
| `ProductionTask` | `production.ProductionOrder` + `ProductionOperation` | V1 task → V2 order+operations hierarchy |
| `ShipmentLog` | `shipping.Shipment` + `logistics` | Split into Shipment + ShipmentItem + ShipmentTracking |
| `Color` | `products.Color` (if exists in V2) or `sales.OrderItemColor` | Color as FK in order items |
| `PaintingProcess` | `painting.PaintingProcess` + `painting.PaintingProcessStage` | Stages split into separate model |
| `PaintingAssignmentRule` | `painting.PaintingAssignmentRule` | Similar structure |
| `WorkerProfile` | `planning.Resource` / `planning.Worker` | Worker becomes Resource in planning domain |
| N/A | `inventory.UOM` | V1 uses string unit field, V2 uses FK to UOM |
| N/A | `reporting.Barcode` | V2 adds barcode scanning layer |
| N/A | `reporting.MigrationMap` | V2 adds migration tracking |
| N/A | `reporting.BusinessEvent` | V2 adds event sourcing |
| N/A | `reporting.AuditLog` | V2 adds audit trail |
