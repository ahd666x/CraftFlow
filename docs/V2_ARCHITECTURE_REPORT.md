# CraftFlow V2 Architecture Report

## Executive Summary

CraftFlow (internal: `selvi`) is a manufacturing/production management system for a furniture factory. The current architecture is monolithic with two Django apps (`product` and `inventory`) containing significant business logic inside models and a 5352-line views.py file. This report documents the current state and the planned V2 refactoring.

---

## 1. Current Architecture

### Apps
| App | Purpose | Models | Key Issues |
|-----|---------|--------|------------|
| `product` | Core manufacturing, orders, painting, reports | 15 models | Monolithic views.py (5352 lines), business logic in model.save(), signals with side effects |
| `inventory` | Raw materials, suppliers, stock movements | 6 models | Depends on product decorators, cross-app coupling |

### Cross-App Dependencies
1. `product.Material.raw_material` → `inventory.RawMaterial`
2. `inventory.StockMovement.reference_task` → `product.ProductionTask`
3. `inventory/views.py` imports decorators from `product.decorators`
4. `inventory/migrations/0001_initial.py` depends on `product.0014`

### Database
- SQLite3 (`db.sqlite3`)
- No connection pooling
- No transaction management at app level

### Frontend
- Server-rendered Django templates
- jQuery + Bootstrap
- No API layer (despite DRF being installed)
- No app namespace in `product/urls.py`

---

## 2. Model Inventory

### V1 Models (Current)

| Model | App | Purpose | Business Logic |
|-------|-----|---------|---------------|
| Customer | product | Customer info | None |
| ProductCategory | product | Product categorization | None |
| Material | product | Sheet material definition | None |
| Order | product | Customer order | `generate_tasks()` |
| Product | product | Product definition | None |
| OrderItem | product | Order line item | `save()` calculates price, `sync_packaging_units()` |
| Color | product | Color assignment per part | None |
| Part | product | Physical part definition | None |
| ProductBOM | product | BOM for product | None |
| ProductionTask | product | Production task | **Heavy logic in `save()`**: auto-status, event logging, material consumption, next-step activation, order status update |
| WorkerProfile | product | Worker skills/availability | None |
| ProductionLog | product | Production log entry | None |
| ProductionEvent | product | Event timeline | None |
| PackagingUnit | product | Packaging/shipping unit | None |
| ShipmentLog | product | Shipment record | None |
| PaintingProcess | product | Painting process definition | None |
| PaintingStage | product | Painting stage | None |
| PaintingAssignmentRule | product | Worker assignment rules | None |
| Holiday | product | Holiday calendar | None |
| Supplier | inventory | Supplier | None |
| RawMaterialCategory | inventory | Raw material category | None |
| RawMaterial | inventory | Raw material master | `current_stock` property, `stock_status` property |
| StockMovement | inventory | Stock transaction | None |
| PurchaseOrder | inventory | Purchase order | None |
| PurchaseOrderItem | inventory | PO line item | `line_total` property |

### Signals
- `generate_qr_code` - post_save on OrderItem
- `create_packaging_qr_codes` - post_save on OrderItem

---

## 3. Business Logic Audit

### Critical Issues

1. **ProductionTask.save()** - Violates Single Responsibility:
   - Auto-sets status to `done` when `completed_quantity >= quantity`
   - Sets `completed_at`
   - Calls `log_production_event()`
   - Calls `consume_material_for_task()`
   - Activates next step (`pending`)
   - Calls `update_order_status()`

2. **OrderItem.save()** - Violates SRP:
   - Calculates `unit_price`
   - Should be in service

3. **Order.generate_tasks()** - Complex orchestration:
   - Creates dynamic Part variations
   - Creates ProductionTask objects
   - Updates order status
   - Should be in service

4. **utils.py** (1859 lines) - God object:
   - Date helpers
   - Material lookup
   - Size adjustment
   - Barcode update
   - Painting scheduler (1000+ lines)
   - Cascade scheduling
   - Worker assignment
   - Export/import
   - Event logging
   - Material consumption

5. **Signals** - Hidden side effects:
   - QR code generation
   - Packaging unit creation

---

## 4. V2 Target Architecture

### Apps Structure

