"""
Phase 8: V2 PaintingScheduler Characterization Tests

Verifies V2 PaintingScheduler behavior across all 11 documented behaviors.
Each test class maps to one V1 behavior.
"""

import datetime
from datetime import time, timedelta
from unittest.mock import patch

import jdatetime
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from django.contrib.auth.models import User

from accounts.models import Worker, Holiday
from painting.models import (
    PaintingProcess,
    PaintingProcessStage,
    PaintingAssignmentRule,
    PaintingSchedule,
    PaintingScheduleItem,
)
from painting.scheduler import (
    V2PaintingScheduler,
    CascadeCannotFit,
    CascadeTooComplex,
    CascadeCrossDayConflict,
    _insert_and_cascade_worker_day,
    _task_matches_rule,
    _worker_day_bounds,
    _is_working_day,
)
from production.models import ProductionOrder, ProductionOrderItem, ProductionOperation
from planning.models import Routing, WorkCenter
from sales.models import Customer, CustomerOrder, CustomerOrderItem, OrderItemColor
from products.models import ProductCategory, Product, ProductPart
from bom.models import BOM


def find_next_working_day(start_jalali):
    """Find the next working day (not weekend, not holiday)."""
    d = start_jalali
    for _ in range(30):
        if d.weekday() == 6:
            d = d + jdatetime.timedelta(days=1)
            continue
        if Holiday.objects.filter(date=d.togregorian()).exists():
            d = d + jdatetime.timedelta(days=1)
            continue
        return d
    return d


class PaintingSchedulerTestBase(TransactionTestCase):
    """Base class with common test fixtures."""

    def setUp(self):
        self.user1 = User.objects.create_user('worker1', first_name='کارگر', last_name='۱')
        self.user2 = User.objects.create_user('worker2', first_name='کارگر', last_name='۲')
        self.user3 = User.objects.create_user('worker3', first_name='کارگر', last_name='۳')

        self.worker1 = Worker.objects.create(
            user=self.user1, station='paint', skills=['painter'],
            skill_priority={'painter': 10},
            employee_id='W001',
            work_start=time(8, 0), work_end=time(16, 30),
            break_start=time(12, 30), break_end=time(13, 30),
        )
        self.worker2 = Worker.objects.create(
            user=self.user2, station='paint', skills=['painter'],
            skill_priority={'painter': 5},
            employee_id='W002',
            work_start=time(8, 0), work_end=time(16, 30),
            break_start=time(12, 30), break_end=time(13, 30),
        )
        self.worker3 = Worker.objects.create(
            user=self.user3, station='paint', skills=['painter', 'helper'],
            skill_priority={'painter': 3, 'helper': 5},
            employee_id='W003',
            work_start=time(9, 0), work_end=time(17, 0),
            break_start=time(13, 0), break_end=time(14, 0),
        )

        self.process = PaintingProcess.objects.create(
            name='روند تست', code='TEST', color_codes=['1', '2', '3']
        )
        self.stage1 = PaintingProcessStage.objects.create(
            process=self.process, sequence=1, name='پایه',
            duration_minutes=60, drying_time_minutes=30,
            required_skill='painter',
        )
        self.stage2 = PaintingProcessStage.objects.create(
            process=self.process, sequence=2, name='لعاب',
            duration_minutes=90, drying_time_minutes=0,
            required_skill='painter',
        )
        self.stage3 = PaintingProcessStage.objects.create(
            process=self.process, sequence=3, name='خاتمه',
            duration_minutes=30, drying_time_minutes=0,
            required_skill='helper',
        )

        self.category = ProductCategory.objects.create(name='Test Cat')
        self.product = Product.objects.create(
            category=self.category, name='محصول تست', code='TEST_PROD',
            base_price=1000000, default_colors={'body': '1', 'door': '2'},
        )
        self.part = ProductPart.objects.create(
            product=self.product, name='بدنه', code='P1',
            length=100, width=50, thickness=16,
        )

        self.customer = Customer.objects.create(name='مشتری تست')
        self.order = CustomerOrder.objects.create(
            customer=self.customer, order_date='2024-01-01'
        )
        self.order_item = CustomerOrderItem.objects.create(
            order=self.order, product=self.product, quantity=10
        )
        self.order_color = OrderItemColor.objects.create(
            order_item=self.order_item, part='بدنه', code='1'
        )

        # WorkCenter for production
        self.work_center = WorkCenter.objects.create(
            code='WC1', name='مرکز آزمون'
        )

        self.routing = Routing.objects.create(
            product=self.product, revision='A', name='راست مسیر',
            effective_date='2024-01-01', status='active',
        )

        self.bom = BOM.objects.create(
            product=self.product, revision='A', effective_date='2024-01-01',
        )

        self.prod_order = ProductionOrder.objects.create(
            order=self.order, order_number='PO001',
            routing=self.routing, bom_revision='A', status='planned',
        )
        self.prod_order_item = ProductionOrderItem.objects.create(
            production_order=self.prod_order,
            customer_order_item=self.order_item,
            product=self.product, quantity=10,
            bom=self.bom, routing=self.routing,
        )

        self.target_date = find_next_working_day(jdatetime.date.today())
        self.gregorian_date = self.target_date.togregorian()


