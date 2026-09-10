# Phase 13: Migration Execution Plan (Steps B & C)

## Step B — Recovery Options

### Option A: Preserve Existing V2 Data

**Description:** Only applies if V2 tables already exist with data (not the current state).
Schema migration would be skipped for apps that already have tables.
Data migration would preserve records that have valid MigrationMap entries
and quarantine unmapped records.

**Status: NOT APPLICABLE to current state** — V2 tables do not exist.
Documented for future reference (e.g., partial migration scenario).

### Option B: Clean V2 Clone Rebuild (RECOMMENDED)

**Description:** Apply V2 schema migrations from scratch, then run
`craftflow_migrate_v2` to clone all V1 data into V2 tables.

**Advantages:**
- Clean schema state with no partial/mismatched data
- Full MigrationMap coverage from day one
- Deterministic results (idempotent migration command)
- All FK relationships created cleanly
- BusinessEvent and AuditLog populated during migration

**Risks:**
- Schema migration must succeed without errors (dependencies exist)
- V2 models may have evolved beyond V1 capabilities (data loss possible for unmapped fields)
- 11 pending V1 migrations (0006-0017) will also run, potentially modifying V1 tables
  — mitigated by: V1 data is preserved, migrations are additive/schema-only (verified: 0015 creates ProductionEvent table, 0017 adds delivery_notes field to ShipmentLog)

**Records Affected:**
- V2: 0 existing records → 15,119+ new records (Customer: 307, Product: 84, BOM: 786, Order: 185, OrderItem: 395, ProductionTask: 13,068, Material: 12, ShipmentLog: 267, + all lookup/reference data)
- V1: 0 modifications (read-only by design; pending V1 migrations are schema-only)
- MigrationMap: 0 → ~16,000+ entries

**Rollback:**
- If V2 migrations haven't been committed: `git checkout .` on migration directory
- If migrations applied but migration failed: `python manage.py migrate <app> zero`
- V1 data is never modified — rollback is safe
- Keep `db.sqlite3.backup.20260908-1919` as emergency restore point

**Commands:**
```bash
# 1. Create backup (if not already done)
cp db.sqlite3 db.sqlite3.backup.$(date +%Y%m%d-%H%M)

# 2. Apply all V2 schema migrations (including pending V1 migrations)
python -m django migrate --settings=selvi.settings

# 3. Run data migration (idempotent)
python -m django craftflow_migrate_v2 --settings=selvi.settings

# 4. Verify reconciliation
python -m django craftflow_reconcile_v2 --settings=selvi.settings --json
python -m django craftflow_reconcile_v2 --settings=selvi.settings

# 5. Run test suite
python -m django test --settings=selvi.settings -v 1
```

**Time Estimate:** ~10-15 minutes (schema ~2 min, data migration ~5-8 min, validation ~3 min)

**Effect on Tests:**
- All 143 tests should continue to pass (tests use isolated test database)
- Reconciliation tests in `reporting/tests/test_reconciliation.py` will now show
  all entities reconciled instead of mismatches on missing tables

---

## Step C — Migration Dependency Plan

Migration order defines the sequence in which V1 data is cloned into V2 tables.
Each phase depends on successful completion of the previous phase (referential integrity).

### Phase 1: Foundation — UOM, Categories, Workers

**Precondition:** None (creates lookup tables first)

**Source Models (V1):**
- None — lookup tables are seeded (not migrated from V1)

**Target Models (V2):**
- `inventory.UOM` — seed with standard units (piece, kg, meter, liter, set)
- `inventory.UOMConversion` — between standard UOMs
- `inventory.ItemCategory` — seed with standard categories
- `inventory.RawMaterialCategory` — seed with standard categories
- `products.ProductCategory` — migrate from `product.ProductCategory`
- `planning.WorkerProfile` — migrate from `product.WorkerProfile` → `planning.Resource`
- `planning.WorkCenter` — seed or migrate from V1 work centers
- `planning.Skill` — seed or migrate from V1 skill sets

