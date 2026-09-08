# Phase 29: Performance and Reliability Baseline

Status: **Assessment Only — No Changes Made**

## Current State

- SQLite 6.4 MB database
- Django 5.2 with debug mode on
- No query logging infrastructure
- No index analysis performed

## Known Hotspots

1. `product/views.py` — 100+ references to OrderItem, heavy dashboard queries
2. `PaintingScheduler` in `product/utils.py` — complex scheduling algorithm
3. `reporting/selectors.py` — aggregation queries without verified indexes
4. Dashboard endpoints — likely N+1 patterns

## Required Work (Future)

- Enable Django debug-toolbar or Silk for query profiling
- Add indexes only where query analysis proves need
- Never modify PaintingScheduler algorithm
- Register baseline before any optimization

## No Changes Made This Phase