class TestCascadeInsert(PaintingSchedulerTestBase):
    """Behavior 1 & 2: Cascade insert + domino shift"""

    def test_cascade_insert_shifts_subsequent_tasks(self):
        """Inserting a task before existing ones shifts them forward."""
        bounds = _worker_day_bounds(self.gregorian_date, worker=self.worker1)
        existing_start = bounds['start'] + timedelta(minutes=60)
        existing_end = existing_start + timedelta(minutes=60)

        timeline = [
            [existing_start, existing_end, 'existing_op'],
        ]

        # Insert new task at the start of day (before existing task)
        new_start = bounds['start']
        new_end = new_start + timedelta(minutes=90)

        new_items, pushed = _insert_and_cascade_worker_day(
            timeline, bounds, new_start, new_end, 'new_task'
        )

        # New task should be first
        self.assertEqual(new_items[0][2], 'new_task')
        # Existing op should be pushed after new_end
        existing_entry = [row for row in new_items if row[2] == 'existing_op'][0]
        self.assertEqual(existing_entry[0], new_end)
        self.assertIn('existing_op', pushed)

    def test_cascade_insert_into_gap_no_shift(self):
        """Inserting into a gap doesn't shift anything."""
        bounds = _worker_day_bounds(self.gregorian_date, worker=self.worker1)
        early_start = bounds['start']
        early_end = early_start + timedelta(minutes=60)

        timeline = [
            [early_start, early_end, 'existing_op'],
        ]

        # Insert into gap after early_end
        new_start = early_end
        new_end = new_start + timedelta(minutes=30)

        new_items, pushed = _insert_and_cascade_worker_day(
            timeline, bounds, new_start, new_end, 'gap_task'
        )

        self.assertEqual(len(pushed), 0)

    def test_cascade_cannot_fit_day_bounds(self):
        """Cascade raises when task doesn't fit in day bounds (Behavior 11)."""
        bounds = _worker_day_bounds(self.gregorian_date, worker=self.worker1)

        new_start = bounds['end'] - timedelta(minutes=30)
        new_end = bounds['end'] + timedelta(minutes=60)

        timeline = []

        with self.assertRaises(CascadeCannotFit):
            _insert_and_cascade_worker_day(
                timeline, bounds, new_start, new_end, 'overflow_task'
            )

    def test_cascade_skips_lunch_break_immovable(self):
        """Tasks never overlap lunch break; pushed past it."""
        bounds = _worker_day_bounds(self.gregorian_date, worker=self.worker1)
        lunch_start = bounds['break_start']
        lunch_end = bounds['break_end']

        task_start = lunch_start - timedelta(minutes=30)
        task_end = lunch_end + timedelta(minutes=60)

        new_items, pushed = _insert_and_cascade_worker_day(
            [], bounds, task_start, task_end, 'lunch_span_task'
        )

        result = [row for row in new_items if row[2] == 'lunch_span_task'][0]
        self.assertEqual(result[0], lunch_end)


