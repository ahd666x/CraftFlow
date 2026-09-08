# Final Architecture Verification

Date: 2026-09-08
Status: **Read-Only Assessment — No Code Changes**

## Domain Status

| Domain | V1 Status | V2 Status | Evidence |
|--------|-----------|-----------|----------|
| Orders/Sales | **V1 Active** | V2 orphan | `Order` has 78+ view refs; `CustomerOrder` has zero callers |
| Products | **V1 Active** | V2 orphan | `Product` used in views; `products.Product` unused |
| BOM | **V1 Active** | V2 Pilot | `ProductBOM` read by `VersionedBOMService`; `bom.BOM` has create methods |
| Routing | **V1 Active** | V2 Pilot | V1 has no Routing model; `planning.Routing` has create methods |
| Production | **V1 Active** | V2 orphan | `ProductionTask` is core execution; `ProductionOperation` unused |
| Inventory | **V1 Active** | V2 orphan | `StockMovement` is source of truth; `StockLedger` unused |
| Warehouse | — | V2 orphan | All models unused; services have no callers |
| Painting | **V1 Active** | V2 duplicate | `PaintingScheduler` in utils.py is truth; V2 models duplicate |
| Packaging | **V1 Active** | V2 orphan | `PackagingUnit` has QR; `Package` unused |
| Shipping | **V1 Active** | V2 orphan | `ShipmentLog` active; `Shipment` unused |
| Quality | — | V2 orphan | All models unused |
| Events/Audit | **V1 Active** | V2 orphan | `ProductionEvent` active; `BusinessEvent` unused |
| Barcode | **V1 Active** | V2 Pilot | `BarcodeResolver` handles legacy QR; `Barcode` model unused |
| Planning | — | V2 Pilot | `Routing` has create methods but no callers |

## Known Risks

1. **V2 has zero production traffic** — all V2 models are schema-only
2. **No domain has completed Pilot** — Phases 9-22 not executed
3. **No data migration performed** — MigrationMap table empty
4. **SQLite FKs not enforced** — data integrity risk on PostgreSQL migration
5. **PaintingScheduler is monolithic** — 1800+ lines in utils.py
6. **No CI pipeline** — code quality depends on manual review

## Next 90 Days Backlog

1. Execute Phases 9-12 (Stock Ledger, Warehouse, Events pilots)
2. Execute Phases 18-20 (BOM, Quality, Packaging pilots)
3. Build CI pipeline (Phase 33)
4. Create regression test suite (Phase 34)
5. Data governance scan (Phase 35)