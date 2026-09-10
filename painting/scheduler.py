"""
V2 Painting Scheduler - mirrors V1 PaintingScheduler behavior using V2 models.

Key mappings:
  V1 ProductionTask        → V2 ProductionOperation
  V1 WorkerProfile         → V2 Worker (accounts.models)
  V1 PaintingStage         → V2 PaintingProcessStage
  V1 PaintingAssignmentRule → V2 PaintingAssignmentRule
  V1 PaintingProcess       → V2 PaintingProcess
  V1 Holiday               → V2 Holiday (accounts.models)
  V1 PaintingSchedule      → V2 PaintingSchedule + PaintingScheduleItem

Worker identity: V1 used User.id (via WorkerProfile.user_id).
V2 Worker has OneToOne to User, so Worker.user_id == User.id.
ProductionOperation.assigned_worker is a FK to User (same identity).
"""

import logging
from datetime import datetime, time, timedelta
from collections import defaultdict, deque

import jdatetime
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import (
    PaintingProcessStage,
    PaintingAssignmentRule,
    PaintingSchedule,
    PaintingScheduleItem,
)
from accounts.models import Worker, Holiday
from production.models import ProductionOperation

logger = logging.getLogger(__name__)

DEFAULT_TASK_DURATION_MINUTES = 60
MAX_CASCADE_STEPS = 100


class CascadeCannotFit(Exception):
    def __init__(self, task, worker_id):
        self.task = task
        self.worker_id = worker_id


class CascadeTooComplex(Exception):
    pass


class CascadeCrossDayConflict(Exception):
    def __init__(self, task):
        self.task = task


def _worker_day_bounds(gregorian_date, worker=None, allow_overtime=False):
    """Return work-day bounds for a V2 Worker. 8:00–16:30, lunch 12:30–13:30."""
    start_time = worker.work_start if worker and worker.work_start else time(8, 0)
    end_time = time(16, 30)
    if worker and worker.work_end and not allow_overtime:
        end_time = worker.work_end
    break_start_time = worker.break_start if worker and worker.break_start else time(12, 30)
    break_end_time = worker.break_end if worker and worker.break_end else time(13, 30)

    if allow_overtime:
        end_time = time(23, 59)

    return {
        'start': timezone.make_aware(datetime.combine(gregorian_date, start_time)),
        'end': timezone.make_aware(datetime.combine(gregorian_date, end_time)),
        'break_start': timezone.make_aware(datetime.combine(gregorian_date, break_start_time)),
        'break_end': timezone.make_aware(datetime.combine(gregorian_date, break_end_time)),
    }


def _color_part_matches(operation, color_codes):
    """Check if an operation's color matches the given color codes list."""
    item = getattr(operation, 'order_item', None)
    if not item:
        return False
    color_part = getattr(operation, 'color_part', '') or ''

    try:
        from sales.models import OrderColor
        color_obj = item.ordercolor.filter(part=color_part).first()
        if color_obj and color_obj.code and color_obj.code != 'nan':
            code = str(color_obj.code)
            return code in [str(c) for c in color_codes]
    except Exception:
        pass

    try:
        product = getattr(item, 'product', None)
        if product:
            default_codes = product.default_colors
            if isinstance(default_codes, str):
                import json
                default_codes = json.loads(default_codes) or {}
            if isinstance(default_codes, dict):
                code = default_codes.get(color_part)
                if code and code != 'nan':
                    return str(code) in [str(c) for c in color_codes]
    except Exception:
        pass

    return False


def _task_matches_rule(operation, rule):
    """
    Check if a ProductionOperation matches a PaintingAssignmentRule.
    Mirrors V1 `_task_matches_rule`.
    """
    if rule.painting_stage is not None:
        if getattr(operation, 'painting_stage_id', None) != rule.painting_stage_id:
            return False

    if rule.process is not None:
        stage = getattr(operation, 'painting_stage', None)
        if not stage or stage.process_id != rule.process_id:
            return False

    if rule.color_codes:
        if not operation.order_item or not (operation.color_part or ''):
            return False
        return _color_part_matches(operation, rule.color_codes)

    return True


