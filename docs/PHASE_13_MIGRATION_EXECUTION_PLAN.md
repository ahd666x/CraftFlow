# Phase 13: Migration Execution Plan (Corrected)

## Step B — Recovery Options

### Option A: Preserve Existing V2 Data

**Status: NOT APPLICABLE** — V2 tables do not exist. Documented for future reference.

### Option B: Clean V2 Clone Rebuild (RECOMMENDED)

**Description:** Apply pending V2 schema migrations from scratch, then run
`craftflow_migrate_v2` to clone all V1 data into V2 tables.

**CRITICAL PRE-FLIGHT:** Two V1 migration name mismatches exist. The `django_migrations`
table has `product.0004_holiday_paintingprocess_order_due_date_and_more` and
`product.0005_remove_workerprofile_skill_costs_and_more`, but the files on disk are
`product.0004_paintingprocess_order_due_date_order_priority_and_more` and
`product.0005_holiday`. Django will try to apply the disk versions, which will fail
because the tables/columns already exist.

**Pre-migration fix (on local clone database only):**
```bash
# Fake the two mismatched V1 migrations so Django skips them
python manage.py migrate product 0004 --fake
python manage.py migrate product 0005 --fake
# Now apply all pending migrations
python manage.py migrate
```

**Advantages:**
- Clean schema state with no partial/mismatched data
- Full MigrationMap coverage from day one
- Deterministic results (idempotent migration command)
- All FK relationships created cleanly
- BusinessEvent and AuditLog populated during migration

**Risks:**
- Migration name mismatch on product.0004/0005 requires `--fake` pre-step
- V2 models may have evolved beyond V1 capabilities (data loss possible for unmapped fields)
- 11 pending V1 migrations (0006-0017) will run after 0004/0005 are faked
- `product.0014_remove_manual_task_fields` removes `is_manual_item_task` and
  `manual_reference_file` fields — **irreversible data loss** for those columns
  (these fields may not exist if 0004 was applied under the old name)

**Records Affected:**
- V2: 0 existing → ~15,200+ new records
  - Customer: 307, Product: 84, Part: 2078, BOM items: 786, Orders: 185, OrderItems: 395
  - ProductionOperations: 13,068, Materials: 12, PackagingUnits: 523, Shipments: 267
  - + lookup data (Color, Worker, Painting definitions, etc.)
- V1: 0 modifications (read-only by design; pending V1 migrations are schema-only)
- MigrationMap: 0 → ~16,000+ entries

**Rollback:**
- Database restore from backup: `cp db.sqlite3.backup.<timestamp> db.sqlite3`
- No git destructive operations — rollback is purely at the database level
- V1 data is never modified by V2 migrations

**Commands:**
```bash
# 1. Create backup (if not already done)
cp db.sqlite3 db.sqlite3.backup.$(date +%Y%m%d-%H%M)

# 2. Fake the two mismatched V1 migrations (fix name mismatch)
python manage.py migrate product 0004 --fake
python manage.py migrate product 0005 --fake

# 3. Apply all remaining V2 schema migrations
python manage.py migrate --settings=selvi.settings

# 4. Run data migration (idempotent)
python manage.py craftflow_migrate_v2 --settings=selvi.settings

# 5. Verify reconciliation
python manage.py craftflow_reconcile_v2 --settings=selvi.settings --json
python manage.py craftflow_reconcile_v2 --settings=selvi.settings

# 6. Run test suite
python -m django test --settings=selvi.settings -v 1

# 7. Run system check
python -m django check --settings=selvi.settings
```

**Time Estimate:** ~10-15 minutes (schema ~2 min, data migration ~5-8 min, validation ~3 min)

**Effect on Tests:**
- All 143 tests should continue to pass (tests use isolated test database)
- Reconciliation will show improved coverage after migration

---

## Step C — Migration Dependency Plan (Corrected)

### Phase 1: Foundation — UOM, Categories, Workers

**Precondition:** V2 schema applied (all migrations run). V1 data accessible.

