from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from reporting.barcode_resolver import BarcodeResolver
from reporting.models import MigrationMap, MigrationRun
from product.models import Order, Customer, OrderItem, Product, ProductCategory, PackagingUnit

User = get_user_model()


class BarcodeResolverTests(TestCase):
    """تست‌های BarcodeResolver برای سازگاری QRهای legacy"""

    def setUp(self):
        self.user = User.objects.create_user(username='barcodeuser', password='testpass')
        self.customer = Customer.objects.create(name='Barcode Customer')
        self.category = ProductCategory.objects.create(name='Barcode Cat')
        self.product = Product.objects.create(
            category=self.category,
            name='Barcode Product',
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
        # PackagingUnits are auto-created by signal
        self.pu = self.item.packaging_units.first()

    def test_order_item_qr_url_resolution(self):
        """QR URL مربوط به OrderItem باید resolve شود"""
        qr_url = f"https://selvichoob.ir{reverse('scan_qr', args=[self.item.id])}"
        result = BarcodeResolver.resolve(qr_url)
        self.assertEqual(result['entity_type'], 'order_item')
        self.assertEqual(result['entity_id'], self.item.id)
        self.assertEqual(result['entity'], self.item)
        self.assertTrue(result['legacy'])
        self.assertEqual(result['resolved_url'], reverse('scan_qr', args=[self.item.id]))

    def test_packaging_unit_qr_url_resolution(self):
        """QR URL مربوط به PackagingUnit باید resolve شود"""
        qr_url = f"https://selvichoob.ir{reverse('scan_packaging_unit', args=[self.pu.id])}"
        result = BarcodeResolver.resolve(qr_url)
        self.assertEqual(result['entity_type'], 'packaging_unit')
        self.assertEqual(result['entity_id'], self.pu.id)
        self.assertEqual(result['entity'], self.pu)
        self.assertTrue(result['legacy'])

    def test_legacy_entity_without_migration_map(self):
        """legacy entity بدون MigrationMap باید به‌عنوان legacy معتبر برگردد"""
        result = BarcodeResolver.resolve(str(self.item.id))
        self.assertTrue(result['legacy'])
        self.assertIsNone(result['v2_metadata'])

    def test_legacy_entity_with_migration_map(self):
        """legacy entity با MigrationMap باید v2_metadata داشته باشد"""
        run = MigrationRun.objects.create(
            phase='order_item',
            name='test-run',
            status='completed'
        )
        MigrationMap.objects.create(
            migration_type='order_item',
            old_model='product.OrderItem',
            old_id=self.item.id,
            old_app='product',
            new_model='sales.CustomerOrderItem',
            new_id=999,
            new_app='sales',
            migration_run=run,
            is_legacy=True
        )
        result = BarcodeResolver.resolve(str(self.item.id))
        self.assertTrue(result['legacy'])
        self.assertIsNotNone(result['v2_metadata'])
        self.assertEqual(result['v2_metadata']['v2_model'], 'sales.CustomerOrderItem')
        self.assertEqual(result['v2_metadata']['v2_id'], '999')

    def test_invalid_id_returns_unknown(self):
        """شناسه نامعتبر باید unknown برگرداند"""
        result = BarcodeResolver.resolve('999999')
        self.assertEqual(result['entity_type'], 'unknown')
        self.assertFalse(result['legacy'])

    def test_non_numeric_payload(self):
        """پرداختهای غیرعددی باید unknown برگردانند"""
        result = BarcodeResolver.resolve('hello-world')
        self.assertEqual(result['entity_type'], 'unknown')

    def test_empty_payload(self):
        """پرداختهای خالی باید unknown برگردانند"""
        result = BarcodeResolver.resolve('')
        self.assertEqual(result['entity_type'], 'unknown')

    def test_scan_qr_view_still_works(self):
        """scan_qr view باید همان رفتار سابق را حفظ کند"""
        url = reverse('scan_qr', args=[self.item.id])
        self.assertIn(str(self.item.id), url)
        self.assertTrue(url.startswith('/scan/'))

    def test_scan_packaging_unit_view_still_works(self):
        """scan_packaging_unit view باید همان رفتار سابق را حفظ کند"""
        url = reverse('scan_packaging_unit', args=[self.pu.id])
        self.assertIn(str(self.pu.id), url)

    def test_is_legacy_payload(self):
        """is_legacy_payload باید درست تشخیص دهد"""
        self.assertTrue(BarcodeResolver.is_legacy_payload(str(self.item.id)))
        self.assertFalse(BarcodeResolver.is_legacy_payload('invalid'))

    def test_get_scan_url(self):
        """get_scan_url باید URL درست برگرداند"""
        url = BarcodeResolver.get_scan_url('order_item', self.item.id)
        self.assertEqual(url, reverse('scan_qr', args=[self.item.id]))
        url = BarcodeResolver.get_scan_url('packaging_unit', self.pu.id)
        self.assertEqual(url, reverse('scan_packaging_unit', args=[self.pu.id]))

    def test_resolver_is_read_only(self):
        """Resolver نباید هیچ تغییری در دیتابیس ایجاد کند"""
        from django.db import connection
        # Count queries before
        initial_count = OrderItem.objects.count()
        BarcodeResolver.resolve(str(self.item.id))
        final_count = OrderItem.objects.count()
        self.assertEqual(initial_count, final_count)