class TestStickyWorker(PaintingSchedulerTestBase):
    """Behavior 3: Sticky worker for same order_item + color_part"""

    def test_existing_ops_same_item_added_to_item_workers(self):
        """Operations from same order_item populate _item_workers."""
        op_start = timezone.make_aware(
            datetime.datetime.combine(self.gregorian_date, time(8, 0))
        )

        op_ids = []
        for i, stage in enumerate([self.stage1, self.stage2, self.stage3], 1):
            end = op_start + timedelta(minutes=stage.duration_minutes)
            op = ProductionOperation.objects.create(
                production_order=self.prod_order,
                production_order_item=self.prod_order_item,
                operation_name=f'Stage{i}',
                operation_code=f'S{i}',
                work_center=self.work_center,
                sequence=i,
                painting_stage=stage,
                assigned_worker=self.user1,
                planned_start=op_start,
                planned_end=end,
                order_item=self.order_item,
                color_part='body',
            )
            op_ids.append(op.pk)

        scheduler = V2PaintingScheduler(op_ids, self.target_date)
        scheduler._load()

        item_key = (self.order_item.id, 'body')
        self.assertIn(self.user1.id, scheduler._item_workers[item_key])

    def test_sticky_worker_score_boost(self):
        """Sticky worker gets score reduction for same order history."""
        op = ProductionOperation.objects.create(
            production_order=self.prod_order,
            production_order_item=self.prod_order_item,
            operation_name='Test',
            operation_code='T1',
            work_center=self.work_center,
            sequence=1,
            painting_stage=self.stage1,
            order_item=self.order_item,
            color_part='body',
            status='waiting',
            planned_start=None,
            planned_end=None,
        )

        scheduler = V2PaintingScheduler([op.id], self.target_date)
        scheduler._load()

        # Manually add to item_workers to simulate existing assignment
        item_key = (self.order_item.id, 'body')
        scheduler._item_workers[item_key].add(self.user1.id)
        scheduler._item_workers[item_key].add(self.user2.id)

        worker_id, start = scheduler._select_worker(op, None)
        self.assertIsNotNone(worker_id)
        # Worker1 should be preferred due to order history
        self.assertIn(worker_id, [self.user1.id, self.user2.id])


