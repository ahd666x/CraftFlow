# Phase 8: V2 PaintingScheduler

## Status: COMPLETE

## Objective
Implement V2 PaintingScheduler that mirrors V1 `PaintingScheduler` behavior using V2 models:
- `ProductionOperation` (task) instead of `ProductionTask`
- `Worker` + `WorkerSchedule` instead of `WorkerProfile`
- `PaintingProcessStage` instead of `PaintingStage`

## V1 Behaviors to Characterize

| # | Behavior | V1 Source | V2 Target |
|---|---|---|---|
| 1 | Cascade insert | `_insert_and_cascade_worker_day` | `painting/scheduler.py` |
| 2 | Cascade shift (domino) | same function | same |
| 3 | Sticky worker | `_order_worker_history`, `_item_workers` | `V2PaintingScheduler._order_worker_history` |
| 4 | Worker assignment rules | `_task_matches_rule`, `_worker_rule_info` | V2 same |
| 5 | Color compatibility | `_task_matches_rule` (color_codes path) | `_color_part_matches` |
| 6 | Process/stage dependency | `_get_item_next_task`, `_maybe_enqueue_successor` | `_get_operation_next_stage` |
| 7 | Drying time | `drying_time_minutes` propagation | same |
| 8 | Holiday/weekend | `is_working_day`, `Holiday` | `_is_working_day` |
| 9 | Worker bounds | `_worker_day_bounds` | `_worker_day_bounds` |
| 10 | Unscheduled/ghost task | `get_unscheduled_ready_items` | scheduler with empty ops |
| 11 | CascadeOverflowError | `_CascadeCannotFit` | `CascadeCannotFit` |

## V1 Code Reference

V1 `PaintingScheduler` is in `product/utils.py` lines 745–1252.

Key functions ported to V2:
- `_worker_day_bounds` → V2 uses `Worker` model (worker.work_start, etc.)
- `_task_matches_rule` → uses `operation.painting_stage`, `operation.order_item`, `operation.color_part`
- `_get_item_next_task` → `_get_operation_next_stage` (filters by painting_stage__sequence)
- `_insert_and_cascade_worker_day` → identical logic
- `_run_cascade_schedule` → filters by `painting_stage__isnull=False`
- `PaintingScheduler.build()` → uses `operation.sequence` instead of `step_order`
- `PaintingScheduler.apply()` → creates `PaintingScheduleItem` + bulk_updates `ProductionOperation`

## Test Plan

Tests in `painting/tests/test_scheduler_characterization.py`:

| Test Class | Tests |
|---|---|
| TestCascadeInsert | cascade_insert_shifts_subsequent, cascade_insert_into_gap, cascade_cannot_fit, cascade_skips_lunch |
| TestStickyWorker | sticky_worker_same_order_item |
| TestWorkerAssignmentRules | exclusive_rule_filters_workers, exclusion_rule_blocks_worker, priority_rule_affects_score |
| TestColorCompatibility | color_code_matching_process, color_code_no_match |
| TestProcessStageDependency | drying_time_propagation, stage_chain_dependency |
| TestHolidayWeekend | is_working_day_weekend, is_working_day_holiday, is_working_day_normal |
| TestWorkerBounds | custom_worker_hours, default_worker_bounds, overtime_extended_end |
| TestUnscheduledGhostTask | unscheduled_operation_not_scheduled |
| TestCascadeOverflow | cascade_cannot_fit_day_bounds |

## V2 Model Notes

`ProductionOperation` has these V1-compatible fields:
- `painting_stage` (FK to PaintingProcessStage)
- `assigned_worker` (FK to User)
- `order_item` (FK to CustomerOrderItem)
- `color_part` (CharField)
- `planned_start` / `planned_end` (DateTimeField)
- `sequence` (PositiveIntegerField) — equivalent to V1 `step_order`
- `production_order` (FK to ProductionOrder)
- `status` (waiting, ready, in_progress, etc.)

`Worker` model has:
- `user` (OneToOne to User) — Worker.user_id == User.id
- `station` (choices including 'paint')
- `skills` (JSONField list)
- `skill_priority` (JSONField dict)
- `is_available` (BooleanField)
- `work_start`, `work_end`, `break_start`, `break_end` (TimeField)
- `excluded_products`, `excluded_items` (M2F)

`Holiday` in V2 is in `accounts.models` (same as `is_working_day` source).