```
core/           - Abstract models, base enums, common utilities
accounts/       - User, Worker (extends User), permissions
customers/      - Customer, CustomerGroup
sales/          - CustomerOrder, CustomerOrderItem, OrderItemColor
products/       - Product, ProductCategory, ProductPart
bom/            - BOM, BOMItem, BOMItemMaterialRule
inventory/      - UOM, UOMConversion, Item, StockLocation, StockLot, StockBalance, StockLedger, StockReservation
warehouse/      - MaterialRequirement, MaterialRequest, MaterialRequestItem, MaterialIssue, MaterialIssueItem, MaterialConsumption, MaterialReturn, MaterialReturnItem, MaterialWaste
production/     - ProductionOrder, ProductionOrderItem, ProductionBatch, ProductionBatchItem, ProductionOperation, OperationAssignment, OperationExecution, WIPUnit, WIPTransfer
planning/       - Routing, RoutingOperation, RoutingDependency, ProductionPart
painting/       - PaintingProcess, PaintingProcessStage, PaintingAssignmentRule
quality/        - QualityInspection, QualityDefect, ReworkOrder
packaging/      - Package, PackageItem
shipping/       - Shipment, ShipmentItem
reporting/      - BusinessEvent, AuditLog, Barcode, MigrationMap, MigrationRun
```

### Key Design Decisions

1. **Item** is the master inventory item (replaces Material + RawMaterial unification)
2. **StockLedger** is source of truth; StockBalance is read-optimized
3. **ProductionOperation** replaces ProductionTask as central production unit
4. **BusinessEvent** replaces ProductionLog + ProductionEvent as unified timeline
5. **AuditLog** for data changes (separate from business events)
6. **MigrationMap** tracks V1→V2 ID mapping for data migration
7. **Services** contain all business logic
8. **Selectors** handle complex queries
9. **Views** only handle HTTP concerns
10. **Models** are thin data containers

---

## 5. Migration Strategy

### Phase Overview

| Phase | Focus | Commit |
|-------|-------|--------|
| 01 | Audit report | v2/phase-01-audit |
| 02 | Schema - create V2 apps and models | v2/phase-02-schema |
| 03 | Master data models | v2/phase-03-master-data |
| 04 | BOM & Routing | v2/phase-04-bom-routing |
| 05 | Sales & Production models | v2/phase-05-production |
| 06 | Inventory models | v2/phase-06-inventory |
| 07 | Warehouse models | v2/phase-07-warehouse |
| 08 | Services layer | v2/phase-08-services |
| 09 | Migration data & mapping | v2/phase-09-migration |
| 10 | UI update | v2/phase-10-ui |

### Data Migration Principles
- Idempotent migrations
- MigrationMap for ID tracking
- No data loss
- Legacy data flagged as `is_legacy=True`
- Validation at each step

---

## 6. Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Data loss during migration | MigrationMap, idempotent scripts, backups |
| Business logic breakage | Services layer preserves all logic, tests |
| Performance regression | StockBalance for reads, proper indexes |
| Concurrent access (SQLite) | Documented limitation, PostgreSQL recommended for production |
| Incomplete migration | Phase-by-phase validation |
| Breaking changes to UI | Parallel V1/V2 during transition |

---

## 7. Testing Strategy

### Per Phase
1. `python manage.py check`
2. Migration validation
3. Unit tests for new models
4. Integration tests for services
5. Record count verification
6. FK integrity check
7. Duplicate detection

### Coverage Goals
- All services: 90%+
- All selectors: 90%+
- Models: basic CRUD
- Critical workflows: end-to-end

---

## 8. Dependencies Between Phases

```
Phase 01 (Audit) → Phase 02 (Schema) → Phase 03 (Master Data)
                                              ↓
Phase 04 (BOM/Routing) ← Phase 05 (Production) ← Phase 02
                                              ↓
Phase 06 (Inventory) ← Phase 07 (Warehouse) ← Phase 05
                                              ↓
Phase 08 (Services) ← Phase 09 (Migration) ← All above
                                              ↓
Phase 10 (UI) ← Phase 09
```

---

## 9. Open Questions / Decisions Needed

1. Should we keep V1 apps running in parallel during migration?
2. PostgreSQL setup for production - need to provision
3. Which V1 data is critical to preserve exactly?
4. Barcode format - should it change in V2?
5. QR code generation - keep in signal or move to service?