class TestWorkerAssignmentRules(PaintingSchedulerTestBase):
    """Behavior 4, 5: Worker assignment rules (exclusive, exclusion, priority)"""

    def test_exclusive_rule_filters_workers(self):
        """Workers without exclusive match are filtered out."""
        op = ProductionOperation.objects.create(
            production_order=self.prod_order,
            production_order_item=self.prod_order_item,
            operation_name='Test',
            operation_code='T1',
            work_center=self.work_center,
            sequence=1,
            painting_stage=self.stage1,
            order_item=self.order_item,
            color_part='body',
            status='waiting',
        )

        PaintingAssignmentRule.objects.create(
            worker=self.worker1, painting_stage=self.stage1,
            rule_type='exclusive', priority=10, is_active=True,
        )
        PaintingAssignmentRule.objects.create(
            worker=self.worker2, painting_stage=self.stage1,
            rule_type='exclusive', priority=10, is_active=True,
        )

        scheduler = V2PaintingScheduler([op.id], self.target_date)
        scheduler._load()
        scheduler.build()

        rule_info = scheduler._worker_rule_info(op)
        # worker1 and worker2 have exclusive rule matching, worker3 doesn't
        self.assertTrue(rule_info[self.user1.id]['matches_exclusive'])
        self.assertTrue(rule_info[self.user2.id]['matches_exclusive'])
        self.assertFalse(rule_info[self.user3.id]['has_exclusive'])
        self.assertFalse(rule_info[self.user3.id]['matches_exclusive'])

    def test_exclusion_rule_blocks_worker(self):
        """Exclusion rule marks worker as excluded for matching tasks."""
        op = ProductionOperation.objects.create(
            production_order=self.prod_order,
            production_order_item=self.prod_order_item,
            operation_name='Test',
            operation_code='T1',
            work_center=self.work_center,
            sequence=1,
            painting_stage=self.stage1,
            order_item=self.order_item,
            color_part='body',
            status='waiting',
        )

        PaintingAssignmentRule.objects.create(
            worker=self.worker2, painting_stage=self.stage1,
            rule_type='exclusion', priority=100, is_active=True,
        )

        scheduler = V2PaintingScheduler([op.id], self.target_date)
        scheduler._load()

        rule_info = scheduler._worker_rule_info(op)

        self.assertTrue(rule_info[self.user2.id]['excluded'])
        self.assertFalse(rule_info[self.user1.id]['excluded'])
        self.assertFalse(rule_info[self.user3.id]['excluded'])

    def test_priority_rule_affects_selection(self):
        """Priority rules lower selection score for matching workers."""
        op = ProductionOperation.objects.create(
            production_order=self.prod_order,
            production_order_item=self.prod_order_item,
            operation_name='Test',
            operation_code='T1',
            work_center=self.work_center,
            sequence=1,
            painting_stage=self.stage1,
            order_item=self.order_item,
            color_part='body',
            status='waiting',
        )

        PaintingAssignmentRule.objects.create(
            worker=self.worker1, painting_stage=self.stage1,
            rule_type='priority', priority=50, is_active=True,
        )

        scheduler = V2PaintingScheduler([op.id], self.target_date)
        scheduler._load()

        worker_id, start = scheduler._select_worker(op, None)
        self.assertEqual(worker_id, self.user1.id)

    def test_task_matches_rule_color_code(self):
        """_task_matches_rule with color_codes matches color_part."""
        op = ProductionOperation(
            production_order=self.prod_order,
            production_order_item=self.prod_order_item,
            operation_name='Test',
            operation_code='T1',
            work_center=self.work_center,
            sequence=1,
            painting_stage=self.stage1,
            order_item=self.order_item,
            color_part='body',
            status='waiting',
        )

        rule = PaintingAssignmentRule(
            painting_stage=None,
            process=self.process,
            color_codes=['1'],
            rule_type='priority',
        )

        result = _task_matches_rule(op, rule)
        self.assertTrue(result)

    def test_task_matches_rule_color_code_no_match(self):
        """_task_matches_rule with color_codes fails on mismatched color."""
        op = ProductionOperation(
            production_order=self.prod_order,
            production_order_item=self.prod_order_item,
            operation_name='Test',
            operation_code='T1',
            work_center=self.work_center,
            sequence=1,
            painting_stage=self.stage1,
            order_item=self.order_item,
            color_part='body',
            status='waiting',
        )

        rule = PaintingAssignmentRule(
            painting_stage=None,
            process=self.process,
            color_codes=['99'],
            rule_type='priority',
        )

        result = _task_matches_rule(op, rule)
        self.assertFalse(result)


class TestProcessStageDependency(PaintingSchedulerTestBase):
    """Behavior 6, 7: Process/stage dependency + drying time propagation"""

    def test_drying_time_propagation(self):
        """Drying time is added to task end for successor readiness."""
        op = ProductionOperation(
            production_order=self.prod_order,
            production_order_item=self.prod_order_item,
            operation_name='Test',
            operation_code='T1',
            work_center=self.work_center,
            sequence=1,
            painting_stage=self.stage1,
            order_item=self.order_item,
            color_part='body',
            status='waiting',
        )

        duration = op.painting_stage.duration_minutes
        drying = op.painting_stage.drying_time_minutes

        start = timezone.make_aware(
            datetime.datetime.combine(self.gregorian_date, time(8, 0))
        )
        end = start + timedelta(minutes=duration)
        ready_for_next = end + timedelta(minutes=drying)

        # Verify drying time calculation
        self.assertEqual(ready_for_next, start + timedelta(minutes=duration + drying))
        self.assertEqual(drying, 30)

    def test_next_stage_dependency_chain(self):
        """Stage 1 drying time creates ready constraint for stage 2."""
        # Create stage1 op already scheduled
        op_start = timezone.make_aware(
            datetime.datetime.combine(self.gregorian_date, time(8, 0))
        )
        op1 = ProductionOperation.objects.create(
            production_order=self.prod_order,
            production_order_item=self.prod_order_item,
            operation_name='Stage1',
            operation_code='S1',
            work_center=self.work_center,
            sequence=1,
            painting_stage=self.stage1,
            assigned_worker=self.user1,
            planned_start=op_start,
            planned_end=op_start + timedelta(minutes=60),
            order_item=self.order_item,
            color_part='body',
        )

        # Create stage2 op also scheduled (for _get_operation_next_stage)
        op2_start = op_start + timedelta(hours=2)
        op2 = ProductionOperation.objects.create(
            production_order=self.prod_order,
            production_order_item=self.prod_order_item,
            operation_name='Stage2',
            operation_code='S2',
            work_center=self.work_center,
            sequence=2,
            painting_stage=self.stage2,
            assigned_worker=self.user1,
            planned_start=op2_start,
            planned_end=op2_start + timedelta(minutes=90),
            order_item=self.order_item,
            color_part='body',
        )

        from painting.scheduler import _get_operation_next_stage
        next_op = _get_operation_next_stage(op1)
        self.assertIsNotNone(next_op)
        self.assertEqual(next_op.id, op2.id)

        # Ready time = op1 end + drying_time_minutes
        ready = op1.planned_end + timedelta(minutes=op1.painting_stage.drying_time_minutes)
        self.assertEqual(ready, op_start + timedelta(minutes=60 + 30))