**MigrationMap types:** `uom`, `item_category`, `product_category`, `worker`, `work_center`, `skill`, `raw_material_category`

**Idempotency Key:** `uom_<code>_v1` — skip if UOM with code already exists
**Reconciliation Rule:** V1 ProductCategory count (7) == V2 ProductCategory count (7)
**Rollback Rule:** `DELETE FROM inventory_uom WHERE legacy_ref IS NOT NULL`
**Warning Policy:** V1 has no explicit UOM column; product.unit is free-text. Map to standard UOMs with 90% threshold (warn if <90% mapped).

### Phase 2: Entities — Customers, Products, Items

**Precondition:** Phase 1 complete (Categories, UOMs exist)

**Source Models (V1):**
- `product.Customer` (307) → `customers.Customer` (307)
- `product.CustomerAddress` (implied from address field) → `customers.CustomerAddress`
- `product.Product` (84) → `products.Product` (84)
- `product.Part` (2078) → `products.ProductPart` (2078) + `inventory.Item` (subset)
- `product.ProductCategory` (7) → `products.ProductCategory` (7, already done in Phase 1)
- `product.Color` (757) → `products.Color` or dedicated Color table
- `product.Material` (12) → `inventory.RawMaterial` (12)
- `product.PackagingUnit` (523) → `inventory.Item` or dedicated packaging table

**Target Models (V2):**
- `customers.Customer`, `customers.CustomerAddress`
- `products.Product`, `products.ProductPart`, `products.ProductRevision`
- `inventory.Item`, `inventory.ItemCategory`, `inventory.RawMaterial`
- `inventory.ItemSupplier`

**MigrationMap types:** `customer`, `customer_address`, `product`, `product_part`, `color`, `material`, `packaging_unit`, `item`

**Idempotency Key:** `v1_<app_label>_<v1_pk>` — MigrationMap entry exists for this V1 row
**Reconciliation Rule:** Count match + all migrated records have MigrationMap entry
**Rollback Rule:** `DELETE FROM <v2_table> WHERE migration_map_id IS NOT NULL` (preserves non-V1 records)
**Warning Policy:** Alert if duplicate Customer.name+phone found (V1 has no email field, dedup harder)

### Phase 3: Part & ProductionPart Linkage

**Precondition:** Phase 2 complete (Products, Parts, Items exist)

**Source Models (V1):**
- `product.ProductBOM` (786) — BOM entries linking Product→Part
- `product.Part` (2078) — already migrated as ProductPart in Phase 2

**Target Models (V2):**
- `bom.BOM` — one BOM per Product (or versioned)
- `bom.BOMItem` — links BOM to Part
- `planning.ProductionPart` — links Product to Part (planning perspective)
- `bom.BOMItemMaterialRule` — if material consumption rules exist in V1 ProductBOM

**MigrationMap types:** `bom`, `bom_item`, `production_part`

**Idempotency Key:** `bom_<v1_productbom_pk>` for BOMItem; `bom_<v1_product_pk>` for BOM header
**Reconciliation Rule:** V1 ProductBOM count (786) == V2 BOMItem count (786)
**Rollback Rule:** Cascade delete BOMs and BOMItems created from V1
**Warning Policy:** V1 ProductBOM is self-referential (Part→Part). Verify all Part FKs resolve in V2 ProductPart.

### Phase 4: Routing, Painting Definitions

**Precondition:** Phase 3 complete (Products, Parts, BOMs exist)

**Source Models (V1):**
- `product.PaintingProcess` (3) → `painting.PaintingProcess`
- `product.PaintingStage` (15) → `painting.PaintingProcessStage`
- `product.PaintingAssignmentRule` (7) → `painting.PaintingAssignmentRule`
- V1 ProductionTask routing info → `planning.Routing`, `planning.RoutingOperation`

**Target Models (V2):**
- `painting.PaintingProcess`, `painting.PaintingProcessStage`
- `painting.PaintingAssignmentRule`
- `planning.Routing`, `planning.RoutingOperation`, `planning.RoutingDependency`

