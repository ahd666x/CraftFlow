# Phase 4: Master Data and Product Engineering Migration

Date: 2026-09-09
Prerequisites: V2 schema deployed (Phase 3), MigrationMap/MigrationRun framework live, backup confirmed
Status: Implemented and validated

## Command

python manage.py craftflow_migrate_v2 --phase master-data --dry-run
python manage.py craftflow_migrate_v2 --phase master-data --execute [--name "X"]
python manage.py craftflow_migrate_v2 --rollback <run_id>

Source: `reporting/management/commands/craftflow_migrate_v2.py`

## Scope

Clones (idempotent) V1 master data into V2 models. Zero V1 mutation.

| V1 model | Decision | V2 target | Records |
|----------|----------|-----------|---------|
| product.ProductCategory | KEEP | products.ProductCategory | 6 |
| product.Product | KEEP | products.Product | 83 |
| product.Customer | KEEP | customers.Customer | 300 |
| product.Material | MERGE | inventory.Item | 12 |
| inventory.RawMaterial | MERGE | inventory.Item | 1 |
| product.Part (base) | KEEP | products.ProductPart | 786 |
| product.Part (variation) | KEEP | planning.ProductionPart | 1163 |
| product.ProductBOM | REPLACE | bom.BOM / BOMItem / BOMItemMaterialRule | 77 / 786 / 786 |
| product.PaintingProcess | REPLACE | painting.PaintingProcess | 3 |
| product.PaintingStage | REPLACE | painting.PaintingProcessStage | 15 |
| product.WorkerProfile | REPLACE | accounts.Worker | 15 |

## Design rules

### Idempotency anchor
Anchored on `MigrationMap(migration_type, old_id, old_app)`, NOT on V2 natural keys.
V1 Part has no reliable unique key (66 duplicate groups even on product+name+size),
so `get_or_create` on natural keys would create duplicates on re-run.

### Zero V1 mutation
V1 rows are read-only. The command never writes to V1 tables.

### Ambiguous data
Records that cannot be mapped are skipped and recorded as `MigrationMap.is_legacy=True`
with a `legacy_reason`. They are never guessed. Skipped records in this phase:

| type | reason | count |
|------|--------|-------|
| part | not referenced by any BOM; product unknown | 10 |
| production_part | base ProductPart not migrated | 13 |

### color_material_map
Preserved as-is and documented. Relational conversion (color -> material rule) is
NOT performed because every `color_material_map` in the V1 dataset is empty (639 str,
147 dict, all `{}`). The BOM mapper refuses to proceed when a non-empty map is found
(warning + skip), so no silent loss can occur.

### Material / RawMaterial merge
Merge rule: identical name (case-insensitive, trimmed). This is the only provable key
because `product.Material.raw_material` FK is NULL for all 12 materials.
- Material without RawMaterial -> standalone Item (warning recorded)
- RawMaterial without Material -> standalone Item (warning recorded)
- Multiple RawMaterials sharing a name -> skip + warning

Result: 13 Items created, 0 merged (the single RawMaterial "سفید" has no matching
Material name), 2 UOMs created (lit, pcs), 1 ItemCategory created.

### PersianDateField
V1 stores Gregorian in DB; V2 DateField reads the same value. Direct copy, no conversion.

### Status / enum mapping
- WorkerProfile.stage -> Worker.station (direct, all V1 values exist in V2 choices)
- PaintingStage.required_skill -> PaintingProcessStage.required_skill (general/painter)

## Validation

### 1. Dry run (zero mutation)
Snapshot before/after is identical: MigrationMap=4765, MigrationRun=1, Product=83,
ProductPart=786, BOM=77, BOMItem=786. No writes.

### 2. Execute
`MigrationRun 10 completed: processed=3170 skipped=23 failed=0`

### 3. Execute again (idempotency)
`MigrationRun 11 completed: processed=3170 skipped=23 failed=0`
All domains report `created=0` — no duplicates.

### 4. Ambiguous data
10 parts and 13 production parts skipped with `is_legacy=True` and explicit reasons.

### 5. Rollback
`Rollback complete for MigrationRun 8: 9530 MigrationMap rows deleted, 3904 V2 rows deleted.`
Rollback deletes only V2 rows created by that run (in FK-safe order) plus its
MigrationMap and MigrationRun rows. V1 untouched. Verified: re-execute after rollback
reproduces the same counts.

### 6. Count reconciliation
V2 totals match V1 totals minus skipped:
- ProductCategory 6 = 6
- Product 83 = 83
- Customer 171 (300 - 129 reused from prior run)
- Worker 15 = 15
- Item 13 = 12 Material + 1 RawMaterial
- ProductPart 786 (796 - 10 skipped)
- ProductionPart 1163 (1176 - 13 skipped)
- BOM 77 (786 BOMItems reference 77 distinct products)
- BOMItem 786 = 786
- BOMItemMaterialRule 786 = 786
- PaintingProcess 3 = 3
- PaintingProcessStage 15 = 15

V1 counts unchanged after every operation.

## Risks
- Low: All V2 models have zero callers; migration does not affect runtime behavior.
- Medium: V1 Part has no natural key; idempotency depends on MigrationMap integrity.
- Medium: color_material_map is empty in this dataset; if non-empty maps appear in
  future data, the BOM mapper will skip them until an explicit rule is added.

## Rollback
`python manage.py craftflow_migrate_v2 --rollback <run_id>`
Deletes only that run's V2 rows, MigrationMap rows, and the MigrationRun itself.

## Commit
v2/phase-04-master-data-migration