**Source Models (V1):**
- `product.WorkerProfile` (15) → `accounts.Worker` (15) — OneToOne User, station, skills, work hours
- `product.ProductCategory` (7) → `products.ProductCategory` (7)
- `product.Holiday` (0) → seed or skip

**Target Models (V2):**
- `inventory.UOM` — **Seed** (not migrated from V1). V1 uses free-text `unit` fields
- `inventory.UOMConversion` — **Seed** standard conversions
- `inventory.ItemCategory` — **Seed** standard categories
- `inventory.RawMaterialCategory` — **Seed** standard categories
- `products.ProductCategory` — migrated from V1
- `accounts.Worker` — migrated from V1 WorkerProfile
- `planning.WorkCenter` — **Seed** based on STATION_CHOICES
- `planning.Skill` — **Seed** based on WorkerProfile.skills

**MigrationMap types:** `uom`, `item_category`, `product_category`, `worker`, `work_center`, `skill`, `raw_material_category`

**Idempotency Key:** `v1_workerprofile_<v1_pk>` for Worker; `v1_productcategory_<v1_pk>` for Category
**Reconciliation Rule:** V1 WorkerProfile count (15) == V2 accounts.Worker count (15)
**Rollback Rule:** Restore database from backup (no destructive git operations)
**Warning Policy:** V1 has no explicit UOM column; product.unit is free-text. Map to UOM.code via fuzzy matching. Warn if <90% mapped.

### Phase 2: Entities — Customers, Products, Items

**Precondition:** Phase 1 complete (Workers, Categories, UOMs exist)

**Source Models (V1):**
- `product.Customer` (307) → `customers.Customer` (307)
  - V1 fields: name, phone, address. V2 adds: email, mobile, postal_code, etc.
  - No email in V1 — leave blank or synthesize from name
- `product.Product` (84) → `products.Product` (84)
  - V1 `unit` (free text) → V2 `uom` (FK to inventory.UOM)
- `product.Part` (2078) → `products.ProductPart` + `inventory.Item`
  - Parts with `material` FK → `inventory.Item` (item_type='component')
  - All parts → `products.ProductPart`
- `product.Material` (12) → `inventory.RawMaterial` (12) + `inventory.Item` (12)
- `product.PackagingUnit` (523) → `inventory.Item` (item_type='packaging')
  - Only packaging units that represent product SKUs; not all 523 are unique items
- `product.Color` (757) → tracked via `sales.OrderItemColor` (V2)
  - Colors are order-specific, not standalone inventory items

**Target Models (V2):**
- `customers.Customer`, `customers.CustomerGroup`, `customers.CustomerAddress`
- `products.Product`, `products.ProductPart`, `products.ProductRevision`
- `inventory.Item`, `inventory.ItemCategory`, `inventory.ItemSupplier`
- `inventory.RawMaterial`, `inventory.RawMaterialCategory`
- `inventory.Supplier` — seed or migrate from V1 if Supplier table exists

**MigrationMap types:** `customer`, `customer_address`, `product`, `product_part`, `color`, `material`, `packaging_unit`, `item`, `raw_material`, `supplier`

**Idempotency Key:** `v1_<app_label>_<v1_pk>` — MigrationMap entry exists
**Reconciliation Rule:** V1 count matches V2 count for each entity type
**Rollback Rule:** Restore database from backup
**Warning Policy:** V1 Customer has no email field (fields: address, id, name, phone, user, user_id). Email must be synthesized or left blank.

### Phase 3: Part & ProductionPart Linkage

**Precondition:** Phase 2 complete (Products, Parts, Items exist)

**Source Models (V1):**
- `product.ProductBOM` (786) → `bom.BOM` + `bom.BOMItem` + `bom.BOMItemMaterialRule`
  - V1 ProductBOM fields: product, part, quantity, color_part, color_material_map(JSON),
    allow_material_override, size_affected, size_adjustment_rule
  - V2 BOMItem fields: bom, part, quantity, scrap_factor
  - V2 BOMItemMaterialRule: material_item(FK Item), quantity, rule_type, condition

