"""Phase 9 tests: QualityService, EventService, AuditService, Selectors."""

import json

from datetime import timedelta

import jdatetime
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from django.contrib.auth.models import User

from accounts.models import Worker, Holiday
from production.models import ProductionOrder, ProductionOperation, ProductionOrderItem
from planning.models import Routing, WorkCenter
from sales.models import Customer, CustomerOrder, CustomerOrderItem
from products.models import ProductCategory, Product, ProductPart
from bom.models import BOM

from quality.models import QualityInspection, QualityDefect, ReworkOrder
from quality.services import QualityService
from quality.selectors import QualitySelectors

from reporting.models import BusinessEvent, AuditLog, MigrationMap
from reporting.services import EventService, AuditService
from reporting.selectors import ReportingSelectors


def find_next_working_day(start_jalali):
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


class Phase9TestBase(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user('tester', first_name='تست', last_name='کننده')
        self.inspector = User.objects.create_user('inspector', first_name='بازرس', last_name='۱')

        self.category = ProductCategory.objects.create(name='Test Cat')
        self.product = Product.objects.create(
            category=self.category, name='محصول تست', code='PROD_P9',
            base_price=1000000,
        )

        self.customer = Customer.objects.create(name='مشتری تست P9')
        self.order = CustomerOrder.objects.create(
            customer=self.customer, order_date='2024-01-01'
        )
        self.order_item = CustomerOrderItem.objects.create(
            order=self.order, product=self.product, quantity=100
        )

        self.work_center = WorkCenter.objects.create(code='WC_P9', name='WC Test')
        self.routing = Routing.objects.create(
            product=self.product, revision='A', name='Test Routing',
            effective_date='2024-01-01', status='active',
        )
        self.bom = BOM.objects.create(
            product=self.product, revision='A', effective_date='2024-01-01',
        )

        self.prod_order = ProductionOrder.objects.create(
            order=self.order, order_number='PO_P9_001',
            routing=self.routing, bom_revision='A', status='planned',
        )
        self.prod_order_item = ProductionOrderItem.objects.create(
            production_order=self.prod_order,
            customer_order_item=self.order_item,
            product=self.product, quantity=100,
            bom=self.bom, routing=self.routing,
        )
        self.target_date = find_next_working_day(jdatetime.date.today())
        self.gregorian_date = self.target_date.togregorian()

        self.operation = ProductionOperation.objects.create(
            production_order=self.prod_order,
            production_order_item=self.prod_order_item,
            operation_name='Painting',
            operation_code='PNT',
            work_center=self.work_center,
            sequence=1,
            status='in_progress',
        )


class TestQualityService(Phase9TestBase):
    """Tests for QualityService mutations."""

    def test_create_inspection_generates_unique_number(self):
        """create_inspection generates a unique inspection number."""
        inspection = QualityService.create_inspection(
            production_order=self.prod_order,
            inspection_type='in_process',
            result='pass',
            inspected_by=self.inspector,
            notes='Initial inspection',
        )

        self.assertIsNotNone(inspection.pk)
        self.assertEqual(inspection.result, 'pass')
        self.assertEqual(inspection.production_order, self.prod_order)
        self.assertTrue(inspection.inspection_number.startswith('QI-'))

        # Second inspection should have different number
        inspection2 = QualityService.create_inspection(
            production_order=self.prod_order,
            inspection_type='final',
            result='fail',
            inspected_by=self.inspector,
        )
        self.assertNotEqual(inspection.inspection_number, inspection2.inspection_number)

    def test_add_defect_creates_defect_with_inspection_fk(self):
        """add_defect creates QualityDefect linked to inspection."""
        inspection = QualityService.create_inspection(
            production_order=self.prod_order,
            inspection_type='in_process',
            result='fail',
            inspected_by=self.inspector,
        )

        defect = QualityService.add_defect(
            inspection=inspection,
            code='CRACK-001',
            description='شکاف در سطح',
            severity='major',
            quantity=5,
            is_reworkable=True,
        )

        self.assertEqual(defect.quality_inspection, inspection)
        self.assertEqual(defect.code, 'CRACK-001')
        self.assertEqual(defect.severity, 'major')
        self.assertEqual(defect.quantity, 5)

    def test_create_rework_order_links_inspection_and_operation(self):
        """create_rework_order links quality inspection and production operation."""
        inspection = QualityService.create_inspection(
            production_order=self.prod_order,
            inspection_type='in_process',
            result='fail',
            inspected_by=self.inspector,
        )

        rework = QualityService.create_rework_order(
            production_order=self.prod_order,
            production_operation=self.operation,
            quality_inspection=inspection,
            defect_description='رنگ پرچ‌کرده',
            repair_description='رنگ‌آمی مجدد',
            quantity=3,
            assigned_to=None,
        )

        self.assertEqual(rework.quality_inspection, inspection)
        self.assertEqual(rework.production_operation, self.operation)
        self.assertEqual(rework.quantity, 3)
        self.assertEqual(rework.status, 'draft')

    def test_complete_rework_validates_quantity(self):
        """complete_rework raises ValueError if completed_quantity > quantity."""
        inspection = QualityService.create_inspection(
            production_order=self.prod_order,
            inspection_type='in_process',
            result='fail',
            inspected_by=self.inspector,
        )

        rework = QualityService.create_rework_order(
            production_order=self.prod_order,
            production_operation=self.operation,
            quality_inspection=inspection,
            defect_description='Test defect',
            repair_description='Test repair',
            quantity=5,
        )

        rework = QualityService.start_rework(rework, self.inspector)
        self.assertEqual(rework.status, 'in_progress')

        # Valid completion
        rework = QualityService.complete_rework(rework, self.inspector, 5)
        self.assertEqual(rework.completed_quantity, 5)
        self.assertEqual(rework.status, 'completed')

        # Over-completion should fail
        rework2 = QualityService.create_rework_order(
            production_order=self.prod_order,
            production_operation=self.operation,
            quality_inspection=inspection,
            defect_description='Test defect 2',
            repair_description='Test repair 2',
            quantity=3,
        )
        with self.assertRaises(ValueError):
            QualityService.complete_rework(rework2, self.inspector, 4)

    def test_inspection_creates_business_event(self):
        """Creating an inspection creates a BusinessEvent."""
        QualityService.create_inspection(
            production_order=self.prod_order,
            inspection_type='in_process',
            result='pass',
            inspected_by=self.inspector,
        )

        events = BusinessEvent.objects.filter(category='quality', event_type='created')
        self.assertEqual(events.count(), 1)


class TestEventService(Phase9TestBase):
    """Tests for EventService."""

    def test_log_event_with_content_object(self):
        """log_event creates BusinessEvent with GenericForeignKey."""
        event = EventService.log_event(
            category='production',
            event_type='started',
            title='Operation started',
            description='Painting operation started',
            user=self.user,
            content_object=self.operation,
            metadata={'stage': 'painting'},
        )

        self.assertEqual(event.category, 'production')
        self.assertEqual(event.event_type, 'started')
        self.assertEqual(event.created_by, self.user)
        self.assertEqual(event.content_object, self.operation)
        self.assertEqual(event.metadata, {'stage': 'painting'})

    def test_log_production_event(self):
        """log_production_event creates production event."""
        event = EventService.log_production_event(
            'completed', self.operation, user=self.user
        )

        self.assertEqual(event.category, 'production')
        self.assertEqual(event.event_type, 'completed')

    def test_log_quality_event(self):
        """log_quality_event creates quality event."""
        inspection = QualityService.create_inspection(
            production_order=self.prod_order,
            inspection_type='in_process',
            result='pass',
            inspected_by=self.inspector,
        )

        event = EventService.log_quality_event(
            'inspected', inspection, user=self.inspector
        )

        self.assertEqual(event.category, 'quality')
        self.assertEqual(event.event_type, 'inspected')

    def test_log_with_correlation(self):
        """log_with_correlation preserves correlation_id."""
        event = EventService.log_with_correlation(
            'corr-001', 'production', 'completed', 'Done',
            user=self.user, content_object=self.operation,
        )

        self.assertEqual(event.correlation_id, 'corr-001')


class TestAuditService(Phase9TestBase):
    """Tests for AuditService."""

    def test_log_create(self):
        """log_create creates CREATE audit entry."""
        audit = AuditService.log_create(
            user=self.user,
            model_name='ProductionOrder',
            instance=self.prod_order,
            changes={'status': 'planned'},
        )

        self.assertEqual(audit.action, 'create')
        self.assertEqual(audit.model_name, 'ProductionOrder')
        self.assertEqual(audit.object_id, str(self.prod_order.pk))
        self.assertEqual(audit.changes, {'status': 'planned'})

    def test_log_update(self):
        """log_update creates UPDATE audit entry."""
        audit = AuditService.log_update(
            user=self.user,
            model_name='ProductionOrder',
            instance=self.prod_order,
            changes={'status': {'old': 'planned', 'new': 'released'}},
        )

        self.assertEqual(audit.action, 'update')
        self.assertEqual(audit.changes, {'status': {'old': 'planned', 'new': 'released'}})

    def test_log_delete(self):
        """log_delete creates DELETE audit entry."""
        audit = AuditService.log_delete(
            user=self.user,
            model_name='ProductionOperation',
            object_repr=str(self.operation),
            object_id=self.operation.pk,
        )

        self.assertEqual(audit.action, 'delete')
        self.assertEqual(audit.object_id, str(self.operation.pk))

    def test_log_status_change(self):
        """log_status_change creates status change audit."""
        audit = AuditService.log_status_change(
            user=self.user,
            model_name='ProductionOperation',
            instance=self.operation,
            old_status='waiting',
            new_status='in_progress',
        )

        self.assertEqual(audit.action, 'update')
        self.assertEqual(audit.changes, {'old_status': 'waiting', 'new_status': 'in_progress'})

    def test_log_assignment(self):
        """log_assignment creates assignment audit."""
        worker = Worker.objects.create(
            user=User.objects.create_user('worker_p9'),
            station='paint', employee_id='W_P9',
        )
        audit = AuditService.log_assignment(
            user=self.user,
            model_name='ProductionOperation',
            instance=self.operation,
            old_worker=None,
            new_worker=worker,
        )

        self.assertEqual(audit.action, 'assign')
        self.assertIn('new_worker', audit.changes)


class TestQualitySelectors(Phase9TestBase):
    """Tests for QualitySelectors read-only query functions."""

    def test_get_inspections_for_order(self):
        """get_inspections_for_order filters by order and type."""
        QualityService.create_inspection(
            production_order=self.prod_order,
            inspection_type='in_process',
            result='pass',
            inspected_by=self.inspector,
        )
        QualityService.create_inspection(
            production_order=self.prod_order,
            inspection_type='final',
            result='fail',
            inspected_by=self.inspector,
        )

        results = QualitySelectors.get_inspections_for_order(self.prod_order, inspection_type='in_process')
        self.assertEqual(results.count(), 1)
        self.assertEqual(results.first().inspection_type, 'in_process')

    def test_get_inspection_with_defects(self):
        """get_inspection_with_defects prefetches defects."""
        inspection = QualityService.create_inspection(
            production_order=self.prod_order,
            inspection_type='in_process',
            result='fail',
            inspected_by=self.inspector,
        )
        QualityService.add_defect(inspection, 'D1', 'desc', 'minor', 2)
        QualityService.add_defect(inspection, 'D2', 'desc', 'major', 1)

        loaded = QualitySelectors.get_inspection_with_defects(inspection.pk)
        self.assertEqual(loaded.defects.count(), 2)

    def test_get_rework_orders_for_order(self):
        """get_rework_orders_for_order filters by status."""
        inspection = QualityService.create_inspection(
            production_order=self.prod_order,
            inspection_type='in_process',
            result='fail',
            inspected_by=self.inspector,
        )
        QualityService.create_rework_order(
            production_order=self.prod_order,
            production_operation=self.operation,
            quality_inspection=inspection,
            defect_description='d', repair_description='r', quantity=1,
        )

        results = QualitySelectors.get_rework_orders_for_order(self.prod_order, status='draft')
        self.assertEqual(results.count(), 1)

    def test_get_recent_inspections(self):
        """get_recent_inspections filters by date range."""
        QualityService.create_inspection(
            production_order=self.prod_order,
            inspection_type='in_process',
            result='pass',
            inspected_by=self.inspector,
        )

        results = QualitySelectors.get_recent_inspections(days=7)
        self.assertGreaterEqual(results.count(), 1)

    def test_get_defect_summary(self):
        """get_defect_summary aggregates defects by severity."""
        inspection = QualityService.create_inspection(
            production_order=self.prod_order,
            inspection_type='in_process',
            result='fail',
            inspected_by=self.inspector,
        )
        QualityService.add_defect(inspection, 'D1', 'minor defect', 'minor', 5)
        QualityService.add_defect(inspection, 'D2', 'major defect', 'major', 2)

        summary = QualitySelectors.get_defect_summary(self.prod_order)
        severities = {item['defects__severity'] for item in summary}
        self.assertIn('minor', severities)
        self.assertIn('major', severities)


class TestReportingSelectors(Phase9TestBase):
    """Tests for ReportingSelectors."""

    def test_get_business_events_filters(self):
        """get_business_events filters by category."""
        EventService.log_production_event('started', self.operation, user=self.user)
        EventService.log_quality_event('inspected', None, user=self.user) if False else None

        events = ReportingSelectors.get_business_events(category='production')
        self.assertGreaterEqual(events.count(), 1)

    def test_get_audit_logs_filters(self):
        """get_audit_logs filters by user."""
        AuditService.log_create(
            user=self.user,
            model_name='ProductionOrder',
            instance=self.prod_order,
        )

        logs = ReportingSelectors.get_audit_logs(user=self.user)
        self.assertGreaterEqual(logs.count(), 1)

    def test_get_migration_stats(self):
        """get_migration_stats returns aggregate stats."""
        stats = ReportingSelectors.get_migration_stats()
        self.assertIn('total_runs', stats)
        self.assertIn('completed', stats)

    def test_get_legacy_mappings(self):
        """get_legacy_mappings returns is_legacy=True mappings."""
        MigrationMap.objects.create(
            migration_type='product',
            old_id='1',
            new_id='100',
            is_legacy=True,
            old_app='product',
            old_model='Product',
            new_app='products',
            new_model='Product',
        )

        mappings = ReportingSelectors.get_legacy_mappings()
        self.assertEqual(mappings.count(), 1)
