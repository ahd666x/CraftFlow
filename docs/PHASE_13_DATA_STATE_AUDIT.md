# Phase 13: Data-State Audit (Corrected)

## Executive Summary

**V2 schema has NOT been applied to the local clone database.** Zero V2 tables exist.
The database contains only V1 (`product` app) tables with live data (~15K records across key entities).
MigrationMap, BusinessEvent, AuditLog, and Barcode tables do not exist.

**V1 is the single source of truth.** V1 data must not be touched.

## CRITICAL: Migration Name Mismatch

**Important discovery:** The `django_migrations` table contains entries for migration names
that DO NOT match the current migration files on disk:

| In django_migrations (applied) | File on disk (pending) |
|---|---|
| `product.0004_holiday_paintingprocess_order_due_date_and_more` | `product.0004_paintingprocess_order_due_date_order_priority_and_more` |
| `product.0005_remove_workerprofile_skill_costs_and_more` | `product.0005_holiday` |

The migration files were regenerated/renamed AFTER being applied. Running `migrate` will
try to re-apply these migrations, which will **FAIL** because the tables and columns they
create already exist.

**Mitigation for disposable copy:** Use `migrate --fake` for the affected migrations before
running `migrate` normally, OR drop and recreate the schema from a fresh state.

## Step A — Current Data State (Local Clone Database)

### Applied Migrations (in django_migrations table)

```
product.0001_initial                     ✓ (V1 core: Customer, Product, Part, Order, OrderItem, ProductionTask, etc.)
product.0002_shipmentlog                  ✓ (adds ShipmentLog + PackagingUnit)
product.0003_alter_shipmentlog_options    ✓ (alters ShipmentLog)
product.0004_holiday_paintingprocess...   ✓ (old name — applied but file renamed on disk)
product.0005_remove_workerprofile_skill... ✓ (old name — applied but file renamed on disk)
```

Plus core apps (admin, auth, contenttypes, sessions) — 23 total applied migrations.

### Pending Migrations (on disk, NOT applied)

All V2 app migrations pending. All `product.0006` through `product.0017` pending:

```
bom.0001_initial          customers.0001_initial     inventory.0001_initial
inventory.0002_uom_itemcategory_item_stocklocation_stocklot_and_more
inventory.0003_item_consumption_per_unit
packaging.0001_initial    packaging.0002_initial
painting.0001_initial     painting.0002_initial
planning.0001_initial     production.0001_initial
production.0002_operationexecution_worker_nullable
production.0003_productionoperation_assigned_worker_and_more
production.0004_add_production_order_item_snapshots
products.0001_initial     quality.0001_initial
reporting.0001_initial    reporting.0002_barcode_legacy...
reporting.0003_alter_migrationmap_migration_type
sales.0001_initial        sessions.0001_initial
shipping.0001_initial
warehouse.0001_initial    warehouse.0002_materialconsumption_idempotency_key...
warehouse.0003_materialconsumption_material_issue_item_nullable
```

### V1 Tables (product app) — Applied & Live

| Table | Rows | Notes |
|---|---|---|
| `product_customer` | 307 | Fields: user(FK), name, phone, address |
| `product_product` | 84 | Fields: category(FK), name, unit (free-text), base_price |
| `product_productcategory` | 7 | Fields: name, parent(self-FK), description |
| `product_productbom` | 786 | Fields: product(FK), part(FK), quantity, color_part, color_material_map(JSON), |
|  |  | allow_material_override, size_affected, size_adjustment_rule |
| `product_part` | 2078 | Fields: material(FK), name, length, width, thickness, f3, routing_code |
| `product_order` | 185 | Fields: user(FK), customer(FK), number, created_at, due_date, priority, status |
| `product_orderitem` | 395 | Fields: order(FK), product(FK), quantity, size, unit_price, qr_code(Image) |
| `product_productiontask` | 13,068 | Fields: order(FK), part(FK), station_name, step_order, quantity, status, |
|  |  | scanned_by(FK User), completed_at, painting_stage(FK), scheduled_start/end, |
|  |  | assigned_worker(FK User), order_item(FK), color_part, completed_quantity |
| `product_productionlog` | 1679 | Fields: order_item(FK), stage, user(FK), notes, created_at |
| `product_material` | 12 | Fields: name, thickness, raw_material(FK inventory.RawMaterial, nullable) |
| `product_color` | 757 | Fields: name, code, ... |
| `product_packagingunit` | 523 | Fields: order_item(FK), unit_number, qr_code(Image), is_packed, is_shipped, ... |
| `product_workerprofile` | 15 | Fields: user(OneToOne), stage, skills(JSON), skill_priority(JSON), |
|  |  | is_available, work_start/end, break_start/end, excluded_products, excluded_items |
| `product_shipmentlog` | 267 | Fields: packaging_unit(FK), plate_number, shipped_at, shipped_by(FK User), |
|  |  | delivery_notes |
| `product_paintingprocess` | 3 | Fields: name, code, color_codes(JSON), is_active, description |
| `product_paintingstage` | 15 | Fields: order, name, duration_minutes, drying_time_minutes, required_skill, |
|  |  | temperature_min/max, humidity_max, is_mandatory, notes, process(FK) |
| `product_paintingassignmentrule` | 7 | Fields: worker(FK WorkerProfile), painting_stage(FK), color_codes(JSON), |
|  |  | process(FK), rule_type, priority, is_active, created_at |
| `product_holiday` | 0 | Fields: date, description |