**Target Models (V2):**
- `bom.BOM` — one BOM per Product (or versioned)
- `bom.BOMItem` — links BOM to ProductPart
- `bom.BOMItemMaterialRule` — maps BOMItem to material (Item) with consumption rules
  - V1 `color_material_map` → BOMItemMaterialRule entries
  - V1 `allow_material_override` → rule_type='alternative' or 'color_override'

**MigrationMap types:** `bom`, `bom_item`, `bom_item_material_rule`

**Idempotency Key:** `v1_productbom_<v1_pk>` for BOMItem
**Reconciliation Rule:** V1 ProductBOM count (786) == V2 BOMItem count (786)
**Rollback Rule:** Restore database from backup
**Warning Policy:** V1 ProductBOM `color_material_map` JSON may have complex nested structure. Verify all referenced Materials exist in V2 inventory.Item.

### Phase 4: Routing, Painting Definitions

**Precondition:** Phase 3 complete (Products, Parts, BOMs exist)

**Source Models (V1):**
- `product.PaintingProcess` (3) → `painting.PaintingProcess` (3)
  - V1: name, code, color_codes(JSON), is_active, description
  - V2 adds: estimated_time_minutes
- `product.PaintingStage` (15) → `painting.PaintingProcessStage` (15)
  - V1: order, name, duration_minutes, drying_time_minutes, required_skill, process(FK)
  - V2 adds: temperature_min/max, humidity_max, is_mandatory
- `product.PaintingAssignmentRule` (7) → `painting.PaintingAssignmentRule` (7)
  - V1 worker FK = WorkerProfile; V2 worker FK = accounts.Worker (after Phase 1)
- V1 `ProductionTask.routing_code` or similar → `planning.Routing` + `RoutingOperation`
  - V1 task has `station_name`, `step_order` — these become RoutingOperation entries

**Target Models (V2):**
- `painting.PaintingProcess`, `painting.PaintingProcessStage`
- `painting.PaintingAssignmentRule` — worker FK must reference accounts.Worker
- `planning.Routing`, `planning.RoutingOperation`, `planning.RoutingDependency`
- `planning.ProductionPart` — links Product to ProductPart (planning perspective)

**MigrationMap types:** `painting_process`, `painting_stage`, `painting_assignment_rule`, `routing`, `routing_operation`, `production_part`

**Idempotency Key:** `v1_paintingprocess_<v1_pk>` for PaintingProcess
**Reconciliation Rule:** V1 PaintingProcess count (3) == V2 count (3), Stages (15) == V2 Stages (15)
**Rollback Rule:** Restore database from backup
**Warning Policy:** V1 PaintingAssignmentRule.worker references WorkerProfile. Must map to accounts.Worker via MigrationMap from Phase 1.

### Phase 5: Orders & OrderItems

**Precondition:** Phase 2 complete (Customers, Products, Items exist)

**Source Models (V1):**
- `product.Order` (185) → `sales.CustomerOrder` (185)
  - V1 status: draft/planned/producing/completed — maps directly to V2
  - V1 Order has no `order_number` — V2 requires unique `order_number`; synthesize from V1 id
- `product.OrderItem` (395) → `sales.CustomerOrderItem` (395)
  - V1: order, product, quantity, size, unit_price, qr_code
  - V2 adds: line_total, is_custom, production_notes, estimated_delivery
- `product.OrderColor` (if exists) → `sales.OrderItemColor`

**Target Models (V2):**
- `sales.CustomerOrder`, `sales.CustomerOrderItem`
- `sales.OrderItemColor` — if V1 has OrderColor model

**MigrationMap types:** `order`, `order_item`, `order_item_color`

**Idempotency Key:** `v1_product_order_<v1_pk>` for CustomerOrder
**Reconciliation Rule:** V1 Order count (185) == V2 CustomerOrder count (185)
**Rollback Rule:** Restore database from backup
**Warning Policy:** V1 Order.status has no 'cancelled' state; V2 adds it. Map missing statuses to 'draft'.