def _get_operation_next_stage(operation):
    """
    For a given operation, find the next painting stage in the same process
    for the same order_item + color_part. Mirrors V1 `_get_item_next_task`.
    """
    stage = getattr(operation, 'painting_stage', None)
    if not stage:
        return None
    process_id = stage.process_id
    sequence = stage.sequence

    return ProductionOperation.objects.filter(
        order_item_id=operation.order_item_id,
        color_part=operation.color_part or '',
        painting_stage__process_id=process_id,
        painting_stage__sequence__gt=sequence,
        planned_start__isnull=False,
    ).exclude(pk=operation.pk).select_related('painting_stage').order_by('painting_stage__sequence').first()


def _insert_and_cascade_worker_day(timeline, bounds, new_start, new_end, new_task_marker):
    """
    Insert a task into the worker-day timeline and cascade-shift subsequent
    tasks forward. The lunch break is immovable.
    Mirrors V1 `_insert_and_cascade_worker_day`.
    """
    lunch_start, lunch_end = bounds['break_start'], bounds['break_end']

    items = [list(row) for row in timeline if row[2] is not None]
    items.append([new_start, new_end, new_task_marker])
    items.sort(key=lambda r: r[0])

    pushed = []
    prev_end = bounds['start']

    for row in items:
        s, e, t = row
        old_s, old_e = s, e

        if s < prev_end:
            shift = prev_end - s
            s, e = s + shift, e + shift

        if s < lunch_end and e > lunch_start:
            shift = lunch_end - s
            s, e = s + shift, e + shift

        row[0], row[1] = s, e

        if (s, e) != (old_s, old_e) and t is not new_task_marker:
            pushed.append(t)

        if e > bounds['end']:
            raise CascadeCannotFit(t if t is not new_task_marker else new_task_marker, None)

        prev_end = e

    items.append([lunch_start, lunch_end, None])
    items.sort(key=lambda r: r[0])

    return items, pushed


def _maybe_enqueue_successor(op, new_end, ref_date, changes, task_objects, queue):
    """Enqueue the next stage operation in the chain, mirroring V1 behavior."""
    if not (op.order_item_id and op.color_part):
        return

    drying = op.painting_stage.drying_time_minutes if op.painting_stage else 0
    required_ready = new_end + timedelta(minutes=drying)

    succ = _get_operation_next_stage(op)
    if not succ:
        return

    for i, (q_op, q_wid, q_min) in enumerate(queue):
        if q_op.pk == succ.pk:
            if q_min is None or required_ready > q_min:
                queue[i] = (q_op, q_wid, required_ready)
            return

    if succ.pk in changes:
        succ_wid, succ_start, _ = changes[succ.pk]
    else:
        succ_wid, succ_start = succ.assigned_worker_id, succ.planned_start

    if succ_start is not None and succ_start >= required_ready:
        return

    if succ_start is not None and succ_start.date() != ref_date:
        raise CascadeCrossDayConflict(succ)

    task_objects.setdefault(succ.pk, succ)
    queue.append((succ, succ_wid, required_ready))