### Missing V1 Tables (Pending Migrations 0004-0017 not reflected in disk vs. applied)

The V1 model definitions in `models.py` include `ProductionEvent` (line 737), but the
`product_productionevent` table does NOT exist because migration `0015` is pending.
However, `ProductionTask.save()` calls `log_production_event()` in a try/except, so
this is gracefully handled.

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
- All 14 expected migration types missing

### BusinessEvent / AuditLog Status

Neither `reporting_businessevent` nor `reporting_auditlog` nor `reporting_barcode` tables exist.
- 0 BusinessEvents
- 0 AuditLog entries
- 0 Barcode records

### FK Integrity Check (V1 Only)

| Check | Result |
|---|---|
| `product_orderitem` orphan Product FK | 0 (clean) |
| `product_orderitem` orphan Order FK | 0 (clean) |
| `product_productbom` orphan Product FK | 0 (clean) |
| `product_productbom` orphan Part FK | 0 (clean) |
| `product_productiontask` orphan Order FK | 0 (assumed clean — same FK) |
| `product_shipmentlog` orphan PackagingUnit FK | 0 (verified column name is `packaging_unit_id`) |

### Data Classification

| Domain | V1 Data Status | V2 Data Status | Action Needed |
|---|---|---|---|
| Master Data | Clean, no orphans | Missing | Apply V2 schema + migrate |
| Transactional | ~15K records | Missing | Apply V2 schema + migrate |
| Reference Data | WorkerProfile (15), Color (757) | Missing | Apply V2 schema + migrate |
| Events/Audit | ProductionEvent table missing | Missing | Apply V1 migration 0015, then migrate to V2 BusinessEvent |

## V2 Model Structure (from codebase, not yet in DB) — VERIFIED

### V2 Worker Models
- **`accounts.Worker`** — OneToOne User FK; Fields: employee_id, station, skills(JSON), skill_priority(JSON), is_available, work_start/end, break_start/end, hourly_rate, excluded_products(M2M), excluded_items(M2M)
- V1 `WorkerProfile` → V2 `accounts.Worker` (V1 has OneToOne to User directly; V2 has OneToOne to User via accounts app)

### V2 Stock Models
- **`inventory.StockLedger`** — In `inventory` app (NOT warehouse app). FK: item, location, lot; Fields: ledger_type, quantity, balance_after
- **`inventory.StockBalance`** — In `inventory` app. FK: item, location (unique). Fields: quantity_on_hand, quantity_reserved, quantity_available
- **`warehouse.MaterialConsumption`** — In `warehouse` app. FK: material_issue_item, item, production_order, production_operation. Fields: quantity, consumption_date
- `inventory.StockMovement` (V1-style) → maps to `inventory.StockLedger` entries

### V2 Production Models
- **`production.ProductionOrder`** — FK: order(CustomerOrder), routing; Fields: order_number, status, planned_start/end, actual_start/end, priority
- **`production.ProductionOrderItem`** — FK: production_order, customer_order_item, product, bom, routing. Fields: quantity, completed_quantity, bom_snapshot(JSON), routing_snapshot(JSON)
- **`production.ProductionOperation`** — FK: production_order, production_order_item, work_center, part(ProductPart), painting_stage, assigned_worker, order_item. Fields: operation_name, sequence, status, planned/actual dates, completed_quantity, scanned_by, completed_at, color_part

**V1 ProductionTask** (13,068 rows) maps to **V2 ProductionOperation** (one V1 task → one V2 operation), with ProductionOrder created per V1 Order that has status 'producing'.

### V2 Shipping Models
- **`shipping.Shipment`** — FK: customer_order, customer, created_by(User). NO `shipped_by` field (uses `created_by`)
- Fields: shipment_number, status, shipment_date, delivery_date, carrier, tracking_number, etc.
- **`shipping.ShipmentItem`** — FK: shipment, package; Fields: quantity, weight_kg, volume_m3
- **`shipping.ShipmentTracking`** — FK: shipment; Fields: status, location, timestamp