### Phase 6: Production Orders & Operations (WIP)

**Precondition:** Phases 2-4 complete (Products, BOMs, Routing, Orders exist)

**Source Models (V1):**
- `product.Order` with status 'producing' (137 orders) → `production.ProductionOrder`
  - Creates one ProductionOrder per producing Order
- `product.ProductionTask` (13,068) → `production.ProductionOperation` (13,068)
  - V1 task: order, part, station_name, step_order, quantity, status, scanned_by, completed_at,
    painting_stage, scheduled_start/end, assigned_worker, order_item, color_part, completed_quantity
  - V2 operation: production_order, production_order_item, product, operation_name, work_center,
    sequence, status, planned_start/end, actual_start/end, completed_quantity, part, painting_stage,
    assigned_worker, order_item, color_part, scanned_by, completed_at
- `product.ProductionLog` (1679) → `production.OperationExecution`
  - V1 log: order_item, stage, user, notes, created_at
  - V2 execution: operation, worker, started_at, ended_at, quantity_produced, run_time_minutes

**Target Models (V2):**
- `production.ProductionOrder`, `production.ProductionOrderItem`
- `production.ProductionOperation`, `production.OperationExecution`
- `production.OperationAssignment` — worker assignments
- `production.ProductionBatch`, `production.ProductionBatchItem`
- `production.WIPUnit`, `production.WIPTransfer`

**MigrationMap types:** `production_order`, `production_order_item`, `production_operation`, `operation_execution`, `wip_unit`

**Idempotency Key:** `v1_product_productiontask_<v1_pk>` for ProductionOperation
**Reconciliation Rule:** V1 ProductionTask count (13,068) == V2 ProductionOperation count (13,068)
**Rollback Rule:** Restore database from backup
**Warning Policy:** This is the largest table (13K rows). Must process in batches of 1000.
V1 task status (waiting/pending/done) → V2 operation status (waiting/ready/in_progress/completed).
V1 `station_name` → V2 `operation_name` (use station_name as operation name, look up work_center).

### Phase 7: Inventory & Stock

**Precondition:** Phase 2 complete (Items, RawMaterials exist); Phase 6 partial (ProductionOrders exist)

**Source Models (V1):**
- V1 `StockMovement` → `inventory.StockLedger`
  - V1 has `StockMovement` model (in inventory app, added by migration 0001)
  - Maps to `inventory.StockLedger` entries
- `product.Material` (12) already migrated as RawMaterial in Phase 2
- V1 `product_productiontask.completed_quantity` / `quantity` → derive stock consumption

**Target Models (V2):**
- `warehouse.MaterialRequirement` — material needs per order item
- `warehouse.MaterialIssue`, `warehouse.MaterialIssueItem`
- `warehouse.MaterialConsumption` — actual consumption per operation
- `inventory.StockLedger`, `inventory.StockBalance`
- `inventory.StockReservation`, `inventory.StockLot`
- `warehouse.MaterialRequest`, `warehouse.MaterialRequestItem`
- `warehouse.MaterialReturn`, `warehouse.MaterialWaste`

**MigrationMap types:** `stock_ledger`, `stock_balance`, `material_requirement`, `material_issue`, `stock_reservation`

**Idempotency Key:** `v1_stockmovement_<v1_pk>` for StockLedger
**Reconciliation Rule:** Stock records derived from V1 production data — no direct 1:1 mapping
**Rollback Rule:** Restore database from backup
**Warning Policy:** V1 does not have explicit stock tables. Stock must be synthesized from ProductionTask completions and StockMovement records. Warn if StockMovement count doesn't match expected ledger entries.

### Phase 8: Barcodes, Packaging, Shipping

**Precondition:** Phase 6 complete (ProductionOrders exist), Phase 5 complete (Orders exist)

