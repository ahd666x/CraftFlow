# Phase 6: Inventory and Warehouse V2

## Objective
مدل و workflow کامل انبار V2 را پیاده‌سازی و تست کن.

## Workflow
MaterialRequirement → StockReservation → MaterialRequest → MaterialIssue → Production Location → MaterialConsumption → MaterialReturn / MaterialWaste

## Models
- `inventory.StockLedger` / `inventory.StockBalance` / `inventory.StockReservation` / `inventory.StockLot` / `inventory.StockLocation` / `inventory.Item`
- `warehouse.MaterialRequirement` / `warehouse.MaterialRequest` / `warehouse.MaterialRequestItem` / `warehouse.MaterialIssue` / `warehouse.MaterialIssueItem` / `warehouse.MaterialConsumption` / `warehouse.MaterialReturn` / `warehouse.MaterialReturnItem` / `warehouse.MaterialWaste`

## Requirements Implemented
1. **StockMovement V1 → StockLedger V2 migration**: اضافه شدن فاز `inventory` به `craftflow_migrate_v2`
2. **Opening/closing balance reconciliation**: `InventoryService` تمام mutationها موجودی را به‌روز می‌کند
3. **Reserve only available**: `InventoryService.reserve_stock` فقط `quantity_available` را کم می‌کند
4. **Issue, consumption, return, waste independent**: هر کدام در `WarehouseService` به صورت مستقل هستند
5. **transaction.atomic**: تمام mutationها در `transaction.atomic` هستند
6. **select_for_update**: تمام mutationها قبل از خواندن balance از `select_for_update()` استفاده می‌کنند
7. **Ledger and balance never inconsistent**: هر mutation همزمان balance و ledger را به‌روز می‌کند
8. **Item, lot, location validation**: در هر mutation اعتبارسنجی می‌شود
9. **Dry-run/execute commands**: `craftflow_migrate_v2 --phase inventory --dry-run|--execute`

## Tests Added
- `InventoryReceiptTests`: receipt, positive quantity, lot creation, balance update
- `InventoryReservationTests`: reserve decreases available, insufficient stock, positive quantity, release restores
- `InventoryTransferTests`: two ledger entries, same location raises, insufficient balance raises
- `InventoryAdjustmentTests`: increase, decrease, zero raises, negative balance raises
- `InventoryNegativeStockTests`: issue, waste, consume more than available raises
- `InventoryConcurrencyTests`: concurrent updates with select_for_update
- `InventoryReconciliationTests`: balance matches ledger sum
- `WarehouseIssueTests`: decreases source, increases target, lot update, duplicate idempotency
- `WarehouseConsumptionTests`: decreases balance, creates ledger, more than available raises, duplicate idempotency
- `WarehouseReturnTests`: increases target balance
- `WarehouseWasteTests`: decreases balance, creates ledger, more than available raises
- `WarehousePartialIssueTests`: partial issue updates balance correctly
- `MaterialRequirementTests`: create requirement

## Migration
- `craftflow_migrate_v2 --phase inventory --dry-run|--execute`
- `StockMovement` → `StockLedger` با idempotency
- `MigrationMap` برای هر movement ایجاد می‌شود

## Status
تکمیل شده.
