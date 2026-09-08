from django.test import TestCase
from django.core.exceptions import ValidationError
from decimal import Decimal
from django.contrib.auth import get_user_model
from unittest.mock import patch

from production.models import ProductionOrder, ProductionOrderItem, ProductionOperation
from production.services import ProductionService
from planning.models import Routing, RoutingOperation, RoutingDependency, WorkCenter
from products.models import ProductCategory, Product, ProductPart
from sales.models import Customer, CustomerOrder, CustomerOrderItem
from bom.models import BOM
from inventory.models import ItemCategory, UOM, Item, StockLocation, StockBalance, StockLedger, StockReservation
from inventory.services import InventoryService
from warehouse.models import MaterialIssue, MaterialIssueItem, MaterialConsumption
from warehouse.services import WarehouseService

User = get_user_model()


class ProductionDependencyTests(TestCase):
    """تست‌های ProductionService.complete_operation با RoutingDependency"""

    def setUp(self):
        self.user = User.objects.create_user(username='produser', password='testpass')
        self.customer = Customer.objects.create(name='Dep Customer')
        self.order = CustomerOrder.objects.create(
            customer=self.customer,
            order_date='2024-01-01'
        )
        self.category = ProductCategory.objects.create(name='Test Cat')
        self.product = Product.objects.create(
            category=self.category,
            name='Dep Product',
            base_price=1000000
        )
        self.coi = CustomerOrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=1
        )
        self.wc = WorkCenter.objects.create(code='WC-01', name='Test WC')
        self.routing = Routing.objects.create(
            product=self.product,
            revision='A',
            name='Dep Routing',
            effective_date='2024-01-01'
        )
        RoutingOperation.objects.create(
            routing=self.routing,
            sequence=1,
            operation_name='Op1',
            operation_code='OP1',
            work_center=self.wc,
            run_time_per_unit_minutes=1
        )
        RoutingOperation.objects.create(
            routing=self.routing,
            sequence=2,
            operation_name='Op2',
            operation_code='OP2',
            work_center=self.wc,
            run_time_per_unit_minutes=1
        )
        self.po = ProductionOrder.objects.create(
            order=self.order,
            routing=self.routing,
            order_number='PO-DEP-001',
            status='draft'
        )
        self.bom = BOM.objects.create(
            product=self.product,
            revision='A',
            effective_date='2024-01-01',
            created_by=self.user
        )
        ProductPart.objects.create(
            product=self.product,
            name='Test Part',
            code='P-001',
            length=100,
            width=50,
            thickness=16
        )
        self.poi = ProductionOrderItem.objects.create(
            production_order=self.po,
            customer_order_item=self.coi,
            product=self.product,
            quantity=1,
            bom=self.bom,
            routing=self.routing
        )
        ProductionService.create_operations_for_order_item(self.poi)
        self.op1 = ProductionOperation.objects.get(production_order_item=self.poi, operation_code='OP1')
        self.op2 = ProductionOperation.objects.get(production_order_item=self.poi, operation_code='OP2')

    def test_no_dependency_no_auto_activation(self):
        """بدون RoutingDependency، operation بعدی خودکار ready نمی‌شود"""
        self.assertEqual(self.op2.status, 'waiting')
        ProductionService.complete_operation(self.op1, completed_quantity=1)
        self.op2.refresh_from_db()
        self.assertEqual(self.op2.status, 'waiting')

    def test_dependency_based_activation(self):
        """با RoutingDependency، operation بعدی فعال می‌شود"""
        RoutingDependency.objects.create(
            routing=self.routing,
            predecessor=RoutingOperation.objects.get(routing=self.routing, operation_code='OP1'),
            successor=RoutingOperation.objects.get(routing=self.routing, operation_code='OP2'),
            dependency_type='FS',
            is_active=True
        )
        self.assertEqual(self.op2.status, 'waiting')
        ProductionService.complete_operation(self.op1, completed_quantity=1)
        self.op2.refresh_from_db()
        self.assertEqual(self.op2.status, 'ready')

    def test_partial_completion_does_not_complete_without_force(self):
        """تکمیل جزئی بدون force_complete=False، operation را completed نمی‌کند"""
        ProductionService.complete_operation(self.op1, completed_quantity=0)
        self.op1.refresh_from_db()
        self.assertEqual(self.op1.status, 'waiting')

    def test_force_complete_partial(self):
        """force_complete=True، تکمیل جزئی را accepted می‌کند"""
        ProductionService.complete_operation(self.op1, completed_quantity=0, force_complete=True)
        self.op1.refresh_from_db()
        self.assertEqual(self.op1.status, 'completed')