**Source Models (V1):**
- `product.ShipmentLog` (267) → `shipping.Shipment` + `shipping.ShipmentItem` + `shipping.ShipmentTracking`
  - V1 ShipmentLog: packaging_unit(FK), plate_number, shipped_at, shipped_by(User), delivery_notes
  - V1 ShipmentLog tracks individual packaging unit shipments
  - V2 Shipment: customer_order(FK), customer(FK), shipment_number, status, shipment_date, etc.
  - One V2 Shipment can group multiple V1 ShipmentLogs by Order
- `product.PackagingUnit` (523) → `packaging.Package` (523)
  - V1: order_item(FK), unit_number, qr_code, is_packed, is_shipped, packed_at/by, shipped_at/by
  - V2 Package: customer_order_item(FK), production_order_item(FK nullable), package_number,
    status, qr_code(ImageField upload_to='qr/packaging/'), packed_at/by
- `product.OrderItem.qr_code` (ImageField, upload_to='qr/') → `reporting.Barcode`
  - Existing QR codes from V1 → V2 Barcode records

**Target Models (V2):**
- `shipping.Shipment`, `shipping.ShipmentItem`, `shipping.ShipmentTracking`
- `packaging.Package`, `packaging.PackageItem`, `packaging.PackagingSpecification`
- `reporting.Barcode` — assign barcodes to migrated records for tracking
  - V1 QR files at `media/qr/` → V2 Barcode records with `legacy_entity_type` and `legacy_entity_id`

**MigrationMap types:** `shipment`, `shipment_item`, `package`, `package_item`, `packaging_spec`, `barcode`

**Idempotency Key:** `v1_shipmentlog_<v1_pk>` for ShipmentItem
**Reconciliation Rule:** V1 ShipmentLog count (267) should match V2 ShipmentItem count (267)
**Rollback Rule:** Restore database from backup
**Warning Policy:** V1 ShipmentLog FK is `packaging_unit_id` (confirmed from model). V2 Shipment groups
by CustomerOrder. Verify all PackagingUnit→Package mappings from Phase 6. Barcode assignment must be
unique — check for duplicates.

### Phase 9: Events, Audit, Legacy References

**Precondition:** All data migration phases complete (all target records exist); V1 migration 0015 applied

**Source Models (V1):**
- `product.ProductionEvent` — requires V1 migration 0015 to have been applied (creates `product_productionevent` table)
  - Fields: task(FK), order(FK), order_item(FK nullable), station_name, event_type, quantity,
    old_status, new_status, old_worker(FK User), new_worker(FK User), user(FK User), created_at
- `product.ProductionLog` (1679) → `reporting.BusinessEvent`
  - V1 log: order_item, stage, user, notes, created_at
  - V2 BusinessEvent: category, event_type, title, description, occurred_at, content_type, object_id,
    metadata(JSON), legacy_reference, legacy_app, legacy_model, legacy_id

**Target Models (V2):**
- `reporting.BusinessEvent` — event sourcing for all migrated records
- `reporting.AuditLog` — audit trail for all migration operations
- `reporting.Barcode` — populate with V1 QR references from Phase 8

**MigrationMap types:** `business_event`, `audit_log`

**Idempotency Key:** `v1_productionevent_<v1_pk>` for BusinessEvent
**Reconciliation Rule:** V1 event sources (ProductionLog: 1679, ProductionEvent: depends on 0015) should produce
equivalent V2 BusinessEvent entries
**Rollback Rule:** Restore database from backup
**Warning Policy:** V1 `product_productionevent` table does not exist if migration 0015 hasn't been applied.
Migration 0015 depends on 0014, which depends on 0013, etc. If migrations are applied in dependency order,
the table will exist by the time Phase 9 runs.

## Product Migration Analysis (0006-0017)

### 0006_paintingassignmentrule
- **Operation:** CreateModel `PaintingAssignmentRule` (FK to WorkerProfile, PaintingStage, PaintingProcess)
- **Data loss risk:** None (new table)
- **Dependency:** product.0005_holiday
- **Reversible:** Yes (DeleteModel)