**MigrationMap types:** `painting_process`, `painting_stage`, `painting_assignment_rule`, `routing`, `routing_operation`

**Idempotency Key:** `painting_process_<v1_id>` for PaintingProcess
**Reconciliation Rule:** V1 PaintingProcess count (3) == V2 count (3), V1 Stages (15) == V2 Stages (15)
**Rollback Rule:** Delete painting/routing records with `legacy_app='product'`
**Warning Policy:** PaintingAssignmentRule may reference workers that must exist in planning.Resource

### Phase 5: Orders & OrderItems

**Precondition:** Phase 2 complete (Customers, Products exist)

**Source Models (V1):**
- `product.Order` (185) → `sales.CustomerOrder`
- `product.OrderItem` (395) → `sales.CustomerOrderItem`
- `product.OrderItemColor` (if exists) → `sales.OrderItemColor`

**Target Models (V2):**
- `sales.CustomerOrder`, `sales.CustomerOrderItem`
- `sales.OrderItemColor` (optional)
- `sales.SalesQuotation` (if V1 has quotations)

**MigrationMap types:** `order`, `order_item`, `order_item_color`

**Idempotency Key:** `v1_product_order_<v1_pk>` for CustomerOrder
**Reconciliation Rule:** V1 Order count (185) == V2 CustomerOrder count (185)
**Rollback Rule:** `DELETE FROM sales_customerorderitem WHERE migration_map_id IS NOT NULL; DELETE FROM sales_customerorder WHERE migration_map_id IS NOT NULL`
**Warning Policy:** Order status mapping (V1: draft/planned/producing/completed → V2: pending/confirmed/in_progress/completed). Verify all V1 statuses have a V2 mapping.

### Phase 6: Production Orders & Operations (WIP)

**Precondition:** Phases 2-4 complete (Products, BOMs, Routing, Orders exist)

**Source Models (V1):**
- `product.Order` with status 'producing' (137) → `production.ProductionOrder`
- `product.ProductionTask` (13,068) → `production.ProductionOrderItem` + `production.ProductionOperation`
- `product.ProductionLog` (1679) → `production.OperationExecution`

**Target Models (V2):**
- `production.ProductionOrder`, `production.ProductionOrderItem`
- `production.ProductionOperation`, `production.OperationExecution`
- `production.OperationAssignment`, `production.ProductionBatch`
- `production.WIPUnit`, `production.WIPTransfer`

**MigrationMap types:** `production_order`, `production_order_item`, `production_operation`, `operation_execution`, `wip_unit`

**Idempotency Key:** `v1_product_productiontask_<v1_pk>` for ProductionOperation
**Reconciliation Rule:** V1 ProductionTask count (13,068) == V2 ProductionOperation count (13,068)
**Rollback Rule:** Truncate production tables with legacy references
**Warning Policy:** This is the largest table (13K rows). V1 task→operation split may 1:1 or 1:N. Log any mismatches. V1 task status (done/pending/waiting) → V2 operation status mapping (completed/waiting/in_progress).

### Phase 7: Inventory & Stock

**Precondition:** Phase 2 complete (Items, RawMaterials exist); Phase 6 partial (ProductionOrders exist)

**Source Models (V1):**
- `product.ProductBOM` (as material consumption) → `warehouse.MaterialRequirement`
- V1 `product.Material` (12) already migrated as RawMaterial in Phase 2

**Target Models (V2):**
- `warehouse.MaterialRequirement`, `warehouse.MaterialRequest`
- `warehouse.MaterialIssue`, `warehouse.MaterialIssueItem`
- `warehouse.MaterialConsumption`
- `warehouse.StockBalance`, `warehouse.StockLedger`, `warehouse.StockReservation`
- `warehouse.MaterialReturn`, `warehouse.MaterialWaste`

**MigrationMap types:** `material_requirement`, `material_request`, `material_issue`, `stock_ledger`, `stock_balance`

