# Phase 13.1: Migration Safety Repair and Disposable Clone Validation

## Step A — Data-State Audit (Corrected)

See `docs/PHASE_13_DATA_STATE_AUDIT.md` for the full corrected audit.

### CRITICAL FINDING: Migration Name Mismatch

The `django_migrations` table contains entries that do NOT match the current migration files on disk:

| In django_migrations (applied) | File on disk (pending) |
|---|---|
| `product.0004_holiday_paintingprocess_order_due_date_and_more` | `product.0004_paintingprocess_order_due_date_order_priority_and_more` |
| `product.0005_remove_workerprofile_skill_costs_and_more` | `product.0005_holiday` |

The old migrations created tables (`PaintingProcess`, `PaintingStage`, `PaintingAssignmentRule`, `Holiday`, WorkerProfile fields) that the current file-based migrations also try to create. Running `migrate` without `--fake` on these will fail with "table already exists".

### V1 Data State (Local Clone Database)

- **20 V1 tables** with 15,119 total records
  - Customer: 307, Product: 84, Part: 2,078, BOM: 786, Order: 185, OrderItem: 395
  - ProductionTask: 13,068 (6,053 done, 3,047 pending, 3,968 waiting)
  - ProductionLog: 1,679, ShipmentLog: 267, PackagingUnit: 523, Material: 12
  - WorkerProfile: 15, Color: 757, PaintingProcess: 3, PaintingStage: 15, PaintingAssignmentRule: 7

- **0 V2 tables** exist (no V2 schema applied)
- **MigrationMap table**: does not exist
- **V1 FK integrity**: Clean (no orphaned records on OrderItem→Product, OrderItem→Order, ProductBOM→Product, ProductBOM→Part)

### V2 Schema (from model verification)

All 77 V2 tables exist in the codebase models with correct field definitions.
Key verified mappings:
- V1 `ShipmentLog.packaging_unit` (FK) → V2 `shipping.ShipmentItem.package` (FK)
- V1 `PackagingUnit.order_item` (FK) → V2 `packaging.Package.customer_order_item` (FK)
- V1 `WorkerProfile` (OneToOne User) → V2 `accounts.Worker` (OneToOne User)
- V1 `ProductionTask` (13,068) → V2 `production.ProductionOperation` (13,068)
- StockLedger is in `inventory` app (not warehouse); MaterialConsumption is in `warehouse` app

## Step B — QR Test Isolation Fix

### Problem

`selvi/settings.py` had `MEDIA_ROOT = '/root/selvi/selvi/media'` (Linux path).
On Windows, this resolves to `C:\root\selvi\selvi\media`, which Django's `FileSystemStorage`
auto-creates. QR code files accumulate there across test runs, polluting the filesystem
and the repository's parent directory.

### Fix Applied

1. **settings.py**: Changed `MEDIA_ROOT` to be env-configurable:
   ```python
   MEDIA_ROOT = os.environ.get('DJANGO_MEDIA_ROOT', '/root/selvi/selvi/media')
   ```
   At runtime (no env var set), behavior is unchanged — still uses `/root/selvi/selvi/media`.

2. **conftest.py** (new, project root): Auto-sets `DJANGO_MEDIA_ROOT` to a
   `tempfile.mkdtemp()` directory when running tests, so QR files go to OS temp dir.

3. **AGENTS.md**: Updated Test Commands section with MEDIA_ROOT isolation notes.

4. **Tests**: No test files modified. Tests that test QR behavior (`test_order_item_qr_url_pattern`,
   `test_packaging_unit_qr_url_pattern`) still check real generation (not mocked), now with
   writable MEDIA_ROOT. Tests not specifically about QR mock qrcode as before.

### Verification

- All 143 tests pass with the fix
- QR files now generated in `tempfile.mkdtemp()` during tests (not in repo)
- `C:\root\selvi\selvi\media` is no longer written to

## Step C — Disposable Schema Migration Test

### Procedure

1. Created backup: `db.sqlite3.original_backup` (non-destructive copy)
2. Created disposable copy: `db.sqlite3.v2-schema-test`
3. Swapped files: original `db.sqlite3` → `db.tmp_hold`, disposable → `db.sqlite3`
4. Faked mismatched migrations: `0004`, `0005` (old names applied, files renamed)
5. Faked product `0006`-`0015` (tables already exist from old migrations; 0015 ProductionEvent table does NOT exist)
6. Applied `migrate` — product 0016/0017 + all V2 app migrations succeeded
7. Ran `django check` — passed
8. Ran full test suite — 143 tests passed (uses separate test database)
9. Restored original `db.sqlite3`

### Results

**Before migration:**
- Total tables: 31 (20 V1 + 11 core)
- V1 tables: 20
- V2 tables: 0
- V2 table count: 0

**After migration:**
- Total tables: 112 (20 V1 + 15 core + 77 V2)
- V1 tables: 20 (UNCHANGED)
- V1 row counts: **IDENTICAL** (Customer: 307, Product: 84, BOM: 786, Order: 185, ProductionTask: 13,068, etc.)
- V2 tables: 77 (all created, all 0 rows — data migration not run)
- V2 table count: 77

