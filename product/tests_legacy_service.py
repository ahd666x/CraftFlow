from django.test import TestCase, override_settings
from unittest.mock import patch
import jdatetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from product.models import (
    Order, Customer, OrderItem, Product, ProductCategory,
    ProductionTask, ProductionEvent, Material, Part, ProductBOM
)
from product.services import LegacyProductionService
from inventory.models import RawMaterialCategory, RawMaterial, StockMovement

User = get_user_model()


class LegacyProductionServiceTests(TestCase):
    """تست‌های LegacyProductionService"""

    def setUp(self):
        self.user = User.objects.create_user(username='serviceuser', password='testpass')
        self.customer = Customer.objects.create(name='Service Customer')
        self.category = ProductCategory.objects.create(name='Test Cat')
        self.product = Product.objects.create(
            category=self.category,
            name='Service Product',
            base_price=1000000
        )
        self.order = Order.objects.create(
            customer=self.customer,
            user=self.user,
            status='draft'
        )
        self.item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=2,
            unit_price=1000000
        )
        self.material = Material.objects.create(
            name='Service Material',
            thickness=16.0
        )
        cat = RawMaterialCategory.objects.create(name='Test RM Cat')
        raw = RawMaterial.objects.create(
            category=cat,
            name='Test Raw',
            unit='pcs',
            min_stock_alert=0
        )
        self.material.raw_material = raw
        self.material.save()

        self.part = Part.objects.create(
            material=self.material,
            name='Chain Part',
            length=100,
            width=50,
            f3='chain-barcode',
            routing_code='cut.cnc.mon.paint.packaging.shipping'
        )
        ProductBOM.objects.create(
            product=self.product,
            part=self.part,
            quantity=1
        )
        self.order.generate_tasks()
        self.task = self.order.tasks.first()

    def test_full_completion_transitions_to_done(self):
        """تکمیل کامل task باید status را به done تغییر دهد"""
        LegacyProductionService.complete_task(self.task, completed_quantity=self.task.quantity, actor=self.user)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'done')
        self.assertEqual(self.task.completed_quantity, self.task.quantity)

    def test_full_completion_sets_completed_at_jalali(self):
        """تکمیل کامل task باید completed_at جلالی تنظیم کند"""
        LegacyProductionService.complete_task(self.task, completed_quantity=self.task.quantity, actor=self.user)
        self.task.refresh_from_db()
        self.assertEqual(self.task.completed_at, jdatetime.date.today())

    def test_partial_completion_does_not_transition_to_done(self):
        """تکمیل جزئی نباید status را به done تغییر دهد"""
        LegacyProductionService.complete_task(self.task, completed_quantity=1, actor=self.user)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'pending')
        self.assertEqual(self.task.completed_quantity, 1)

    def test_partial_completion_sets_scanned_by(self):
        """تکمیل جزئی scanned_by را تنظیم می‌کند"""
        LegacyProductionService.complete_task(self.task, completed_quantity=1, actor=self.user)
        self.task.refresh_from_db()
        self.assertEqual(self.task.scanned_by, self.user)

    def test_no_duplicate_consumption_on_repeated_calls(self):
        """فراخوانی تکراری سرویس نباید مصرف تکراری ثبت کند"""
        LegacyProductionService.complete_task(self.task, completed_quantity=self.task.quantity, actor=self.user)
        count_before = StockMovement.objects.filter(
            reference_task=self.task,
            movement_type='consumption'
        ).count()
        self.assertEqual(count_before, 1)

        # Second call - task already done, should be idempotent
        LegacyProductionService.complete_task(self.task, completed_quantity=self.task.quantity, actor=self.user)
        count_after = StockMovement.objects.filter(
            reference_task=self.task,
            movement_type='consumption'
        ).count()
        self.assertEqual(count_after, 1)

    def test_creates_production_event(self):
        """تکمیل task باید ProductionEvent درست ایجاد کند"""
        LegacyProductionService.complete_task(self.task, completed_quantity=self.task.quantity, actor=self.user)
        events = ProductionEvent.objects.filter(task=self.task, event_type='done')
        self.assertTrue(events.exists())
        event = events.first()
        self.assertEqual(event.new_status, 'done')
        self.assertEqual(event.quantity, self.task.quantity)

    def test_legacy_next_step_activation(self):
        """تکمیل task باید مرحله بعدی legacy را فعال کند"""
        # Create a fresh order for this test to avoid setUp tasks
        fresh_customer = Customer.objects.create(name='Chain Customer')
        fresh_order = Order.objects.create(
            customer=fresh_customer,
            user=self.user,
            status='draft'
        )
        fresh_item = OrderItem.objects.create(
            order=fresh_order,
            product=self.product,
            quantity=1,
            unit_price=1000000
        )
        fresh_order.generate_tasks()
        tasks = list(fresh_order.tasks.order_by('step_order'))
        first_task = tasks[0]
        second_task = tasks[1]

        self.assertEqual(second_task.status, 'waiting')
        LegacyProductionService.complete_task(first_task, completed_quantity=first_task.quantity, actor=self.user)
        second_task.refresh_from_db()
        self.assertEqual(second_task.status, 'pending')

    def test_order_status_update(self):
        """تکمیل task باید وضعیت Order را به‌روز کند"""
        self.order.status = 'draft'
        self.order.save()
        LegacyProductionService.complete_task(self.task, completed_quantity=self.task.quantity, actor=self.user)
        self.order.refresh_from_db()
        # With only 1 task, order should become 'producing' or 'completed'
        self.assertIn(self.order.status, ['producing', 'completed'])

    def test_rollback_on_consumption_error(self):
        """خطای مصرف ماده باید باعث rollback کامل شود"""
        with patch('product.services.consume_material_for_task') as mock_consume:
            mock_consume.side_effect = Exception("consumption error")
            with self.assertRaises(Exception):
                LegacyProductionService.complete_task(self.task, completed_quantity=self.task.quantity, actor=self.user)
        
        # Task should not be marked as done
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'pending')

    def test_idempotent_when_already_done(self):
        """فراخوانی سرویس روی task already done باید idempotent باشد"""
        LegacyProductionService.complete_task(self.task, completed_quantity=self.task.quantity, actor=self.user)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'done')

        # Call again
        LegacyProductionService.complete_task(self.task, completed_quantity=self.task.quantity, actor=self.user)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'done')
        
        # Should not create duplicate events
        events = ProductionEvent.objects.filter(task=self.task, event_type='done')
        self.assertEqual(events.count(), 1)

    def test_bulk_completion_via_service(self):
        """تکمیل چندین task از طریق سرویس"""
        tasks = list(self.order.tasks.all())
        for task in tasks:
            LegacyProductionService.complete_task(task, completed_quantity=task.quantity, actor=self.user)
        
        for task in tasks:
            task.refresh_from_db()
            self.assertEqual(task.status, 'done')