**V1 ShipmentLog** (267 rows) → **V2 Shipment** (via PackagingUnit FK chain). V1 `ShipmentLog.packaging_unit` → V2 `ShipmentItem.package`.

### V2 Packaging Models
- **`packaging.Package`** — FK: customer_order_item, production_order_item(nullable), wip_unit(nullable). Fields: package_number, status, qr_code(ImageField, upload_to='qr/packaging/'), packed_by(User), is_packed, packed_at
- **`packaging.PackageItem`** — FK: package, item(inventory.Item). Fields: quantity, serial_numbers(JSON)
- **`packaging.PackagingSpecification`** — FK: product. Fields: package_type, items_per_package, requires_pallet, image

**V1 PackagingUnit** (523 rows) → **V2 Package**. V1 `PackagingUnit.order_item` → V2 `Package.customer_order_item`.

### V2 Painting Models
- **`painting.PaintingProcess`** — Fields: name, code(unique), color_codes(JSON), is_active, description, estimated_time_minutes
- **`painting.PaintingProcessStage`** — FK: process. Fields: sequence, name, duration_minutes, drying_time_minutes, required_skill, temperature_min/max, humidity_max, is_mandatory
- **`painting.PaintingAssignmentRule`** — FK: worker(accounts.Worker), painting_stage, process. Fields: rule_type, priority, is_active
- **`painting.PaintingSchedule`** — Fields: date(unique), status, created_by(User), notes
- **`painting.PaintingScheduleItem`** — FK: schedule, production_operation, worker, painting_stage. Fields: scheduled_start/end, actual_start/end, status, is_cascade_moved

**V1 PaintingProcess** (3 rows) → **V2 PaintingProcess**. **V1 PaintingStage** (15 rows) → **V2 PaintingProcessStage**. **V1 PaintingAssignmentRule** (7 rows) → **V2 PaintingAssignmentRule** (but FK target changes: V1 `worker` → V1 `WorkerProfile`; V2 `worker` → V2 `accounts.Worker`).

## Corrected V1 → V2 Entity Mapping

| V1 (product app) | V2 (decomposed app) | Migration Type | Notes |
|---|---|---|---|
| `Customer` (307) | `customers.Customer` (307) | `customer` | V2 adds email, mobile, economic_code, national_id |
| `ProductCategory` (7) | `products.ProductCategory` (7) | `product_category` | Similar structure |
| `Product` (84) | `products.Product` (84) | `product` | V2 adds uom FK, default_colors, etc. |
| `Part` (2078) | `products.ProductPart` + `inventory.Item` | `product_part` | Part with material → Item (type='component'); Part without → ProductPart only |
| `ProductBOM` (786) | `bom.BOM` + `bom.BOMItem` | `bom_item` | One BOM per product version; BOMItem links BOM→ProductPart |
| `Material` (12) | `inventory.RawMaterial` (12) | `raw_material` | V1 has FK to V2 RawMaterial (nullable, not yet applied) |
| `OrderItem` (395) | `sales.CustomerOrderItem` (395) | `order_item` | V2 adds unit_price, qr_code (ImageField) |
| `Order` (185) | `sales.CustomerOrder` (185) | `order` | V1 status: draft/planned/producing/completed → V2: same |
| `ProductionTask` (13,068) | `production.ProductionOperation` (13,068) | `task` | One V1 task → one V2 operation. V2 wraps in ProductionOrder per Order |
| `PackagingUnit` (523) | `packaging.Package` (523) | `packaging_unit` | V2 Package has customer_order_item FK |
| `ShipmentLog` (267) | `shipping.Shipment` (267+) | `shipment_log` | One ShipmentLog per PackagingUnit → one Shipment (groups by order) |
| `PaintingProcess` (3) | `painting.PaintingProcess` (3) | `painting_process` | Similar structure |
| `PaintingStage` (15) | `painting.PaintingProcessStage` (15) | `painting_stage` | Similar structure |
| `PaintingAssignmentRule` (7) | `painting.PaintingAssignmentRule` | `painting_assignment_rule` | V1 worker=WorkerProfile → V2 worker=accounts.Worker |
| `WorkerProfile` (15) | `accounts.Worker` (15) | `worker` | V1 WorkerProfile ↔ V2 accounts.Worker (both OneToOne User) |
| `Color` (757) | (mapped via OrderItemColor / BOM) | `color` | Not a standalone V2 model — tracked in OrderItemColor |
| `ProductionLog` (1679) | `reporting.BusinessEvent` | `production_log` | Log entries → V2 BusinessEvent (category='production') |
| `ProductionEvent` (N/A — table missing) | `reporting.BusinessEvent` | `production_event` | Requires V1 migration 0015 first |
