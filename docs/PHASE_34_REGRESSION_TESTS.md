# Phase 34: Critical Workflow Regression Suite

Status: **Not Implemented**

## Required Workflows

| # | Workflow | Current Coverage |
|---|----------|-----------------|
| 1 | Create Order + OrderItem | `tests_legacy_service.py` setUp |
| 2 | Generate V1 tasks | `Order.generate_tasks()` tested |
| 3 | Complete ProductionTask | `LegacyProductionService.complete_task` tested |
| 4 | Idempotent material consumption | `test_no_duplicate_consumption_on_repeated_calls` |
| 5 | QR scan OrderItem | `BarcodeResolver` tests |
| 6 | QR scan PackagingUnit | `BarcodeResolver` tests |
| 7 | Packaging | Not tested |
| 8 | Shipping | Not tested |
| 9 | Warehouse receipt | `InventoryService.receive_stock` tested |
| 10 | V2 reservation/issue | `tests_v2_domain_contracts.py` |
| 11 | Timeline report | Not tested |
| 12 | Transaction rollback | `test_rollback_on_consumption_error` |

## Gaps

- Packaging workflow: no tests
- Shipping workflow: no tests
- Timeline reporting: no tests
- Persian date assertions: partial coverage
- PaintingScheduler: characterization tests only, no rewrite

## No Changes Made