# Phase 43: Capacity Planning

Status: **Assessment Only — No Changes Made**

## Current State

- Database: SQLite 6.4 MB
- ProductionTask: unknown count
- StockMovement: unknown count
- QR media: unknown count

## Bottlenecks

| Area | Evidence | Threshold | Mitigation | Priority |
|------|----------|-----------|------------|----------|
| SQLite single-file | 6.4 MB file | ~1GB | PostgreSQL migration | High |
| No index analysis | Query profiling missing | N/A | Add indexes after profiling | Medium |
| Dashboard queries | Likely N+1 in views.py | N/A | Use selectors | Medium |
| QR media growth | Image files per order | N/A | Archive old QR images | Low |
| Backup duration | Not measured | N/A | Incremental backup | Low |

## PostgreSQL Need

**Yes — required** for FK enforcement, real row locking, and scalability.
See Phase 26 for migration plan.

## No Changes Made