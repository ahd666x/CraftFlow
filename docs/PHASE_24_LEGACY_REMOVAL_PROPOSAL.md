# Phase 24: Legacy Model Removal Proposal

Date: 2026-09-08
Status: **Assessment Only — No Removals Performed**

## Executive Summary

This document evaluates every V1 model for potential removal eligibility.
**Conclusion: No V1 model is currently eligible for removal.**

All V1 models have active operational callers. V2 replacements exist as schema-only
(orphaned) with zero production traffic. Removing any V1 model would break the
application.

---

## Eligibility Criteria

A model is **Eligible for Removal** only if ALL of these hold:

1. No active code callers (views, services, utils, signals, admin, commands, tests)
2. Historical data archived and preserved
3. Reports still functional without it
4. QR/barcode compatibility preserved
5. Explicit user approval obtained
6. V2 replacement proven in production

A model is **Eligible for Deprecation Proposal** if:
- V2 replacement exists but is Pilot-only
- Callers can be migrated with bounded effort
- No data loss risk

---

## Model-by-Model Assessment

### V1 product App Models

| Model | Active Callers | V2 Replacement | Status |
|-------|---------------|----------------|--------|
| `Customer` | Yes (78+ refs in views) | `customers.Customer` (orphan) | **Blocked** |
| `ProductCategory` | Yes | `products.ProductCategory` (orphan) | **Blocked** |
| `Material` | Yes | — (no V2 equivalent) | **Blocked** |
| `Order` | Yes (central aggregate) | `sales.CustomerOrder` (orphan) | **Blocked** |
| `Product` | Yes (28 refs) | `products.Product` (orphan) | **Blocked** |
| `OrderItem` | Yes (100+ refs, QR critical) | `sales.CustomerOrderItem` (orphan) | **Blocked** |
| `Color` | Yes (25 refs) | — | **Blocked** |
| `Part` | Yes (18 refs, barcode f3 critical) | `products.ProductPart` (orphan) | **Blocked** |
| `ProductBOM` | Yes (read by V2 pilot) | `bom.BOM` (pilot only) | **Blocked** |
| `ProductionTask` | Yes (core execution) | `production.ProductionOperation` (orphan) | **Blocked** |
| `WorkerProfile` | Yes (28 refs, scheduling) | `accounts.Worker` (orphan) | **Blocked** |
| `ProductionLog` | Yes (10 refs) | — (no V2 equivalent) | **Blocked — Historical** |
| `ProductionEvent` | Yes (5 refs, audit) | `reporting.BusinessEvent` (orphan) | **Blocked — Historical** |
| `PackagingUnit` | Yes (25 refs, QR critical) | `packaging.Package` (orphan) | **Blocked** |
| `ShipmentLog` | Yes (7 refs) | `shipping.Shipment` (orphan) | **Blocked — Historical** |
| `PaintingProcess` | Yes (20 refs) | `painting.PaintingProcess` (duplicate) | **Blocked** |
| `PaintingStage` | Yes (18 refs) | `painting.PaintingProcessStage` (duplicate) | **Blocked** |
| `PaintingAssignmentRule` | Yes | `painting.PaintingAssignmentRule` (duplicate) | **Blocked** |
| `Holiday` | Yes (scheduling) | `accounts.Holiday` (duplicate) | **Blocked** |

### V1 inventory App Models

| Model | Active Callers | V2 Replacement | Status |
|-------|---------------|----------------|--------|
| `Supplier` | Yes | — | **Blocked** |
| `RawMaterialCategory` | Yes | `inventory.ItemCategory` (orphan) | **Blocked** |
| `RawMaterial` | Yes (consumption) | `inventory.Item` (orphan) | **Blocked** |
| `StockMovement` | Yes (source of truth) | `inventory.StockLedger` (orphan) | **Blocked** |
| `PurchaseOrder` | Yes | — | **Blocked** |
| `PurchaseOrderItem` | Yes | — | **Blocked** |

---

## Models That Could Be Considered First (Future)

When V2 domains reach **Controlled Cutover** status, these become candidates:

1. **`ProductionLog`** — Purely historical audit trail. If V2 `BusinessEvent` covers the same events, this could be read-only legacy.
2. **`ShipmentLog`** — Historical shipping records. V2 `shipping.Shipment` would need to be operational first.
3. **`ProductionEvent`** — Immutable event log. V2 `BusinessEvent` with correlation mapping could replace it.

**Prerequisite for all three:** Their V2 replacements must be in production use, not just schema.

---

## Recommendation

**No action this phase.** The honest assessment is that the V2 is not yet ready for any cutover.
Continuing to propose removals would be misleading.

The path to actual removal requires:
1. Complete each domain's Pilot (Phases 9-22)
2. Achieve Controlled Cutover for each domain (Phase 16)
3. Migrate actual data (Phase 23)
4. Verify V2 in production for at least one operational cycle
5. Then revisit this document

---

## Next Step

When Prompt 25 is invoked with a specific model name, the precondition is that this
document must be updated to mark that model as eligible. Currently no model qualifies.