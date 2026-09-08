# Phase 49: Code Ownership and Domain Map

Status: **Assessment Only — No Changes Made**

## Domain Ownership

| App | Owner | Source of Truth | Allowed Dependencies |
|-----|-------|-----------------|---------------------|
| `product` (legacy) | Production team | All V1 models | `inventory`, `auth`, `django.contrib` |
| `inventory` (legacy) | Warehouse team | `StockMovement` | `product` (ProductionTask FK) |
| `inventory` (V2) | Warehouse team | `StockLedger` | `bom`, `planning` |
| `production` (V2) | Production team | `ProductionOperation` | `planning`, `sales`, `bom` |
| `warehouse` (V2) | Warehouse team | `MaterialIssue` | `inventory` (V2) |
| `painting` (V2) | Painting team | `PaintingSchedule` | `accounts`, `production` |
| `reporting` | All teams | `BusinessEvent`, `AuditLog` | All apps (read-only) |
| `bom` (V2) | Production team | `BOM` | `products`, `planning` |
| `planning` (V2) | Production team | `Routing` | `products` |
| `sales` (V2) | Sales team | `CustomerOrder` | `customers`, `products` |
| `products` (V2) | Production team | `Product` | `customers` |

## Forbidden Dependencies

- `product` (legacy) → any V2 app
- `inventory` (legacy) → any V2 app
- V2 app → `product` (legacy) except via MigrationMap
- `painting` (V2) → `product.utils.PaintingScheduler`

## Public Service API

| App | Service | Public Methods |
|-----|---------|---------------|
| `product` | `LegacyProductionService` | `complete_task` |
| `inventory` | `InventoryService` | `receive_stock`, `reserve_stock`, `transfer_stock`, `adjust_stock` |
| `warehouse` | `WarehouseService` | `issue_material`, `consume_material` |
| `production` | `ProductionService` | `create_operations_for_order_item`, `complete_operation` |
| `bom` | `VersionedBOMService` | `build_bom_snapshot`, `build_routing_snapshot` |
| `reporting` | `BarcodeResolver` | `resolve`, `is_legacy_payload`, `get_scan_url` |

## Deprecated Modules

- `product/utils.py:PaintingScheduler` — V1 truth; do not modify
- `product/models.py:ProductionTask.save()` — being replaced by service

## No Changes Made