class InventoryConcurrencyTests(TestCase):
    """تست‌های InventoryService با قفل‌گذاری و اعتبارسنجی"""

    def setUp(self):
        self.user = User.objects.create_user(username='invuser', password='testpass')
        self.category = ItemCategory.objects.create(name='Inv Cat')
        self.uom = UOM.objects.create(code='pcs', name='عدد', uom_type='count')
        self.location = StockLocation.objects.create(
            code='WH-01',
            name='انبار اصلی',
            location_type='warehouse'
        )
        self.item = Item.objects.create(
            category=self.category,
            code='INV-001',
            name='Inv Item',
            uom=self.uom,
            item_type='material'
        )
        StockBalance.objects.create(
            item=self.item,
            location=self.location,
            quantity_on_hand=Decimal('100'),
            quantity_reserved=Decimal('0'),
            quantity_available=Decimal('100'),
        )

    def test_receive_stock_requires_positive_quantity(self):
        """receive_stock باید مقدار منفی را قبول نکند"""
        with self.assertRaises(ValidationError):
            InventoryService.receive_stock(
                self.item, self.location, Decimal('-1'),
                lot_number='LOT-001', user=self.user
            )

    def test_reserve_stock_requires_positive_quantity(self):
        """reserve_stock باید مقدار منفی را قبول نکند"""
        with self.assertRaises(ValidationError):
            InventoryService.reserve_stock(
                self.item, self.location, Decimal('-1'),
                reference_document='REF', reference_id='1', user=self.user
            )

    def test_reserve_more_than_available_raises(self):
        """رزرو بیشتر از موجودی باید خطا دهد"""
        with self.assertRaises(ValidationError):
            InventoryService.reserve_stock(
                self.item, self.location, Decimal('101'),
                reference_document='REF', reference_id='1', user=self.user
            )

    def test_ledger_created_after_receive(self):
        """پس از رسید، یک رکورد در StockLedger باید ایجاد شود"""
        ledger = InventoryService.receive_stock(
            self.item, self.location, Decimal('10'),
            lot_number='LOT-001', user=self.user
        )
        self.assertEqual(ledger.ledger_type, 'receipt')
        self.assertEqual(ledger.quantity, Decimal('10'))
        self.assertEqual(StockLedger.objects.filter(item=self.item, location=self.location).count(), 1)

    def test_transfer_creates_two_ledger_entries(self):
        """انتقال باید دو رکورد در StockLedger ایجاد کند"""
        to_location = StockLocation.objects.create(
            code='WH-02',
            name='انبار دوم',
            location_type='warehouse'
        )
        result = InventoryService.transfer_stock(
            self.item, self.location, to_location, Decimal('10'),
            user=self.user, reference_document='TRF', reference_id='1'
        )
        self.assertEqual(StockLedger.objects.filter(item=self.item).count(), 2)
        self.assertEqual(result['from_balance'].quantity_on_hand, Decimal('90'))
        self.assertEqual(result['to_balance'].quantity_on_hand, Decimal('10'))


class InventoryItemLocationSafetyTests(TestCase):
    """تست‌های ایمنی Item/Location"""

    def test_create_item_without_warehouse_raises(self):
        """create_item بدون warehouse موجود باید خطا دهد"""
        category = ItemCategory.objects.create(name='Safe Cat')
        uom = UOM.objects.create(code='kg', name='کیلوگرم', uom_type='weight')
        StockLocation.objects.all().delete()
        with self.assertRaises(ValidationError):
            InventoryService.create_item(category, 'SAFE-001', 'Safe Item', uom)

    def test_create_item_with_explicit_location(self):
        """create_item با location صراحی باید موفقیت‌آمیز باشد"""
        category = ItemCategory.objects.create(name='Safe Cat2')
        uom = UOM.objects.create(code='kg', name='کیلوگرم', uom_type='weight')
        location = StockLocation.objects.create(
            code='WH-SAFE',
            name='Safe WH',
            location_type='warehouse'
        )
        item = InventoryService.create_item(category, 'SAFE-002', 'Safe Item2', uom, location=location)
        self.assertEqual(item.stock_balances.first().location, location)


class WarehouseIdempotencyTests(TestCase):
    """تست‌های idempotency برای عملیات انبار"""

    def setUp(self):
        self.user = User.objects.create_user(username='whuser', password='testpass')
        self.category = ItemCategory.objects.create(name='WH Cat')
        self.uom = UOM.objects.create(code='pcs', name='عدد', uom_type='count')
        self.location = StockLocation.objects.create(
            code='WH-WH',
            name='WH Location',
            location_type='warehouse'
        )
        self.item = Item.objects.create(
            category=self.category,
            code='WH-001',
            name='WH Item',
            uom=self.uom,
            item_type='material'
        )
        self.material_issue = MaterialIssue.objects.create(
            issue_number='MI-TEST-001',
            issued_by=self.user,
            status='issued'
        )
        self.mii = MaterialIssueItem.objects.create(
            material_issue=self.material_issue,
            item=self.item,
            source_location=self.location,
            target_location=self.location,
            quantity=Decimal('100')
        )

    def test_duplicate_idempotency_key_raises(self):
        """تکرار idempotency_key باید خطا دهد"""
        WarehouseService.issue_material(
            issued_by=self.user,
            items_data=[{'item': self.item, 'source_location': self.location, 'target_location': self.location, 'quantity': Decimal('10')}],
            idempotency_key='dup-key-001'
        )
        with self.assertRaises(ValidationError):
            WarehouseService.issue_material(
                issued_by=self.user,
                items_data=[{'item': self.item, 'source_location': self.location, 'target_location': self.location, 'quantity': Decimal('10')}],
                idempotency_key='dup-key-001'
            )

    def test_consume_idempotency_key_raises(self):
        """تکرار idempotency_key در مصرف باید خطا دهد"""
        WarehouseService.consume_material(
            self.mii, Decimal('10'), self.user,
            idempotency_key='consume-dup-001'
        )
        with self.assertRaises(ValidationError):
            WarehouseService.consume_material(
                self.mii, Decimal('10'), self.user,
                idempotency_key='consume-dup-001'
            )

    def test_consume_more_than_issued_raises(self):
        """مصرف بیشتر از مقدار صدور باید خطا دهد"""
        with self.assertRaises(ValidationError):
            WarehouseService.consume_material(
                self.mii, Decimal('101'), self.user
            )