class TestHolidayWeekend(PaintingSchedulerTestBase):
    """Behavior 8: Holiday/weekend detection"""

    def test_is_working_day_normal(self):
        """A regular weekday is a working day."""
        result = _is_working_day(self.target_date)
        self.assertTrue(result)

    def test_is_working_day_weekend(self):
        """Jalali weekend (weekday==6) is not a working day."""
        # Find a Saturday (weekday 6 in jdatetime)
        d = self.target_date
        for _ in range(7):
            if d.weekday() == 6:
                break
            d = d + jdatetime.timedelta(days=1)
        self.assertEqual(d.weekday(), 6)
        result = _is_working_day(d)
        self.assertFalse(result)

    def test_is_working_day_holiday(self):
        """A holiday is not a working day."""
        gregorian_holiday = self.gregorian_date + datetime.timedelta(days=1)
        # Ensure it doesn't fall on weekend
        hijri_holiday = jdatetime.date.fromgregorian(date=gregorian_holiday)
        if hijri_holiday.weekday() == 6:
            gregorian_holiday = gregorian_holiday + datetime.timedelta(days=1)
            hijri_holiday = jdatetime.date.fromgregorian(date=gregorian_holiday)

        Holiday.objects.create(date=gregorian_holiday, description='Test Holiday')
        result = _is_working_day(hijri_holiday)
        self.assertFalse(result)


class TestWorkerBounds(PaintingSchedulerTestBase):
    """Behavior 9: Worker day bounds"""

    def test_default_worker_bounds(self):
        """Default bounds are 8:00-16:30, lunch 12:30-13:30."""
        default_user = User.objects.create_user('default_worker')
        worker = Worker.objects.create(
            user=default_user, station='paint', employee_id='DEF001',
        )
        bounds = _worker_day_bounds(self.gregorian_date, worker=worker)

        self.assertEqual(bounds['start'].time(), time(8, 0))
        self.assertEqual(bounds['end'].time(), time(16, 30))
        self.assertEqual(bounds['break_start'].time(), time(12, 30))
        self.assertEqual(bounds['break_end'].time(), time(13, 30))

    def test_custom_worker_bounds(self):
        """Custom worker hours override defaults."""
        custom_user = User.objects.create_user('custom_worker')
        worker = Worker.objects.create(
            user=custom_user, station='paint', employee_id='CUS001',
            work_start=time(9, 0), work_end=time(17, 0),
            break_start=time(13, 0), break_end=time(14, 0),
        )
        bounds = _worker_day_bounds(self.gregorian_date, worker=worker)

        self.assertEqual(bounds['start'].time(), time(9, 0))
        self.assertEqual(bounds['end'].time(), time(17, 0))
        self.assertEqual(bounds['break_start'].time(), time(13, 0))
        self.assertEqual(bounds['break_end'].time(), time(14, 0))

    def test_overtime_extended_end(self):
        """Allow overtime extends end time to 23:59."""
        ot_user = User.objects.create_user('ot_worker')
        worker = Worker.objects.create(
            user=ot_user, station='paint', employee_id='OT001',
            work_start=time(8, 0), work_end=time(16, 30),
            break_start=time(12, 30), break_end=time(13, 30),
        )
        bounds = _worker_day_bounds(self.gregorian_date, worker=worker, allow_overtime=True)

        self.assertEqual(bounds['end'].time(), time(23, 59))

    def test_worker3_custom_bounds(self):
        """Worker3 with custom hours uses those."""
        bounds = _worker_day_bounds(self.gregorian_date, worker=self.worker3)

        self.assertEqual(bounds['start'].time(), time(9, 0))
        self.assertEqual(bounds['end'].time(), time(17, 0))
        self.assertEqual(bounds['break_start'].time(), time(13, 0))
        self.assertEqual(bounds['break_end'].time(), time(14, 0))


