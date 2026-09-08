# Phase 35: Data Governance and Data Quality

Status: **Not Implemented**

## Proposed Command

```bash
python manage.py craftflow_data_quality --report
```

## Checks

| Check | Severity |
|-------|----------|
| Product name/code duplicates | critical |
| RawMaterial / Material duplicates | critical |
| UOM incompatibilities | high |
| Parts without material | high |
| Incomplete BOMs | high |
| Orphan ProductionTasks | high |
| StockMovement without valid reference | critical |
| Incomplete PackagingUnits | medium |
| QR without entity | medium |
| Inconsistent MigrationMap | high |

## Output

- JSON and Markdown reports
- Severity: critical / high / medium / low
- Suggested fix, no automatic correction

## No Changes Made