### 0007_paintingassignmentrule_rule_type_and_more
- **Operation:** AddField `rule_type`, AlterField `priority`
- **Data loss risk:** None
- **Dependency:** product.0006
- **Reversible:** Yes (RemoveField, AlterField back)

### 0008_workerprofile_work_hours
- **Operation:** AddField work_start/end, break_start/end to WorkerProfile
- **Data loss risk:** None (all have defaults)
- **Dependency:** product.0007
- **Reversible:** Yes (RemoveField)

### 0009_productiontask_indexes
- **Operation:** AddIndex × 3 on ProductionTask
- **Data loss risk:** None
- **Dependency:** product.0008
- **Reversible:** Yes (RemoveIndex)

### 0010_rename_skill_costs_workerprofile_skill_priority
- **Operation:** RenameField `skill_costs` → `skill_priority` on WorkerProfile
- **Data loss risk:** None (rename)
- **Dependency:** product.0009
- **Reversible:** Yes (renames back)

### 0011_alter_workerprofile_skill_priority
- **Operation:** AlterField `skill_priority` type to JSONField
- **Data loss risk:** Minimal (JSONField change)
- **Dependency:** product.0010
- **Reversible:** Yes (alters back)

### 0012_rename_prod_task_station_start_idx...
- **Operation:** RenameIndex × 3, AddField `completed_quantity` to ProductionTask
- **Data loss risk:** None
- **Dependency:** product.0011
- **Reversible:** Yes (renames back, removes field)

### 0013_backfill_completed_quantity
- **Operation:** RunPython data migration — sets `completed_quantity = quantity` for tasks with status='done'
- **Data loss risk:** None (data correction)
- **Dependency:** product.0012
- **Reversible:** Yes (noop — RunPython.noop)

### 0014_remove_manual_task_fields
- **Operation:** RenameIndex × 3, RemoveField `is_manual_item_task`, RemoveField `manual_reference_file`
- **Data loss risk:** **YES** — removes two fields from ProductionTask. Any data in these fields is permanently lost.
  However, these fields were likely never populated (they appear to be unused manual task fields).
- **Dependency:** product.0013
- **Reversible:** Partially — RemoveField backward adds fields back, but data is lost. RenameIndex backward requires exact old names.
- **CRITICAL:** If the tables from migration 0004 were created under the old name `0004_holiday_paintingprocess_order_due_date_and_more`
  (not the current file name), these fields may not exist on the table, causing the migration to fail.

### 0015_productionevent
- **Operation:** CreateModel `ProductionEvent` (FK to Task, Order, OrderItem, User)
- **Data loss risk:** None (new table)
- **Dependency:** product.0014, settings.AUTH_USER_MODEL
- **Reversible:** Yes (DeleteModel)
- **NOTE:** This creates the `product_productionevent` table needed for Phase 9.

### 0016_material_consumption_per_unit_material_raw_material
- **Operation:** AddField `consumption_per_unit` (DecimalField, default=1), AddField `raw_material` (FK to inventory.RawMaterial)
- **Data loss risk:** None (additive, nullable FK)
- **Dependency:** inventory.0001_initial, product.0015
- **Reversible:** Yes (RemoveField)

### 0017_shipmentlog_delivery_notes
- **Operation:** AddField `delivery_notes` to ShipmentLog
- **Data loss risk:** None (additive, blank=True)
- **Dependency:** product.0016
- **Reversible:** Yes (RemoveField)

## Rollback Runbook

**No destructive git operations (git checkout, git reset) will be used.**

For the disposable schema migration test:
1. Database file is a copy (`db.sqlite3.v2-schema-test`) — deletion of this file is safe
2. V1 `db.sqlite3` is never modified

For production deployment:
1. Always create a backup before running migrations: `cp db.sqlite3 db.sqlite3.backup.<timestamp>`
2. Test all migrations on a disposable copy first
3. Rollback = restore from backup file
4. No git operations needed for rollback
