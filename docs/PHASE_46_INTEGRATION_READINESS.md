# Phase 46: External Integration Readiness

Status: **Design Only — No Integrations Configured**

## QR / Barcode

| Aspect | Status |
|--------|--------|
| Owner | product app (signals) |
| Direction | Read-only scan → mutation |
| Identifier | OrderItem.id, PackagingUnit.id |
| Retry | Scanner retries on failure |
| Idempotency | BarcodeResolver is read-only |
| Error handling | 404 for unknown QR |
| Audit | ProductionEvent logged |
| Security | No auth on scan endpoints |
| Fallback | Manual entry by operator |

## Inventory Movement

| Aspect | Status |
|--------|--------|
| Owner | inventory app |
| Direction | V1 StockMovement is source of truth |
| Identifier | StockMovement.id |
| Retry | Not implemented |
| Idempotency | `reference_task` provides natural key |
| Error handling | Exception → rollback |
| Audit | StockMovement is immutable |
| Security | Via views |
| Fallback | Manual stock entry |

## Shipment Status

| Aspect | Status |
|--------|--------|
| Owner | product app |
| Direction | PackagingUnit → ShipmentLog |
| Identifier | PackagingUnit.id |
| Retry | Not implemented |
| Idempotency | `unique_together` on PackagingUnit |
| Error handling | Exception → rollback |
| Audit | ShipmentLog is record |
| Security | Via views |
| Fallback | Manual shipment entry |

## Customer / Order Identifiers

| Aspect | Status |
|--------|--------|
| Owner | product app |
| Identifier | Order.id, OrderItem.id |
| Stability | Auto-increment; stable |
| Mapping | MigrationMap for V2 |

## No Changes Made