def _run_cascade_schedule(gregorian_date, initial_entries, exclude_operation_ids=None, allow_overtime=False):
    """
    Run the cascade scheduling engine for a single Gregorian date.
    Mirrors V1 `_run_cascade_schedule`.
    Should be called inside transaction.atomic().
    """
    exclude_operation_ids = set(exclude_operation_ids or [])
    initial_ids = {op.pk for op, _, _ in initial_entries} | exclude_operation_ids

    day_ops = list(
        ProductionOperation.objects.select_for_update().filter(
            painting_stage__isnull=False,
            planned_start__date=gregorian_date,
            planned_start__isnull=False,
        ).exclude(pk__in=initial_ids).select_related('painting_stage', 'order_item')
    )

    task_objects = {op.pk: op for op, _, _ in initial_entries}
    for op in day_ops:
        task_objects[op.pk] = op

    timelines = defaultdict(list)
    bounds_cache = {}

    def get_bounds(wid):
        if wid not in bounds_cache:
            worker = Worker.objects.filter(user_id=wid, station='paint').first()
            bounds_cache[wid] = _worker_day_bounds(gregorian_date, worker=worker, allow_overtime=allow_overtime)
        return bounds_cache[wid]

    for op in day_ops:
        wid = op.assigned_worker_id
        if wid is None:
            continue
        timelines[wid].append([op.planned_start, op.planned_end, op])

    changes = {}
    queue = deque(initial_entries)
    steps = 0

    while queue:
        steps += 1
        if steps > MAX_CASCADE_STEPS:
            raise CascadeTooComplex()

        cur_op, wid, min_start = queue.popleft()
        bounds = get_bounds(wid)

        for tl in timelines.values():
            tl[:] = [row for row in tl if not (row[2] is not None and row[2].pk == cur_op.pk)]

        if not any(row[2] is None for row in timelines[wid]):
            timelines[wid].append([bounds['break_start'], bounds['break_end'], None])

        duration = cur_op.painting_stage.duration_minutes if cur_op.painting_stage else DEFAULT_TASK_DURATION_MINUTES

        start_candidate = bounds['start']
        if min_start and min_start > start_candidate:
            start_candidate = min_start
        end_candidate = start_candidate + timedelta(minutes=duration)

        new_items, pushed = _insert_and_cascade_worker_day(
            timelines[wid], bounds, start_candidate, end_candidate, cur_op
        )
        timelines[wid] = new_items

        final_row = next(r for r in new_items if r[2] is cur_op)
        final_start, final_end = final_row[0], final_row[1]
        changes[cur_op.pk] = (wid, final_start, final_end)

        _maybe_enqueue_successor(
            cur_op, final_end, gregorian_date, changes, task_objects, queue
        )

        for pt in pushed:
            row = next(r for r in new_items if r[2] is pt)
            changes[pt.pk] = (wid, row[0], row[1])
            _maybe_enqueue_successor(
                pt, row[1], gregorian_date, changes, task_objects, queue
            )

    return changes, task_objects


def _is_working_day(jalali_date):
    """Check if a Jalali date is a working day (not weekend, not holiday)."""
    if not isinstance(jalali_date, jdatetime.date):
        jalali_date = jdatetime.date.today()
    if jalali_date.weekday() == 6:
        return False
    gregorian = jalali_date.togregorian()
    return not Holiday.objects.filter(date=gregorian).exists()