**Idempotency Key:** `v1_product_order_<order_pk>_material_<material_index>` for MaterialRequirement
**Reconciliation Rule:** Inventory tables start empty, populated during production execution
**Rollback Rule:** Clean warehouse records with `legacy_app='product'`
**Warning Policy:** V1 does not have explicit stock tables; stock is calculated from ProductionTask completions. This phase is partially synthetic data generation.

### Phase 8: Barcodes, Packaging, Shipping

**Precondition:** Phase 6 complete (ProductionOrders exist)

**Source Models (V1):**
- `product.ShipmentLog` (267) → `shipping.Shipment` + `shipping.ShipmentItem` + `shipping.ShipmentTracking`
- `product.PackagingUnit` (523) → `packaging.Package` + `packaging.PackageItem`
- `product.PackagingUnit` → `packaging.PackagingSpecification`

**Target Models (V2):**
- `shipping.Shipment`, `shipping.ShipmentItem`, `shipping.ShipmentTracking`
- `packaging.Package`, `packaging.PackageItem`, `packaging.PackagingSpecification`
- `reporting.Barcode` — assign barcodes to migrated records for tracking

**MigrationMap types:** `shipment`, `shipment_item`, `package`, `package_item`, `packaging_spec`, `barcode`

**Idempotency Key:** `v1_product_shipmentlog_<v1_pk>` for Shipment
**Reconciliation Rule:** V1 ShipmentLog count (267) == V2 Shipment count (267)
**Rollback Rule:** Clean shipping/packaging/barcode with `legacy_app='product'`
**Warning Policy:** V1 ShipmentLog has limited fields. V2 adds tracking detail that must be synthesized. Barcode assignment must be unique — check for collisions.

### Phase 9: Events, Audit, Legacy References

**Precondition:** All data migration phases complete (all target records exist)

**Source Models (V1):**
- `product.ProductionEvent` (0 — table missing, requires V1 migration 0015)
- V1 `product.ProductionLog` (1679) → `reporting.BusinessEvent`
- V1 `product.ProductionTask` status changes → `reporting.BusinessEvent` (event type: status_change)

**Target Models (V2):**
- `reporting.BusinessEvent` — event sourcing for all migrated records
- `reporting.AuditLog` — audit trail for all migration operations
- `reporting.MigrationMap` — already populated throughout phases 1-8

**MigrationMap types:** `business_event`, `audit_log`

**Idempotency Key:** `v1_event_<v1_pk>_<timestamp>` for BusinessEvent
**Reconciliation Rule:** V1 event sources (ProductionLog: 1679, ProductionEvent: depends on 0015) should produce equivalent V2 BusinessEvent entries
**Rollback Rule:** `DELETE FROM reporting_businessevent WHERE legacy_app='product'; DELETE FROM reporting_auditlog WHERE legacy_app='product'`
**Warning Policy:** V1 `production_productionevent` table does not exist yet (needs migration 0015).
If migration 0015 hasn't been applied before Phase 9, ProductionEvents cannot be migrated — log as data gap.

## Critical Warnings

1. **V1 pending migrations (0006-0017)**: Running `migrate` will apply these too.
   Verify each is additive/schema-only before proceeding.
   - 0015 creates `product_productionevent` table (needed for Phase 9)
   - 0017 adds `delivery_notes` field to ShipmentLog (additive)

2. **No `email` field on V1 Customer**: V2 Customer model likely expects email.
   Must synthesize or leave null.

3. **V1 free-text `unit` field**: V1 uses `Product.unit` as free text; V2 uses UOM FK.
   Need fuzzy matching (e.g., "piece" → UOM.code="piece", "kg" → UOM.code="kg").

4. **13,068 ProductionTasks**: Largest table. Migration command must handle batch processing
   in chunks of 1000 to avoid memory issues.

5. **V1 has no StockLedger/StockBalance**: V2 inventory model expects stock movements.
   Must synthesize from ProductionTask completion data (ProductionLog entries where quantity changed).

6. **ShipmentLog FK column**: `product_shipmentlog` table structure differs from assumed `order_id`.
   Must inspect actual V1 schema before migrating shipments.
