# Phase 9: EventService, AuditLog, QualityInspection/Defect/ReworkOrder, Read-only Selectors

## Status: COMPLETE

## Objective
Provide V2 infrastructure for event logging, audit trails, quality inspection, and read-only selectors following:
- View = thin (delegates to Service/Selector)
- mutation → Service only
- query → Selector only
- permission + audit for all mutations

## V2 Models (pre-existing)

**reporting/models.py:**
- `BusinessEvent` (category, event_type, occurred_at, content_object via GenericFK, metadata, correlation_id, legacy_reference)
- `AuditLog` (user, action, model_name, object_id, changes, ip_address, timestamp)

**quality/models.py:**
- `QualityInspection` (inspection_number, type, production_order, production_operation, result, inspected_by, inspected_at)
- `QualityDefect` (inspection FK, code, description, severity, quantity, is_reworkable)
- `ReworkOrder` (rework_number, production_order, production_operation, status, defect/repair_description, quantity, actual_cost, assigned_to, planned/actual start/end)

## New Service Files

### `reporting/services.py`
- `EventService.log_event()` — generic event creation with content_object GenericFK
- `EventService.log_production_event()` — production-specific events
- `EventService.log_inventory_event()` — inventory-specific events
- `EventService.log_quality_event()` — quality-specific events
- `EventService.log_painting_event()` — painting-specific events
- `EventService.log_shipping_event()` — shipping-specific events
- `EventService.log_with_correlation()` — correlation_id-based tracing

- `AuditService.log()` — generic audit entry
- `AuditService.log_create()` — CREATE audit
- `AuditService.log_update()` — UPDATE audit with changes dict
- `AuditService.log_delete()` — DELETE audit
- `AuditService.log_status_change()` — status change with old/new
- `AuditService.log_assignment()` — worker assignment with old/new

### `quality/services.py`
- `QualityService.create_inspection()` — creates QualityInspection with auto-numbering
- `QualityService.add_defect()` — adds QualityDefect to inspection
- `QualityService.create_rework_order()` — creates ReworkOrder with auto-numbering
- `QualityService.start_rework()` — transitions to in_progress
- `QualityService.complete_rework()` — completes rework with quantity validation
- `EventService.log_quality_event` called for every mutation

### `quality/selectors.py`
- `QualitySelectors.get_inspections_for_order()` — filter by order/type/result
- `QualitySelectors.get_inspection_with_defects()` — prefetch defects
- `QualitySelectors.get_rework_orders_for_order()` — filter by order/status
- `QualitySelectors.get_rework_order_with_items()` — prefetch items
- `QualitySelectors.get_recent_inspections()` — last N days
- `QualitySelectors.get_defect_summary()` — aggregate by severity

### `reporting/selectors.py` (pre-existing, enhanced)
- `ReportingSelectors.get_business_events()` — filter by category/type/date
- `ReportingSelectors.get_audit_logs()` — filter by user/action/date
- `ReportingSelectors.get_migration_stats()` — aggregate migration stats
- `ReportingSelectors.get_legacy_mappings()` — legacy mappings

## Traceability Pattern

All mutations in V2 services should create `BusinessEvent` entries:
```python
EventService.log_production_event('completed', operation, user)
AuditService.log_status_change(user, 'ProductionOperation', operation, 'waiting', 'completed')
```

## Test Coverage

Tests in `quality/tests/test_quality_services.py` and `reporting/tests/test_event_services.py`:
- create_inspection generates unique number
- add_defect creates defect with inspection FK
- complete_rework validates quantity
- EventService creates event with content_object
- AuditService logs create/update/delete
- Selectors return filtered/prefetched querysets
- Permission integration: events created for all mutations