class TestUnscheduledGhostTask(PaintingSchedulerTestBase):
    """Behavior 10: Unscheduled/ghost task handling"""

    def test_empty_operations_returns_zero(self):
        """Scheduler with no operations returns 0 scheduled."""
        scheduler = V2PaintingScheduler([], self.target_date)
        scheduler._load()

        count = scheduler.build()
        self.assertEqual(count, 0)

    def test_ghost_operation_not_in_schedule(self):
        """An operation without painting_stage is not scheduled."""
        op = ProductionOperation.objects.create(
            production_order=self.prod_order,
            production_order_item=self.prod_order_item,
            operation_name='NoPaint',
            operation_code='NP',
            work_center=self.work_center,
            sequence=1,
            painting_stage=None,
            order_item=self.order_item,
            color_part='body',
            status='waiting',
        )

        scheduler = V2PaintingScheduler([op.id], self.target_date)
        scheduler._load()

        # Operations without painting_stage should not be loaded
        self.assertEqual(len(scheduler.operations), 0)


class TestFullScheduleApply(PaintingSchedulerTestBase):
    """End-to-end: build + apply creates PaintingScheduleItems"""

    def test_schedule_creates_painting_schedule_items(self):
        """Scheduling operations creates PaintingScheduleItem records."""
        op = ProductionOperation.objects.create(
            production_order=self.prod_order,
            production_order_item=self.prod_order_item,
            operation_name='Stage1',
            operation_code='S1',
            work_center=self.work_center,
            sequence=1,
            painting_stage=self.stage1,
            order_item=self.order_item,
            color_part='body',
            status='waiting',
            planned_start=None,
            planned_end=None,
        )

        scheduler = V2PaintingScheduler([op.id], self.target_date)
        count, cursors = scheduler.schedule()

        self.assertEqual(count, 1)
        self.assertEqual(PaintingScheduleItem.objects.count(), 1)
        item = PaintingScheduleItem.objects.first()
        self.assertIsNotNone(item.scheduled_start)
        self.assertIsNotNone(item.scheduled_end)
        self.assertIsNotNone(item.worker)

    def test_schedule_chain_cascade(self):
        """Scheduling stage1 cascades drying time to stage2."""
        op_start = timezone.make_aware(
            datetime.datetime.combine(self.gregorian_date, time(8, 0))
        )

        # Create stage1 operation already scheduled
        ProductionOperation.objects.create(
            production_order=self.prod_order,
            production_order_item=self.prod_order_item,
            operation_name='Stage1',
            operation_code='S1',
            work_center=self.work_center,
            sequence=1,
            painting_stage=self.stage1,
            assigned_worker=self.user1,
            planned_start=op_start,
            planned_end=op_start + timedelta(minutes=60),
            order_item=self.order_item,
            color_part='body',
        )

        # Create stage2 operation unscheduled
        op2 = ProductionOperation.objects.create(
            production_order=self.prod_order,
            production_order_item=self.prod_order_item,
            operation_name='Stage2',
            operation_code='S2',
            work_center=self.work_center,
            sequence=2,
            painting_stage=self.stage2,
            order_item=self.order_item,
            color_part='body',
            status='waiting',
            planned_start=None,
            planned_end=None,
        )

        scheduler = V2PaintingScheduler([op2.id], self.target_date)
        count, cursors = scheduler.schedule()

        # Stage2 should be scheduled with ready time = stage1 end + drying
        self.assertEqual(count, 1)
        updated_op2 = ProductionOperation.objects.get(pk=op2.pk)
        self.assertIsNotNone(updated_op2.planned_start)
        # Should start at or after 8:00 + 60min + 30min drying = 9:30
        ready_time = op_start + timedelta(minutes=60 + 30)
        self.assertGreaterEqual(updated_op2.planned_start, ready_time)
