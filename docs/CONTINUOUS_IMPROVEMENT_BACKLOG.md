# Phase 40: Continuous Improvement Backlog

Status: **Prioritized — No New Refactor Started**

## High Priority

| # | Domain | Problem | Evidence | Effort |
|---|--------|---------|----------|--------|
| 1 | All | No CI pipeline | No automated checks | Medium |
| 2 | Barcode | QR scan lacks authorization | Audit finding | Small |
| 3 | Security | SECRET_KEY hardcoded | settings.py | Small |
| 4 | Inventory | StockBalance direct mutation risk | Audit finding | Small |
| 5 | Production | complete_operation sequence logic | Audit finding | Small |

## Medium Priority

| # | Domain | Problem | Evidence | Effort |
|---|--------|---------|----------|--------|
| 6 | Reporting | AuditLog has no callers | Audit finding | Medium |
| 7 | Warehouse | No idempotency key on issue | Audit finding | Medium |
| 8 | Packaging | No tests for packaging workflow | Test gap | Medium |
| 9 | Shipping | No tests for shipping workflow | Test gap | Medium |
| 10 | Events | BusinessEvent has no callers | Audit finding | Medium |

## Low Priority

| # | Domain | Problem | Evidence | Effort |
|---|--------|---------|----------|--------|
| 11 | All | No README.md | Missing | Small |
| 12 | All | No ARCHITECTURE.md | Missing | Small |
| 13 | Performance | No query profiling | Missing | Medium |
| 14 | Monitoring | No logging infrastructure | Missing | Medium |

## Rules

- Each item must be small, testable, and independent
- No item titled "rewrite entire system"
- No item titled "migrate all V1 to V2"
- Each item needs: domain, problem, evidence, risk, user impact, effort, dependency, acceptance criteria, rollback need, proposed prompt

## Next Steps

After this backlog, continue based on actual bugs and domain-specific issues reported,
not pre-scripted phases.