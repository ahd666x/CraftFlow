# Phase 50: Annual Architecture Backlog

Date: 2026-09-08
Status: **Evidence-Based — No New Refactor Started**

## Input Sources

- Phase 41: Go-Live Readiness (No-Go)
- Phase 43: Capacity Planning (SQLite bottleneck)
- Phase 47: Auditability Review (AuditLog unused)
- Phase 28: Security Audit (QR scan lacks auth)
- Phase 29: Performance Baseline (no profiling)
- Phase 35: Data Quality (not implemented)
- Phase 36: Monitoring (not implemented)

## Backlog

### Immediate (Before Any Cutover)

| # | Problem | Evidence | Domain | Impact | Risk | Effort |
|---|---------|----------|--------|--------|------|--------|
| 1 | No CI pipeline | Phase 33 | All | Every PR | Low | Medium |
| 2 | QR scan lacks auth | Phase 28 | Barcode | Security | Low | Small |
| 3 | SECRET_KEY hardcoded | Phase 48 | All | Security | Low | Small |
| 4 | AuditLog unused | Phase 47 | All | Compliance | Low | Medium |
| 5 | No monitoring | Phase 36 | All | Operations | Low | Medium |

### Short-Term (After First Cutover)

| # | Problem | Evidence | Domain | Impact | Risk | Effort |
|---|---------|----------|--------|--------|------|--------|
| 6 | StockBalance direct mutation | Phase 29 | Inventory | Data integrity | Low | Small |
| 7 | complete_operation sequence bug | Phase 3.1 | Production | Workflow | Low | Small |
| 8 | No regression suite | Phase 34 | All | Quality | Low | Medium |
| 9 | No data quality checks | Phase 35 | All | Data health | Low | Medium |
| 10 | SQLite FKs not enforced | Phase 26 | All | Data integrity | Low | High |

### Medium Term

| # | Problem | Evidence | Domain | Impact | Risk | Effort |
|---|---------|----------|--------|--------|------|--------|
| 11 | No query profiling | Phase 29 | All | Performance | Low | Medium |
| 12 | Warehouse idempotency | Phase 3.5 | Warehouse | Reliability | Low | Medium |
| 13 | No README/architecture docs | Phase 32 | All | Onboarding | Low | Small |
| 14 | Feature flag audit missing | Phase 37 | All | Compliance | Low | Small |

## Acceptance Criteria

Each item must be:
- Small and testable
- Independent of other items
- Reversible
- Approved by user before execution

## Next Steps

Continue based on actual findings from Phases 41-50, not pre-scripted phases.