from django.test import TestCase
from django.contrib.auth import get_user_model
from decimal import Decimal

User = get_user_model()


class V2ModelsTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')

    def test_customer_creation(self):
        from customers.models import Customer, CustomerGroup
        group = CustomerGroup.objects.create(name='Test Group')
        customer = Customer.objects.create(
            name='Test Customer',
            group=group,
            phone='09123456789'
        )
        self.assertEqual(customer.name, 'Test Customer')
        self.assertEqual(customer.group.name, 'Test Group')

    def test_product_creation(self):
        from products.models import ProductCategory, Product
        category = ProductCategory.objects.create(name='Test Category')
        product = Product.objects.create(
            category=category,
            name='Test Product',
            base_price=1000000
        )
        self.assertEqual(product.name, 'Test Product')
        self.assertEqual(product.category.name, 'Test Category')

    def test_item_creation(self):
        from inventory.models import ItemCategory, UOM, Item
        category = ItemCategory.objects.create(name='Test Category')
        uom = UOM.objects.create(code='kg', name='کیلوگرم', uom_type='weight')
        item = Item.objects.create(
            category=category,
            code='TEST-001',
            name='Test Item',
            uom=uom,
            item_type='material'
        )
        self.assertEqual(item.code, 'TEST-001')
        self.assertEqual(item.uom.code, 'kg')

    def test_production_order_creation(self):
        from sales.models import Customer, CustomerOrder
        from production.models import ProductionOrder
        from planning.models import Routing, WorkCenter
        from products.models import ProductCategory, Product
        customer = Customer.objects.create(name='Test Customer')
        order = CustomerOrder.objects.create(
            customer=customer,
            order_date='2024-01-01'
        )
        category = ProductCategory.objects.create(name='Test Category')
        product = Product.objects.create(category=category, name='Test Product')
        wc = WorkCenter.objects.create(code='WC-01', name='Test WorkCenter')
        routing = Routing.objects.create(
            product=product,
            revision='A',
            name='Test Routing',
            effective_date='2024-01-01'
        )
        po = ProductionOrder.objects.create(
            order=order,
            routing=routing,
            order_number='PO-001',
            status='draft'
        )
        self.assertEqual(po.order_number, 'PO-001')
        self.assertEqual(po.status, 'draft')

    def test_stock_balance_creation(self):
        from inventory.models import ItemCategory, UOM, Item, StockLocation, StockBalance
        category = ItemCategory.objects.create(name='Test Category')
        uom = UOM.objects.create(code='pcs', name='عدد', uom_type='count')
        item = Item.objects.create(
            category=category,
            code='STOCK-001',
            name='Stock Item',
            uom=uom,
            item_type='material'
        )
        location = StockLocation.objects.create(
            code='WH-01',
            name='انبار اصلی',
            location_type='warehouse'
        )
        balance = StockBalance.objects.create(
            item=item,
            location=location,
            quantity_on_hand=Decimal('100.000'),
            quantity_reserved=Decimal('10.000'),
            quantity_available=Decimal('90.000')
        )
        self.assertEqual(balance.quantity_on_hand, Decimal('100.000'))
        self.assertEqual(balance.quantity_available, Decimal('90.000'))
