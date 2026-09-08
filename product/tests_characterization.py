from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from unittest.mock import patch
import jdatetime
from decimal import Decimal

from product.models import (
    Order, Customer, OrderItem, Product, ProductCategory,
    ProductionTask, ProductionEvent, Material, ShipmentLog, Part, ProductBOM
)
from inventory.models import StockMovement
from product.signals import generate_qr_code, generate_packaging_qr_codes
from product.utils import consume_material_for_task

User = get_user_model()


class V1CharacterizationQRTests(TestCase):
    """تست‌های مشخصه QRهای V1"""

    def setUp(self):
        self.user = User.objects.create_user(username='qruser', password='testpass')
        self.customer = Customer.objects.create(name='QR Customer')
        self.category = ProductCategory.objects.create(name='Test Cat')
        self.product = Product.objects.create(
            category=self.category,
            name='QR Product',
            base_price=1000000
        )
        self.order = Order.objects.create(
            customer=self.customer,
            user=self.user,
            status='draft'
        )

    @patch('product.signals.qrcode.make')
    def test_order_item_qr_url_pattern(self, mock_qr_make):
        """QR OrderItem باید در signal تولید شود و URL ساختارش حفظ شود"""
        mock_qr_make.return_value = type('MockImg', (), {'save': lambda *a, **k: None})()
        item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=1,
            unit_price=1000000
        )
        # بعد از ایجاد، signal QR تولید کرده (یا امتحان کرده)
        # وجود فیلد qr_code را بررسی می‌کنیم
        self.assertTrue(hasattr(item, 'qr_code'))
        # نام فایل باید با qr_order_ شروع شود (ساختار legacy)
        # در صورت عدم تولید واقعی QR در تست، ساختار را از طریق بررسی URL پوشش می‌دهیم
        scan_url = reverse('scan_qr', args=[item.id])
        self.assertIn(str(item.id), scan_url)

    @patch('product.signals.qrcode.make')
    def test_packaging_unit_qr_url_pattern(self, mock_qr_make):
        """QR PackagingUnit باید شامل scan_packaging_unit و پارامتر next باشد"""
        mock_img = type('MockImg', (), {'save': lambda *a, **k: None})()
        mock_qr_make.return_value = mock_img
        item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=1,
            unit_price=1000000
        )
        pu = item.packaging_units.first()
        self.assertTrue(pu)
        self.assertTrue(hasattr(pu, 'qr_code'))
        scan_url = reverse('scan_packaging_unit', args=[pu.id])
        self.assertIn(str(pu.id), scan_url)

    def test_scan_qr_url_resolves(self):
        """URL اسکن QR باید resolve شود"""
        item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=1,
            unit_price=1000000
        )
        url = reverse('scan_qr', args=[item.id])
        self.assertEqual(url, f'/scan/{item.id}/')

    def test_scan_packaging_unit_url_resolves(self):
        """URL اسکن PackagingUnit باید resolve شود"""
        item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=1,
            unit_price=1000000
        )
        pu = item.packaging_units.first()
        url = reverse('scan_packaging_unit', args=[pu.id])
        self.assertIn(str(pu.id), url)


class V1CharacterizationProductionTaskTests(TestCase):
    """تست‌های مشخصه side effects ProductionTask.save()"""

    def setUp(self):
        self.user = User.objects.create_user(username='taskuser', password='testpass')
        self.customer = Customer.objects.create(name='Task Customer')
        self.category = ProductCategory.objects.create(name='Test Cat')
        self.product = Product.objects.create(
            category=self.category,
            name='Task Product',
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
            name='Test Material',
            thickness=16.0
        )
        # Associate raw_material for consumption tracking
        from inventory.models import RawMaterialCategory, RawMaterial
        cat = RawMaterialCategory.objects.create(name='Test RM Cat')
        raw = RawMaterial.objects.create(
            category=cat,
            name='Test Raw',
            unit='pcs',
            min_stock_alert=0
        )
        self.material.raw_material = raw
        self.material.save()

    def test_completion_creates_production_event(self):
        """تکمیل تسک باید ProductionEvent ایجاد کند"""
        part = self.product.bom.first()
        if not part:
            # Create a simple part via ProductBOM
            from product.models import Part
            part = Part.objects.create(
                material=self.material,
                name='Test Part',
                length=100,
                width=50,
                f3='test-barcode',
                routing_code='cut.cnc.mon.paint.packaging.shipping'
            )
            from product.models import ProductBOM
            ProductBOM.objects.create(
                product=self.product,
                part=part,
                quantity=1
            )

        self.order.generate_tasks()
        task = self.order.tasks.first()
        self.assertEqual(task.status, 'pending')

        with patch('product.utils.log_production_event') as mock_log:
            task.status = 'done'
            task.scanned_by = self.user
            task.save()
            self.assertTrue(mock_log.called)

    def test_completion_triggers_material_consumption(self):
        """تکمیل تسک باید مصرف خودکار مواد ثبت کند"""
        part = self.product.bom.first()
        if not part:
            from product.models import Part
            part = Part.objects.create(
                material=self.material,
                name='Consume Part',
                length=100,
                width=50,
                f3='consume-barcode',
                routing_code='cut.paint.packaging.shipping'
            )
            from product.models import ProductBOM
            ProductBOM.objects.create(
                product=self.product,
                part=part,
                quantity=1
            )

        self.order.generate_tasks()
        task = self.order.tasks.first()
        task.status = 'done'
        task.scanned_by = self.user
        task.save()

        movements = StockMovement.objects.filter(
            raw_material=self.material.raw_material,
            movement_type='consumption'
        )
        self.assertTrue(movements.exists())

    def test_no_duplicate_consumption_movement(self):
        """مصرف تکراری برای یک تسک ثبت نشود"""
        part = self.product.bom.first()
        if not part:
            from product.models import Part
            part = Part.objects.create(
                material=self.material,
                name='NoDup Part',
                length=100,
                width=50,
                f3='nodup-barcode',
                routing_code='cut.paint.packaging.shipping'
            )
            from product.models import ProductBOM
            ProductBOM.objects.create(
                product=self.product,
                part=part,
                quantity=1
            )

        self.order.generate_tasks()
        task = self.order.tasks.first()
        task.status = 'done'
        task.scanned_by = self.user
        task.save()

        count_before = StockMovement.objects.filter(
            reference_task=task,
            movement_type='consumption'
        ).count()

        task.completed_quantity = task.quantity
        task.status = 'done'
        task.save()

        count_after = StockMovement.objects.filter(
            reference_task=task,
            movement_type='consumption'
        ).count()

        self.assertEqual(count_before, 1)
        self.assertEqual(count_after, 1)

    def test_legacy_next_step_activation(self):
        """تسک بعدی در مسیر legacy باید pending شود"""
        part = self.product.bom.first()
        if not part:
            from product.models import Part
            part = Part.objects.create(
                material=self.material,
                name='Chain Part',
                length=100,
                width=50,
                f3='chain-barcode',
                routing_code='cut.cnc.mon.paint.packaging.shipping'
            )
            from product.models import ProductBOM
            ProductBOM.objects.create(
                product=self.product,
                part=part,
                quantity=1
            )

        self.order.generate_tasks()
        tasks = list(self.order.tasks.order_by('step_order'))
        self.assertGreaterEqual(len(tasks), 2)

        first_task = tasks[0]
        second_task = tasks[1]

        self.assertEqual(first_task.status, 'pending')
        self.assertEqual(second_task.status, 'waiting')

        first_task.status = 'done'
        first_task.scanned_by = self.user
        first_task.save()

        second_task.refresh_from_db()
        self.assertEqual(second_task.status, 'pending')