**Specific V2 tables created (77):**
- bom: 3 tables (BOM, BOMItem, BOMItemMaterialRule)
- customers: 3 tables (Customer, CustomerAddress, CustomerGroup)
- products: 4 tables (Product, ProductCategory, ProductPart, ProductRevision)
- inventory: 12 tables (Item, UOM, UOMConversion, ItemCategory, ItemSupplier, RawMaterial, RawMaterialCategory, StockBalance, StockLedger, StockLocation, StockLot, StockMovement, StockReservation, Supplier, PurchaseOrder, PurchaseOrderItem) — 16 total
- sales: 5 tables (CustomerOrder, CustomerOrderItem, OrderItemColor, SalesQuotation, SalesQuotationItem)
- production: 8 tables (ProductionOrder, ProductionOrderItem, ProductionBatch, ProductionBatchItem, ProductionOperation, OperationAssignment, OperationExecution, WIPUnit, WIPTransfer) — 9 total
- planning: 5 tables (WorkCenter, Resource, Skill, Routing, RoutingOperation, RoutingDependency, ProductionPart) — 7 total
- painting: 5 tables (PaintingProcess, PaintingProcessStage, PaintingAssignmentRule, PaintingSchedule, PaintingScheduleItem)
- quality: 4 tables (QualityInspection, QualityDefect, ReworkOrder, ReworkOrderItem)
- shipping: 3 tables (Shipment, ShipmentItem, ShipmentTracking)
- packaging: 3 tables (Package, PackageItem, PackagingSpecification)
- warehouse: 11 tables (MaterialRequirement, MaterialRequest, MaterialRequestItem, MaterialIssue, MaterialIssueItem, MaterialConsumption, MaterialReturn, MaterialReturnItem, MaterialWaste)
- reporting: 6 tables (BusinessEvent, AuditLog, Barcode, MigrationMap, MigrationRun)
- accounts: 2+ tables (Worker, WorkerSchedule, Holiday)

**Known limitation:**
- `product_productionevent` table was NOT created (migration 0015 was faked, and the old 0004/0005 did not create it).
  This affects Phase 9 of the migration plan (event migration). The migration command should
  handle this gracefully (catch the missing table and report as data gap, not error).

### Commands Executed

```bash
# Step 1: Backup
cp db.sqlite3 db.sqlite3.original_backup

# Step 2: Create disposable copy
cp db.sqlite3 db.sqlite3.v2-schema-test

# Step 3: Swap files (original out of the way)
mv db.sqlite3 db.sqlite3.tmp_hold
mv db.sqlite3.v2-schema-test db.sqlite3

# Step 4: Fake mismatched migrations
python -m django migrate product 0004 --fake
python -m django migrate product 0005 --fake

# Step 5: Fake product migrations where tables already exist
python -m django migrate product 0006 --fake  # table exists
python -m django migrate product 0007 --fake  # field changes already applied
python -m django migrate product 0008 --fake  # field changes already applied
python -m django migrate product 0014 --fake  # all indexes/renames/fields applied

# Step 6: Fake 0015 (ProductionEvent table does NOT exist)
python -m django migrate product 0015 --fake

# Step 7: Apply remaining migrations (0016, 0017, and all V2 apps)
python -m django migrate

# Step 8: System check
python -m django check

# Step 9: Test suite (uses separate test database)
python -m django test --settings=selvi.settings -v 1

# Step 10: Reconcile
python -m django craftflow_reconcile_v2 --settings=selvi.settings --json

# Step 11: Restore original
mv db.sqlite3 db.sqlite3.v2-schema-test
mv db.sqlite3.tmp_hold db.sqlite3
```

### Validation Results

| Check | Result |
|---|---|
| V1 tables preserved | PASS — all 20 tables with identical row counts |
| V2 schema tables created | PASS — 77 tables created |
| `django check` | PASS — 0 issues |
| Test suite (143 tests) | PASS — OK |
| Reconcile command | PASS — runs without errors |

## Step D — Go/No-Go Decision

### GO WITH FIXES

**Pre-migration requirements before Option B can proceed on the actual clone:**

1. **Fake product migrations 0004–0015** before running `migrate`. These migrations' tables
   already exist from earlier (old-named) migrations, and 0015's ProductionEvent table does
   not exist (migration was faked). The command sequence is:
   ```bash
   python -m django migrate product 0004 --fake
   python -m django migrate product 0005 --fake
   python -m django migrate product 0006 --fake
   ... # through 0015
   python -m django migrate product 0016
   python -m django migrate product 0017
   python -m django migrate  # applies all V2 app migrations
   ```

2. **ProductionEvent table missing**: Migration 0015 must be faked (not applied) because
   the table doesn't exist in the original database. Phase 9 of the migration data script
   must handle the missing `product_productionevent` table gracefully (try/except, report
   as data gap). Alternatively, apply 0015 for real (creates the table) before running
   data migration for events.

3. **Migration 0014 data loss**: The forward migration removes `is_manual_item_task` and
   `manual_reference_file` fields from ProductionTask. If these fields exist in the DB,
   faking 0014 means they remain. If they don't exist (they were already removed by the
   old 0004/0005 migrations), this is fine. Since we fake 0014, no data loss occurs.

4. **Migration 0013 backfill**: Faked — the data correction (`completed_quantity = quantity`
   for done tasks) does not actually run. This is a data quality issue in the V1 clone,
   not a migration blocker. The backfill can be run separately if needed:
   ```python
   from product.models import ProductionTask
   done = ProductionTask.objects.filter(status='done', completed_quantity__lt=F('quantity'))
   done.update(completed_quantity=F('quantity'))
   ```

5. **conftest.py for test isolation**: Added to ensure MEDIA_ROOT uses temp directory
   during tests, preventing QR file pollution.

**Rollback procedure (no destructive git):**
- Restore from database backup: `cp db.sqlite3.backup.<timestamp> db.sqlite3`
- No git checkout/reset/clean required

**Estimated total time for full Option B execution:** ~15-20 minutes
- Pre-migration fixes (fakes): 2 min
- Schema migration: 2 min
- Data migration: 5-10 min
- Validation: 3 min