class V2PaintingScheduler:
    """
    V2 Painting Scheduler - mirrors V1 PaintingScheduler.

    Uses ProductionOperation as the task model (with painting_stage, assigned_worker,
    order_item, color_part, planned_start/planned_end, sequence).
    """

    def __init__(self, operation_ids, target_date, initial_item_cursors=None, assignment_rules=None):
        self.operation_ids = list(operation_ids) if operation_ids else []
        self.target_date = target_date if isinstance(target_date, jdatetime.date) else jdatetime.date.today()
        self.operations = []
        self.workers = []
        self.worker_schedule = {}
        self.worker_load = {}
        self._loaded = False
        self._all_day_operations = []
        self.initial_item_cursors = initial_item_cursors or {}

        self._order_worker_history = defaultdict(set)
        self._exclusion_map = {}
        self._excluded_items_map = {}
        self.assignment_rules = list(assignment_rules) if assignment_rules else list(
            PaintingAssignmentRule.objects.filter(is_active=True).select_related('worker')
        )
        self._item_workers = defaultdict(set)

    def _load(self):
        gregorian = self.target_date.togregorian()

        self._all_day_operations = list(
            ProductionOperation.objects.filter(
                painting_stage__isnull=False,
                planned_start__date=gregorian,
                planned_start__isnull=False,
            ).select_related('painting_stage', 'order_item')
        )

        if self.operation_ids:
            self.operations = list(
                ProductionOperation.objects.filter(
                    pk__in=self.operation_ids,
                    painting_stage__isnull=False,
                    status__in=['waiting', 'ready'],
                    planned_start__isnull=True,
                ).select_related('painting_stage', 'order_item').order_by('order_item_id', 'sequence')
            )

        # Load paint workers with their details
        self.workers = []
        paint_workers = Worker.objects.filter(
            station='paint',
            is_available=True,
        ).select_related('user').prefetch_related('excluded_products', 'excluded_items')

        for w in paint_workers:
            user = w.user
            skill_priority = {}
            if isinstance(w.skill_priority, dict):
                skill_priority = {k: int(v) for k, v in w.skill_priority.items() if str(v).isdigit()}
            self.workers.append({
                'user_id': user.id if user else None,
                'worker_id': w.id,
                'skills': list(
                    {token.strip() for s in (w.skills or []) for token in str(s).split() if token.strip()}
                ) if isinstance(w.skills, list) else [],
                'skill_priority': skill_priority,
                'full_name': f"{user.first_name} {user.last_name}".strip() or (user.username if user else str(w)),
                'worker_obj': w,
            })

        self.worker_schedule = {}
        self.worker_load = {}
        for w in self.workers:
            wid = w['user_id']
            if wid is not None:
                self.worker_schedule[wid] = []
                self.worker_load[wid] = 0

        # Calculate per-worker bounds and exclusion maps
        self._worker_bounds = {}
        for w in self.workers:
            wid = w['user_id']
            if wid is None:
                continue
            worker = w['worker_obj']
            self._worker_bounds[wid] = _worker_day_bounds(gregorian, worker=worker)

            excluded_ids = set(worker.excluded_products.values_list('id', flat=True))
            self._exclusion_map[wid] = excluded_ids
            self._excluded_items_map[wid] = set(
                worker.excluded_items.values_list('id', flat=True)
            )

        # Add lunch break to each worker's schedule
        for wid in self.worker_schedule:
            b = self._worker_bounds.get(wid)
            if b:
                self.worker_schedule[wid].append((b['break_start'], b['break_end'], None))

        # Populate schedules from existing day operations
        for op in self._all_day_operations:
            wid = op.assigned_worker_id
            if wid in self.worker_schedule:
                self.worker_schedule[wid].append((op.planned_start, op.planned_end, op))
                duration = int((op.planned_end - op.planned_start).total_seconds() / 60)
                self.worker_load[wid] = self.worker_load.get(wid, 0) + duration

        for wid in self.worker_schedule:
            self.worker_schedule[wid].sort(key=lambda x: x[0])

        # Order-worker history for sticky worker preference
        order_ids = {op.production_order_id for op in self.operations if op.production_order_id is not None}
        if order_ids:
            from production.models import ProductionOrder
            history_qs = ProductionOperation.objects.filter(
                production_order_id__in=order_ids,
                painting_stage__isnull=False,
                assigned_worker__isnull=False,
            ).values_list('production_order_id', 'assigned_worker_id').distinct()
            for order_id, worker_id in history_qs:
                self._order_worker_history[order_id].add(worker_id)

        # Populated _item_workers from existing operations for items in batch
        item_ids_in_batch = {op.order_item_id for op in self.operations if op.order_item_id}
        item_ids_in_batch.update({op.order_item_id for op in self._all_day_operations if op.order_item_id})
        if item_ids_in_batch:
            existing_item_workers = ProductionOperation.objects.filter(
                order_item_id__in=item_ids_in_batch,
                painting_stage__isnull=False,
                assigned_worker__isnull=False,
            ).values_list('order_item_id', 'color_part', 'assigned_worker_id')
            for item_id, color_part, wid in existing_item_workers:
                if item_id and wid:
                    key = (item_id, color_part or '')
                    self._item_workers[key].add(wid)

        # Compute initial item cursors (ready times) from existing day operations
        if not self.initial_item_cursors and self._all_day_operations:
            item_keys = {(op.order_item_id, op.color_part or '') for op in self._all_day_operations
                         if op.order_item_id}
            for item_id, color_part in item_keys:
                last_op = ProductionOperation.objects.filter(
                    order_item_id=item_id,
                    color_part=color_part,
                    painting_stage__isnull=False,
                    planned_end__isnull=False,
                ).order_by('-planned_end').first()
                if last_op:
                    drying = last_op.painting_stage.drying_time_minutes if last_op.painting_stage else 0
                    self.initial_item_cursors[(item_id, color_part)] = last_op.planned_end + timedelta(minutes=drying)

        self._loaded = True

    def _is_task_excluded_for_worker(self, worker_id, product_id, order_item_id):
        if product_id and product_id in self._exclusion_map.get(worker_id, set()):
            return True
        if order_item_id and order_item_id in self._excluded_items_map.get(worker_id, set()):
            return True
        return False

    def _find_gap(self, worker_id, duration, bounds, item_ready=None, prefer_early=False):
        if worker_id not in self.worker_schedule:
            return None

        intervals = sorted(self.worker_schedule[worker_id], key=lambda x: x[0])
        candidate = bounds['start']
        if item_ready and item_ready > candidate:
            candidate = item_ready

        best_start = None
        best_gap = timedelta.max

        for start, end, _ in intervals:
            if end <= candidate:
                continue
            if start > candidate:
                gap = start - candidate
                if gap >= timedelta(minutes=duration):
                    if prefer_early:
                        return candidate
                    if gap < best_gap:
                        best_gap = gap
                        best_start = candidate
                    if gap == timedelta(minutes=duration):
                        return candidate
            if end > candidate:
                candidate = end

        if bounds['end'] - candidate >= timedelta(minutes=duration):
            if prefer_early or best_start is None:
                return candidate
            if bounds['end'] - candidate < best_gap:
                best_start = candidate
            return best_start

        return best_start

    def _get_gap_size(self, worker_id, start, bounds):
        if worker_id not in self.worker_schedule:
            return None
        intervals = sorted(self.worker_schedule[worker_id], key=lambda x: x[0])
        for s, e, _ in intervals:
            if s > start:
                return int((s - start).total_seconds() / 60)
        return int((bounds['end'] - start).total_seconds() / 60)

    def _get_worker_load(self, worker_id):
        if worker_id not in self.worker_load:
            total = 0
            for start, end, op in self.worker_schedule.get(worker_id, []):
                if op is not None and start and end:
                    total += int((end - start).total_seconds() / 60)
            self.worker_load[worker_id] = total
        return self.worker_load.get(worker_id, 0)

    def _worker_rule_info(self, operation):
        info = {}
        for w in self.workers:
            wid = w.get('user_id')
            if wid is not None:
                info[wid] = {
                    'excluded': False,
                    'has_exclusive': False,
                    'matches_exclusive': False,
                }

        for rule in self.assignment_rules:
            if not rule.is_active:
                continue
            wid = rule.worker.user_id
            if wid not in info:
                continue

            op_matches = _task_matches_rule(operation, rule)

            if rule.rule_type == 'exclusion' and op_matches:
                info[wid]['excluded'] = True

            if rule.rule_type == 'exclusive':
                info[wid]['has_exclusive'] = True
                if op_matches:
                    info[wid]['matches_exclusive'] = True

        return info

    def _select_worker(self, operation, item_ready):
        try:
            skill = operation.painting_stage.required_skill if operation.painting_stage else 'painter'
            duration = operation.painting_stage.duration_minutes if operation.painting_stage else DEFAULT_TASK_DURATION_MINUTES
            is_short_task = duration <= 30

            item = getattr(operation, 'order_item', None)
            product = item.product if item and hasattr(item, 'product') else None
            product_id = product.id if product else None

            item_id = operation.order_item_id
            color_part = operation.color_part or ''
            item_key = (item_id, color_part)
            item_allowed_workers = None
            if item_id and len(self._item_workers.get(item_key, set())) >= 2:
                item_allowed_workers = self._item_workers.get(item_key, set())

            rule_info = self._worker_rule_info(operation)

            candidates = []

            for w in self.workers:
                wid = w.get('user_id')
                if wid is None:
                    continue

                if rule_info[wid]['excluded']:
                    continue
                if rule_info[wid]['has_exclusive'] and not rule_info[wid]['matches_exclusive']:
                    continue

                if skill not in (w.get('skills') or []):
                    continue

                if item_allowed_workers is not None and wid not in item_allowed_workers:
                    if not rule_info[wid]['matches_exclusive']:
                        continue

                if self._is_task_excluded_for_worker(wid, product_id, operation.order_item_id):
                    continue

                bounds = self._worker_bounds.get(wid)
                if bounds is None:
                    continue

                slot = self._find_gap(wid, duration, bounds, item_ready, prefer_early=is_short_task)
                if slot is None:
                    continue

                load = self._get_worker_load(wid)
                skill_priority = 0
                if skill and isinstance(w.get('skill_priority'), dict):
                    try:
                        skill_priority = int(w['skill_priority'].get(skill, 0))
                    except (TypeError, ValueError):
                        skill_priority = 0
                score = (slot - bounds['start']).total_seconds() / 60 + load * 50 - skill_priority * 50

                existing_worker_ids = self._order_worker_history.get(operation.production_order_id, set())
                if wid in existing_worker_ids:
                    score -= 200

                for rule in self.assignment_rules:
                    if rule.is_active and rule.worker.user_id == wid and _task_matches_rule(operation, rule):
                        if rule.rule_type in ('priority', 'exclusive'):
                            score -= rule.priority * 10
                            break

                if is_short_task:
                    gap_size = self._get_gap_size(wid, slot, bounds)
                    if gap_size and gap_size <= duration * 2:
                        score -= 40

                candidates.append((score, wid, slot))

            # Fallback: ignore item_allowed_workers constraint
            if not candidates and item_allowed_workers is not None:
                logger.warning(
                    f"Operation {operation.id} with sticky constraint "
                    f"({len(item_allowed_workers)} workers) found no eligible worker. Retrying without constraint..."
                )
                for w in self.workers:
                    wid = w.get('user_id')
                    if wid is None:
                        continue

                    if rule_info[wid]['excluded']:
                        continue
                    if rule_info[wid]['has_exclusive'] and not rule_info[wid]['matches_exclusive']:
                        continue

                    if skill not in (w.get('skills') or []):
                        continue

                    if self._is_task_excluded_for_worker(wid, product_id, operation.order_item_id):
                        continue

                    bounds = self._worker_bounds.get(wid)
                    if bounds is None:
                        continue

                    slot = self._find_gap(wid, duration, bounds, item_ready, prefer_early=is_short_task)
                    if slot is None:
                        continue

                    load = self._get_worker_load(wid)
                    skill_priority = 0
                    if skill and isinstance(w.get('skill_priority'), dict):
                        try:
                            skill_priority = int(w['skill_priority'].get(skill, 0))
                        except (TypeError, ValueError):
                            skill_priority = 0
                    score = (slot - bounds['start']).total_seconds() / 60 + load * 50 - skill_priority * 50

                    existing_worker_ids = self._order_worker_history.get(operation.production_order_id, set())
                    if wid in existing_worker_ids:
                        score -= 200

                    for rule in self.assignment_rules:
                        if rule.is_active and rule.worker.user_id == wid and _task_matches_rule(operation, rule):
                            if rule.rule_type in ('priority', 'exclusive'):
                                score -= rule.priority * 10
                                break

                    if is_short_task:
                        gap_size = self._get_gap_size(wid, slot, bounds)
                        if gap_size and gap_size <= duration * 2:
                            score -= 40

                    candidates.append((score, wid, slot))

            if not candidates:
                return None, None

            candidates.sort(key=lambda x: x[0])
            selected_score, selected_wid, selected_slot = candidates[0]
            logger.debug(
                f"Selected worker for operation {operation.id}: "
                f"worker {selected_wid} score {selected_score:.1f}, slot {selected_slot}"
            )
            return selected_wid, selected_slot

        except Exception:
            logger.exception("Error in _select_worker")
            raise

    def _assign_task(self, operation, worker_id, start):
        try:
            duration = operation.painting_stage.duration_minutes if operation.painting_stage else DEFAULT_TASK_DURATION_MINUTES
            drying = operation.painting_stage.drying_time_minutes if operation.painting_stage else 0
            end = start + timedelta(minutes=duration)

            if worker_id not in self.worker_schedule:
                self.worker_schedule[worker_id] = []
            self.worker_schedule[worker_id].append((start, end, operation))
            self.worker_schedule[worker_id].sort(key=lambda x: x[0])
            if operation is not None:
                self.worker_load[worker_id] = self.worker_load.get(worker_id, 0) + duration

            operation._assigned_worker_id = worker_id
            operation._planned_start = start
            operation._planned_end = end

            if operation.production_order_id is not None:
                self._order_worker_history[operation.production_order_id].add(worker_id)

            if operation.order_item_id:
                key = (operation.order_item_id, operation.color_part or '')
                self._item_workers[key].add(worker_id)

            return end + timedelta(minutes=drying)

        except Exception:
            logger.exception("Error in _assign_task")
            raise

    def build(self):
        if not self._loaded:
            self._load()

        if not self.operations or not self.workers:
            return 0

        self.operations.sort(key=lambda t: (t.order_item_id, t.sequence))

        scheduled = 0
        item_cursors = dict(self.initial_item_cursors)
        blocked_chains = set()

        for op in self.operations:
            cursor_key = (op.order_item_id, op.color_part or '')

            if cursor_key in blocked_chains:
                continue

            item_ready = item_cursors.get(cursor_key)

            worker_id, start = self._select_worker(op, item_ready)
            if worker_id is None:
                if cursor_key not in blocked_chains:
                    logger.warning(
                        f"Stage {op.painting_stage.name if op.painting_stage else op.id} "
                        f"for item {op.order_item_id} (color part: {op.color_part}) "
                        f"could not be scheduled; remaining stages in chain are skipped."
                    )
                blocked_chains.add(cursor_key)
                continue

            next_ready = self._assign_task(op, worker_id, start)
            item_cursors[cursor_key] = next_ready
            scheduled += 1

        self._remaining_item_cursors = item_cursors

        logger.info(f"{scheduled} of {len(self.operations)} operations scheduled.")
        return scheduled

    def apply(self):
        """Apply scheduled operations to database as PaintingScheduleItems."""
        operations_to_update = [
            op for op in self.operations if hasattr(op, '_assigned_worker_id')
        ]
        if not operations_to_update:
            return 0

        gregorian = self.target_date.togregorian()

        with transaction.atomic():
            schedule = PaintingSchedule.objects.get_or_create(
                date=gregorian,
                defaults={
                    'created_by': None,
                    'status': 'in_progress',
                }
            )[0]

            items_to_create = []
            for op in operations_to_update:
                worker = Worker.objects.filter(user_id=getattr(op, '_assigned_worker_id', None)).first()
                items_to_create.append(PaintingScheduleItem(
                    schedule=schedule,
                    production_operation=op,
                    worker=worker,
                    painting_stage=op.painting_stage,
                    scheduled_start=getattr(op, '_planned_start', None),
                    scheduled_end=getattr(op, '_planned_end', None),
                ))

            PaintingScheduleItem.objects.bulk_create(items_to_create)

            # Update ProductionOperation planned_start/planned_end/assigned_worker
            bulk_ops = []
            for op in operations_to_update:
                op.assigned_worker_id = getattr(op, '_assigned_worker_id', None)
                op.planned_start = getattr(op, '_planned_start', None)
                op.planned_end = getattr(op, '_planned_end', None)
            ProductionOperation.objects.bulk_update(
                operations_to_update,
                ['assigned_worker_id', 'planned_start', 'planned_end']
            )

            logger.info(f"{len(operations_to_update)} operations applied to PaintingSchedule #{schedule.id}.")
            return len(operations_to_update)

    def schedule(self):
        """Schedule operations and apply to database. Returns (count, item_cursors)."""
        self._load()
        count = self.build()
        self.apply()
        logger.info(f"Scheduling complete: {count} operations scheduled.")
        return count, getattr(self, '_remaining_item_cursors', {})


# ===================================================================
# Public API functions
# ===================================================================

def is_paint_working_day(jalali_date):
    """Check if a Jalali date is a working day for painting."""
    return _is_working_day(jalali_date)


def schedule_painting_operations(operation_ids, target_date, created_by=None):
    """
    Schedule painting operations for a given date.

    Args:
        operation_ids: List of ProductionOperation PKs to schedule.
        target_date: Jalali date (jdatetime.date) for scheduling.
        created_by: User who initiated the scheduling (optional).

    Returns:
        Tuple of (scheduled_count, item_cursors_dict)
    """
    scheduler = V2PaintingScheduler(operation_ids, target_date)
    return scheduler.schedule()