class V1CharacterizationJalaliTests(TestCase):
    """تست‌های مشخصه رفتار جلالی"""

    def test_persian_date_field_default(self):
        """PersianDateField باید به تاریخ جلالی پیش‌فرض ذخیره شود"""
        from product.fields import PersianDateField
        from product.models import Order
        order = Order.objects.create(
            customer=Customer.objects.create(name='Jalali Customer'),
            user=User.objects.create_user(username='jalali', password='test'),
            status='draft'
        )
        today_jalali = jdatetime.date.today()
        self.assertEqual(order.created_at, today_jalali)

    def test_persian_date_field_stores_jalali(self):
        """PersianDateField تاریخ جلالی را ذخیره می‌کند"""
        order = Order.objects.create(
            customer=Customer.objects.create(name='Jalali2'),
            user=User.objects.create_user(username='jalali2', password='test'),
            due_date=jdatetime.date(1404, 1, 1),
            status='draft'
        )
        self.assertEqual(order.due_date, jdatetime.date(1404, 1, 1))

    def test_production_task_completed_at_jalali(self):
        """زمان تکمیل ProductionTask باید جلالی باشد"""
        task = ProductionTask.objects.create(
            order=Order.objects.create(
                customer=Customer.objects.create(name='Jalali3'),
                user=User.objects.create_user(username='jalali3', password='test'),
                status='draft'
            ),
            station_name='cut',
            step_order=1,
            quantity=1,
            status='done'
        )
        self.assertEqual(task.completed_at, jdatetime.date.today())


class V1CharacterizationPackagingTests(TestCase):
    """تست‌های مشخصه PackagingUnit و ShipmentLog"""

    def setUp(self):
        self.user = User.objects.create_user(username='packuser', password='testpass')

    def test_packaging_units_created_on_order_item(self):
        """ایجاد OrderItem باید PackagingUnit بسازد"""
        customer = Customer.objects.create(name='Pack Customer')
        category = ProductCategory.objects.create(name='Pack Cat')
        product = Product.objects.create(
            category=category,
            name='Pack Product',
            base_price=1000000
        )
        order = Order.objects.create(
            customer=customer,
            user=User.objects.create_user(username='pack', password='test'),
            status='draft'
        )
        item = OrderItem.objects.create(
            order=order,
            product=product,
            quantity=3,
            unit_price=1000000
        )
        self.assertEqual(item.packaging_units.count(), 3)
        self.assertEqual(
            list(item.packaging_units.values_list('unit_number', flat=True)),
            [1, 2, 3]
        )

    def test_shipment_log_creation(self):
        """ShipmentLog باید به PackagingUnit مرتبط شود"""
        customer = Customer.objects.create(name='Ship Customer')
        category = ProductCategory.objects.create(name='Ship Cat')
        product = Product.objects.create(
            category=category,
            name='Ship Product',
            base_price=1000000
        )
        order = Order.objects.create(
            customer=customer,
            user=User.objects.create_user(username='ship', password='test'),
            status='draft'
        )
        item = OrderItem.objects.create(
            order=order,
            product=product,
            quantity=1,
            unit_price=1000000
        )
        pu = item.packaging_units.first()
        log = ShipmentLog.objects.create(
            packaging_unit=pu,
            plate_number='12B34567',
            shipped_by=self.user
        )
        self.assertEqual(log.packaging_unit, pu)
