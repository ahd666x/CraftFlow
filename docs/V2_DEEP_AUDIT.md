# Phase 1: Deep Repository Audit

Date: 2026-09-08
Scope: Read-only audit. No code changes.
Checks: `python manage.py check` (0 issues), `python manage.py test --verbosity 1` (59 tests, OK)

---

## 1. Data Volume

### V1 (Production Truth)
| Table | Records |
|-------|---------|
| product_productiontask | 12,572 |
| product_productionevent | 6,025 |
| product_part | 1,972 |
| product_color | 744 |
| product_productbom | 786 |
| product_orderitem | 386 |
| product_order | 181 |
| product_packagingunit | 503 |
| product_productionlog | 1,601 |
| product_shipmentlog | 242 |
| product_workerprofile | 15 |
| inventory_stockmovement | 2 |

### V2 (Schema-Only)
- Total V2 records: 16 (test artifacts only)
- MigrationMap: 0
- MigrationRun: 0
- All domain tables (warehouse, quality, packaging, shipping, inventory ledger): 0

---

## 2. Business Logic Placement

### In Model.save() (Wrong Layer)
- ProductionTask.save(): event logging, material consumption, next-step activation, order status update
- OrderItem.save(): auto-calculates unit_price
- Order.generate_tasks(): BOM parsing, material override, size adjustment, barcode generation

### In Views (Wrong Layer)
- scan_qr: creates ProductionLog + calls complete_task
- purchase_order_receive: creates StockMovement directly
- mark_task_done: calls LegacyProductionService.complete_task
- admin_tasks_management: bulk status/worker/delete operations

### In Utils (Correct for V1)
- consume_material_for_task: idempotent StockMovement creation
- log_production_event: centralized ProductionEvent creation
- PaintingScheduler: 500+ lines, cascade insertion, sticky worker

---

## 3. V2 Orphan Status

All V2 services have ZERO production callers:
- InventoryService, ProductionService, WarehouseService, VersionedBOMService, PaintingService, OrderService
- All V2 selectors: zero callers
- All V2 urls.py: empty urlpatterns = []
- No V2 app has views.py or templates
- V2 URL namespace at /v2/ resolves to nothing

---

## 4. V2 Model Completeness Gaps

- ProductionOperation missing: part, scanned_by, completed_at, painting_stage, assigned_worker, order_item, color_part
- CustomerOrder missing V1 created_at (PersianDate), user FK split
- Item renamed min_stock_alert to min_stock, unit to uom FK

---

## 5. Risks

### Critical
- ProductionTask.save() is a god object (66 lines of side effects)
- No feature flags to toggle V1/V2 behavior
- scan_qr has no authorization for mutations

### High
- SQLite FKs not enforced
- SECRET_KEY hardcoded
- PaintingScheduler is monolithic (500+ lines)
- V2 has zero production traffic

### Medium
- No V2 templates or views
- No inventory signals
- V2 models not registered in admin

### Low
- No README
- No V2 app tests outside product/

---

## 6. Dependency Graph

- V1 production code: zero imports from V2 apps
- V2 code imports V1: bom/services.py (ProductBOM), reporting/barcode_resolver.py (OrderItem, PackagingUnit)
- V1 inventory imports V1 product: StockMovement.reference_task -> ProductionTask
- Cross-app V2 imports exist but all are schema-only

---

## 7. Signals

- product/signals.py: generate_qr_code (OrderItem post_save), generate_packaging_qr_codes (OrderItem post_save)
- inventory/signals.py: DOES NOT EXIST
- product/utils.py connects PaintingProcess/WorkerProfile post_save to cache invalidation

---

## 8. Management Commands (8, all in product/)

- import_products: mutates V1 Product/Part/BOM
- extract_paint_schedule: read-only
- export_schedule: read-only
- diagnose_unscheduled_paint: read-only
- clean_ghost_paint_tasks: mutates V1 ProductionTask
- backfill_production_events: mutates V1 ProductionEvent/StockMovement
- backfill_order_item_on_tasks: mutates V1 ProductionTask
- analyze_paint_scheduling: read-only
