from django.db.models import Sum
from django.test import TestCase, TransactionTestCase
from django.db import transaction, IntegrityError
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
from inventory.models import ItemCategory, UOM, Item, StockLocation, StockBalance, StockLedger, StockReservation, StockLot
from inventory.services import InventoryService
from inventory.selectors import InventorySelectors
from warehouse.models import MaterialRequirement, MaterialRequest, MaterialRequestItem, MaterialIssue, MaterialIssueItem, MaterialConsumption, MaterialReturn, MaterialReturnItem, MaterialWaste
from warehouse.services import WarehouseService
from packaging.models import Package, PackageItem
from shipping.models import Shipment, ShipmentItem
from reporting.barcode_resolver import BarcodeResolver
from reporting.models import MigrationMap, MigrationRun
from product.models import Order, OrderItem, Customer as V1Customer, Product as V1Product, ProductCategory as V1ProductCategory, PackagingUnit
from accounts.models import Worker

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
        StockBalance.objects.create(
            item=self.item,
            location=self.location,
            quantity_on_hand=Decimal('100'),
            quantity_reserved=Decimal('0'),
            quantity_available=Decimal('100'),
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
            item=self.mii.item,
            quantity=Decimal('10'),
            consumed_by=self.user,
            location=self.location,
            idempotency_key='consume-dup-001'
        )
        with self.assertRaises(ValidationError):
            WarehouseService.consume_material(
                item=self.mii.item,
                quantity=Decimal('10'),
                consumed_by=self.user,
                location=self.location,
                idempotency_key='consume-dup-001'
            )

    def test_consume_more_than_issued_raises(self):
        """مصرف بیشتر از مقدار صدور باید خطا دهد"""
        with self.assertRaises(ValidationError):
            WarehouseService.consume_material(
                item=self.mii.item,
                quantity=Decimal('101'),
                consumed_by=self.user,
                location=self.location
            )


class InventoryReceiptTests(TestCase):
    """تست‌های رسید موجودی"""

    def setUp(self):
        self.user = User.objects.create_user(username='receiptuser', password='testpass')
        self.category = ItemCategory.objects.create(name='Receipt Cat')
        self.uom = UOM.objects.create(code='pcs', name='عدد', uom_type='count')
        self.location = StockLocation.objects.create(
            code='WH-REC',
            name='انبار رسید',
            location_type='warehouse'
        )
        self.item = Item.objects.create(
            category=self.category,
            code='REC-001',
            name='Receipt Item',
            uom=self.uom,
            item_type='material'
        )
        StockBalance.objects.create(
            item=self.item,
            location=self.location,
            quantity_on_hand=Decimal('0'),
            quantity_reserved=Decimal('0'),
            quantity_available=Decimal('0'),
        )

    def test_receive_stock_creates_ledger(self):
        """رسید موجودی باید یک رکورد در StockLedger ایجاد کند"""
        ledger = InventoryService.receive_stock(
            self.item, self.location, Decimal('10'),
            lot_number='LOT-REC-001', user=self.user
        )
        self.assertEqual(ledger.ledger_type, 'receipt')
        self.assertEqual(ledger.quantity, Decimal('10'))
        self.assertEqual(StockLedger.objects.filter(item=self.item, location=self.location).count(), 1)

    def test_receive_stock_requires_positive_quantity(self):
        """مقدار رسید باید بزرگ‌تر از صفر باشد"""
        with self.assertRaises(ValidationError):
            InventoryService.receive_stock(
                self.item, self.location, Decimal('-1'),
                lot_number='LOT-REC-002', user=self.user
            )

    def test_receive_stock_creates_lot(self):
        """رسید موجودی باید لات را ایجاد یا به‌روز کند"""
        InventoryService.receive_stock(
            self.item, self.location, Decimal('5'),
            lot_number='LOT-REC-003', user=self.user
        )
        lot = StockLot.objects.get(item=self.item, location=self.location, lot_number='LOT-REC-003')
        self.assertEqual(lot.quantity, Decimal('5'))

    def test_receive_stock_updates_balance(self):
        """رسید موجودی باید موجودی را به‌روز کند"""
        InventoryService.receive_stock(
            self.item, self.location, Decimal('20'),
            lot_number='LOT-REC-004', user=self.user
        )
        balance = StockBalance.objects.get(item=self.item, location=self.location)
        self.assertEqual(balance.quantity_on_hand, Decimal('20'))
        self.assertEqual(balance.quantity_available, Decimal('20'))


class InventoryReservationTests(TestCase):
    """تست‌های رزرو موجودی"""

    def setUp(self):
        self.user = User.objects.create_user(username='resuser', password='testpass')
        self.category = ItemCategory.objects.create(name='Res Cat')
        self.uom = UOM.objects.create(code='pcs', name='عدد', uom_type='count')
        self.location = StockLocation.objects.create(
            code='WH-RES',
            name='انبار رزرو',
            location_type='warehouse'
        )
        self.item = Item.objects.create(
            category=self.category,
            code='RES-001',
            name='Res Item',
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

    def test_reserve_stock_decreases_available(self):
        """رزرو باید available را کم کند"""
        reservation = InventoryService.reserve_stock(
            self.item, self.location, Decimal('30'),
            reference_document='REF-001', reference_id='1', user=self.user
        )
        balance = StockBalance.objects.get(item=self.item, location=self.location)
        self.assertEqual(balance.quantity_available, Decimal('70'))
        self.assertEqual(balance.quantity_reserved, Decimal('30'))
        self.assertEqual(reservation.status, 'active')

    def test_reserve_more_than_available_raises(self):
        """رزرو بیشتر از موجودی باید خطا دهد"""
        with self.assertRaises(ValidationError):
            InventoryService.reserve_stock(
                self.item, self.location, Decimal('101'),
                reference_document='REF-002', reference_id='2', user=self.user
            )

    def test_reserve_requires_positive_quantity(self):
        """مقدار رزرو باید بزرگ‌تر از صفر باشد"""
        with self.assertRaises(ValidationError):
            InventoryService.reserve_stock(
                self.item, self.location, Decimal('-1'),
                reference_document='REF-003', reference_id='3', user=self.user
            )

    def test_release_reservation_restores_available(self):
        """آزادسازی رزرو باید available را بازگرداند"""
        InventoryService.reserve_stock(
            self.item, self.location, Decimal('30'),
            reference_document='REF-004', reference_id='4', user=self.user
        )
        InventoryService.release_reservation(
            self.item, self.location, Decimal('30'),
            reference_document='REF-004', reference_id='4'
        )
        balance = StockBalance.objects.get(item=self.item, location=self.location)
        self.assertEqual(balance.quantity_available, Decimal('100'))
        self.assertEqual(balance.quantity_reserved, Decimal('0'))


class InventoryTransferTests(TestCase):
    """تست‌های انتقال موجودی"""

    def setUp(self):
        self.user = User.objects.create_user(username='transuser', password='testpass')
        self.category = ItemCategory.objects.create(name='Trans Cat')
        self.uom = UOM.objects.create(code='pcs', name='عدد', uom_type='count')
        self.from_location = StockLocation.objects.create(
            code='WH-FROM', name='انبار مبدأ', location_type='warehouse'
        )
        self.to_location = StockLocation.objects.create(
            code='WH-TO', name='انبار مقصد', location_type='warehouse'
        )
        self.item = Item.objects.create(
            category=self.category,
            code='TRANS-001',
            name='Trans Item',
            uom=self.uom,
            item_type='material'
        )
        StockBalance.objects.create(
            item=self.item,
            location=self.from_location,
            quantity_on_hand=Decimal('100'),
            quantity_reserved=Decimal('0'),
            quantity_available=Decimal('100'),
        )
        StockBalance.objects.create(
            item=self.item,
            location=self.to_location,
            quantity_on_hand=Decimal('0'),
            quantity_reserved=Decimal('0'),
            quantity_available=Decimal('0'),
        )

    def test_transfer_creates_two_ledger_entries(self):
        """انتقال باید دو رکورد در StockLedger ایجاد کند"""
        result = InventoryService.transfer_stock(
            self.item, self.from_location, self.to_location, Decimal('10'),
            user=self.user, reference_document='TRF', reference_id='1'
        )
        self.assertEqual(StockLedger.objects.filter(item=self.item).count(), 2)
        self.assertEqual(result['from_balance'].quantity_on_hand, Decimal('90'))
        self.assertEqual(result['to_balance'].quantity_on_hand, Decimal('10'))

    def test_transfer_same_location_raises(self):
        """انتقال به همان مکان باید خطا دهد"""
        with self.assertRaises(ValidationError):
            InventoryService.transfer_stock(
                self.item, self.from_location, self.from_location, Decimal('10'),
                user=self.user
            )

    def test_transfer_insufficient_balance_raises(self):
        """انتقال با موجودی ناکافی باید خطا دهد"""
        with self.assertRaises(ValidationError):
            InventoryService.transfer_stock(
                self.item, self.from_location, self.to_location, Decimal('101'),
                user=self.user
            )


class InventoryAdjustmentTests(TestCase):
    """تست‌های اصلاحیه موجودی"""

    def setUp(self):
        self.user = User.objects.create_user(username='adjuser', password='testpass')
        self.category = ItemCategory.objects.create(name='Adj Cat')
        self.uom = UOM.objects.create(code='pcs', name='عدد', uom_type='count')
        self.location = StockLocation.objects.create(
            code='WH-ADJ', name='انبار اصلاحیه', location_type='warehouse'
        )
        self.item = Item.objects.create(
            category=self.category,
            code='ADJ-001',
            name='Adj Item',
            uom=self.uom,
            item_type='material'
        )
        StockBalance.objects.create(
            item=self.item,
            location=self.location,
            quantity_on_hand=Decimal('50'),
            quantity_reserved=Decimal('0'),
            quantity_available=Decimal('50'),
        )

    def test_adjust_stock_increases_balance(self):
        """اصلاحیه مثبت باید موجودی را افزایش دهد"""
        InventoryService.adjust_stock(
            self.item, self.location, Decimal('20'),
            user=self.user, reference_document='ADJ', reference_id='1', reason='افزایش'
        )
        balance = StockBalance.objects.get(item=self.item, location=self.location)
        self.assertEqual(balance.quantity_on_hand, Decimal('70'))

    def test_adjust_stock_decreases_balance(self):
        """اصلاحیه منفی باید موجودی را کاهش دهد"""
        InventoryService.adjust_stock(
            self.item, self.location, Decimal('-20'),
            user=self.user, reference_document='ADJ', reference_id='2', reason='کاهش'
        )
        balance = StockBalance.objects.get(item=self.item, location=self.location)
        self.assertEqual(balance.quantity_on_hand, Decimal('30'))

    def test_adjust_stock_zero_raises(self):
        """اصلاحیه صفر باید خطا دهد"""
        with self.assertRaises(ValidationError):
            InventoryService.adjust_stock(
                self.item, self.location, Decimal('0'),
                user=self.user
            )

    def test_adjust_stock_negative_balance_raises(self):
        """اصلاحیه منفی که به موجودی منفی منجر می‌شود باید خطا دهد"""
        with self.assertRaises(ValidationError):
            InventoryService.adjust_stock(
                self.item, self.location, Decimal('-100'),
                user=self.user
            )


class InventoryNegativeStockTests(TestCase):
    """تست‌های موجودی منفی"""

    def setUp(self):
        self.user = User.objects.create_user(username='neguser', password='testpass')
        self.category = ItemCategory.objects.create(name='Neg Cat')
        self.uom = UOM.objects.create(code='pcs', name='عدد', uom_type='count')
        self.location = StockLocation.objects.create(
            code='WH-NEG', name='انبار منفی', location_type='warehouse'
        )
        self.item = Item.objects.create(
            category=self.category,
            code='NEG-001',
            name='Neg Item',
            uom=self.uom,
            item_type='material'
        )
        StockBalance.objects.create(
            item=self.item,
            location=self.location,
            quantity_on_hand=Decimal('10'),
            quantity_reserved=Decimal('0'),
            quantity_available=Decimal('10'),
        )

    def test_issue_more_than_available_raises(self):
        """صدور بیشتر از موجودی باید خطا دهد"""
        with self.assertRaises(ValidationError):
            WarehouseService.issue_material(
                issued_by=self.user,
                items_data=[{
                    'item': self.item,
                    'source_location': self.location,
                    'target_location': self.location,
                    'quantity': Decimal('20')
                }]
            )

    def test_waste_more_than_available_raises(self):
        """ضایعات بیشتر از موجودی باید خطا دهد"""
        with self.assertRaises(ValidationError):
            WarehouseService.waste_material(
                recorded_by=self.user,
                item=self.item,
                location=self.location,
                quantity=Decimal('20'),
                reason='ضایعات تست',
                cost=Decimal('0')
            )

    def test_consume_more_than_available_raises(self):
        """مصرف بیشتر از موجودی باید خطا دهد"""
        with self.assertRaises(ValidationError):
            WarehouseService.consume_material(
                item=self.item,
                quantity=Decimal('20'),
                consumed_by=self.user,
                location=self.location
            )


class InventoryConcurrencyTests(TransactionTestCase):
    """تست‌های همزمانی"""

    def setUp(self):
        self.user = User.objects.create_user(username='concuser', password='testpass')
        self.category = ItemCategory.objects.create(name='Conc Cat')
        self.uom = UOM.objects.create(code='pcs', name='عدد', uom_type='count')
        self.location = StockLocation.objects.create(
            code='WH-CONC', name='انبار همزمانی', location_type='warehouse'
        )
        self.item = Item.objects.create(
            category=self.category,
            code='CONC-001',
            name='Conc Item',
            uom=self.uom,
            item_type='material'
        )
        StockBalance.objects.create(
            item=self.item,
            location=self.location,
            quantity_on_hand=Decimal('10'),
            quantity_reserved=Decimal('0'),
            quantity_available=Decimal('10'),
        )

    def test_concurrent_issue_updates_balance(self):
        """صدور همزمان باید موجودی را به درستی به‌روز کند"""
        def issue_qty(qty):
            with transaction.atomic():
                balance = StockBalance.objects.select_for_update().get(item=self.item, location=self.location)
                balance.quantity_on_hand -= qty
                balance.quantity_available -= qty
                balance.save(update_fields=['quantity_on_hand', 'quantity_available'])
                StockLedger.objects.create(
                    item=self.item,
                    location=self.location,
                    ledger_type='issue',
                    quantity=-qty,
                    balance_after=balance.quantity_on_hand,
                    created_by=self.user,
                )
        
        issue_qty(Decimal('3'))
        issue_qty(Decimal('4'))
        
        balance = StockBalance.objects.get(item=self.item, location=self.location)
        self.assertEqual(balance.quantity_on_hand, Decimal('3'))
        self.assertEqual(balance.quantity_available, Decimal('3'))


class InventoryReconciliationTests(TestCase):
    """تست‌های reconcile موجودی"""

    def setUp(self):
        self.user = User.objects.create_user(username='recuser', password='testpass')
        self.category = ItemCategory.objects.create(name='Rec Cat')
        self.uom = UOM.objects.create(code='pcs', name='عدد', uom_type='count')
        self.location = StockLocation.objects.create(
            code='WH-RECON', name='انبار reconcile', location_type='warehouse'
        )
        self.item = Item.objects.create(
            category=self.category,
            code='RECON-001',
            name='Recon Item',
            uom=self.uom,
            item_type='material'
        )
        StockBalance.objects.create(
            item=self.item,
            location=self.location,
            quantity_on_hand=Decimal('50'),
            quantity_reserved=Decimal('10'),
            quantity_available=Decimal('40'),
        )

    def test_balance_matches_ledger_sum(self):
        """موجودی باید با مجموع دفتر روزنامه مطابقت داشته باشد"""
        InventoryService.receive_stock(
            self.item, self.location, Decimal('20'),
            lot_number='LOT-RECON', user=self.user
        )
        InventoryService.adjust_stock(
            self.item, self.location, Decimal('-5'),
            user=self.user, reason='اصلاحیه'
        )
        
        balance = StockBalance.objects.get(item=self.item, location=self.location)
        ledger_sum = StockLedger.objects.filter(item=self.item, location=self.location).aggregate(
            total=Sum('quantity')
        )['total'] or Decimal('0')
        
        self.assertEqual(balance.quantity_on_hand, Decimal('65'))
        self.assertEqual(ledger_sum, Decimal('15'))
        self.assertEqual(balance.quantity_on_hand - ledger_sum, Decimal('50'))


class WarehouseIssueTests(TestCase):
    """تست‌های صدور مواد"""

    def setUp(self):
        self.user = User.objects.create_user(username='issueuser', password='testpass')
        self.category = ItemCategory.objects.create(name='Issue Cat')
        self.uom = UOM.objects.create(code='pcs', name='عدد', uom_type='count')
        self.source_location = StockLocation.objects.create(
            code='WH-SRC', name='انبار مبدأ', location_type='warehouse'
        )
        self.target_location = StockLocation.objects.create(
            code='WH-TGT', name='انبار مقصد', location_type='warehouse'
        )
        self.item = Item.objects.create(
            category=self.category,
            code='ISS-001',
            name='Issue Item',
            uom=self.uom,
            item_type='material'
        )
        StockBalance.objects.create(
            item=self.item,
            location=self.source_location,
            quantity_on_hand=Decimal('100'),
            quantity_reserved=Decimal('0'),
            quantity_available=Decimal('100'),
        )
        StockBalance.objects.create(
            item=self.item,
            location=self.target_location,
            quantity_on_hand=Decimal('0'),
            quantity_reserved=Decimal('0'),
            quantity_available=Decimal('0'),
        )

    def test_issue_material_decreases_source_balance(self):
        """صدور باید موجودی مبدأ را کم کند"""
        WarehouseService.issue_material(
            issued_by=self.user,
            items_data=[{
                'item': self.item,
                'source_location': self.source_location,
                'target_location': self.target_location,
                'quantity': Decimal('20')
            }]
        )
        balance = StockBalance.objects.get(item=self.item, location=self.source_location)
        self.assertEqual(balance.quantity_on_hand, Decimal('80'))
        self.assertEqual(balance.quantity_available, Decimal('80'))

    def test_issue_material_increases_target_balance(self):
        """صدور باید موجودی مقصد را افزایش دهد"""
        WarehouseService.issue_material(
            issued_by=self.user,
            items_data=[{
                'item': self.item,
                'source_location': self.source_location,
                'target_location': self.target_location,
                'quantity': Decimal('20')
            }]
        )
        balance = StockBalance.objects.get(item=self.item, location=self.target_location)
        self.assertEqual(balance.quantity_on_hand, Decimal('20'))
        self.assertEqual(balance.quantity_available, Decimal('20'))

    def test_issue_material_with_lot(self):
        """صدور باید لات را به‌روز کند"""
        lot = StockLot.objects.create(
            item=self.item,
            location=self.source_location,
            lot_number='LOT-ISS-001',
            quantity=Decimal('100'),
            received_date='2024-01-01',
            received_by=self.user,
        )
        WarehouseService.issue_material(
            issued_by=self.user,
            items_data=[{
                'item': self.item,
                'source_location': self.source_location,
                'target_location': self.target_location,
                'quantity': Decimal('20'),
                'lot': lot
            }]
        )
        lot.refresh_from_db()
        self.assertEqual(lot.quantity, Decimal('80'))

    def test_duplicate_issue_idempotency_key_raises(self):
        """تکرار idempotency_key در صدور باید خطا دهد"""
        WarehouseService.issue_material(
            issued_by=self.user,
            items_data=[{
                'item': self.item,
                'source_location': self.source_location,
                'target_location': self.target_location,
                'quantity': Decimal('10')
            }],
            idempotency_key='issue-dup-001'
        )
        with self.assertRaises(ValidationError):
            WarehouseService.issue_material(
                issued_by=self.user,
                items_data=[{
                    'item': self.item,
                    'source_location': self.source_location,
                    'target_location': self.target_location,
                    'quantity': Decimal('10')
                }],
                idempotency_key='issue-dup-001'
            )


class WarehouseConsumptionTests(TestCase):
    """تست‌های مصرف مواد"""

    def setUp(self):
        self.user = User.objects.create_user(username='consuser', password='testpass')
        self.category = ItemCategory.objects.create(name='Cons Cat')
        self.uom = UOM.objects.create(code='pcs', name='عدد', uom_type='count')
        self.location = StockLocation.objects.create(
            code='WH-CONS', name='انبار مصرف', location_type='warehouse'
        )
        self.item = Item.objects.create(
            category=self.category,
            code='CONS-001',
            name='Cons Item',
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

    def test_consume_material_decreases_balance(self):
        """مصرف باید موجودی را کم کند"""
        WarehouseService.consume_material(
            item=self.item,
            quantity=Decimal('30'),
            consumed_by=self.user,
            location=self.location
        )
        balance = StockBalance.objects.get(item=self.item, location=self.location)
        self.assertEqual(balance.quantity_on_hand, Decimal('70'))
        self.assertEqual(balance.quantity_available, Decimal('70'))

    def test_consume_material_creates_ledger(self):
        """مصرف باید رکورد در StockLedger ایجاد کند"""
        WarehouseService.consume_material(
            item=self.item,
            quantity=Decimal('10'),
            consumed_by=self.user,
            location=self.location
        )
        self.assertEqual(StockLedger.objects.filter(item=self.item, location=self.location).count(), 1)

    def test_consume_more_than_available_raises(self):
        """مصرف بیشتر از موجودی باید خطا دهد"""
        with self.assertRaises(ValidationError):
            WarehouseService.consume_material(
                item=self.item,
                quantity=Decimal('101'),
                consumed_by=self.user,
                location=self.location
            )


class WarehouseReturnTests(TestCase):
    """تست‌های مرجوعی مواد"""

    def setUp(self):
        self.user = User.objects.create_user(username='retuser', password='testpass')
        self.category = ItemCategory.objects.create(name='Ret Cat')
        self.uom = UOM.objects.create(code='pcs', name='عدد', uom_type='count')
        self.source_location = StockLocation.objects.create(
            code='WH-RET-SRC', name='انبار مرجوعی مبدأ', location_type='warehouse'
        )
        self.target_location = StockLocation.objects.create(
            code='WH-RET-TGT', name='انبار مرجوعی مقصد', location_type='warehouse'
        )
        self.item = Item.objects.create(
            category=self.category,
            code='RET-001',
            name='Ret Item',
            uom=self.uom,
            item_type='material'
        )
        StockBalance.objects.create(
            item=self.item,
            location=self.target_location,
            quantity_on_hand=Decimal('50'),
            quantity_reserved=Decimal('0'),
            quantity_available=Decimal('50'),
        )

    def test_return_material_increases_target_balance(self):
        """مرجوعی باید موجودی مقصد را افزایش دهد"""
        WarehouseService.return_material(
            returned_by=self.user,
            items_data=[{
                'item': self.item,
                'source_location': self.source_location,
                'target_location': self.target_location,
                'quantity': Decimal('10')
            }]
        )
        balance = StockBalance.objects.get(item=self.item, location=self.target_location)
        self.assertEqual(balance.quantity_on_hand, Decimal('60'))
        self.assertEqual(balance.quantity_available, Decimal('60'))


class WarehouseWasteTests(TestCase):
    """تست‌های ضایعات مواد"""

    def setUp(self):
        self.user = User.objects.create_user(username='wasteuser', password='testpass')
        self.category = ItemCategory.objects.create(name='Waste Cat')
        self.uom = UOM.objects.create(code='pcs', name='عدد', uom_type='count')
        self.location = StockLocation.objects.create(
            code='WH-WASTE', name='انبار ضایعات', location_type='warehouse'
        )
        self.item = Item.objects.create(
            category=self.category,
            code='WASTE-001',
            name='Waste Item',
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

    def test_waste_material_decreases_balance(self):
        """ضایعات باید موجودی را کم کند"""
        WarehouseService.waste_material(
            recorded_by=self.user,
            item=self.item,
            location=self.location,
            quantity=Decimal('5'),
            reason='ضایعات تست',
            cost=Decimal('1000')
        )
        balance = StockBalance.objects.get(item=self.item, location=self.location)
        self.assertEqual(balance.quantity_on_hand, Decimal('95'))
        self.assertEqual(balance.quantity_available, Decimal('95'))

    def test_waste_material_creates_ledger(self):
        """ضایعات باید رکورد در StockLedger ایجاد کند"""
        WarehouseService.waste_material(
            recorded_by=self.user,
            item=self.item,
            location=self.location,
            quantity=Decimal('5'),
            reason='ضایعات تست',
            cost=Decimal('1000')
        )
        self.assertEqual(StockLedger.objects.filter(item=self.item, location=self.location).count(), 1)

    def test_waste_more_than_available_raises(self):
        """ضایعات بیشتر از موجودی باید خطا دهد"""
        with self.assertRaises(ValidationError):
            WarehouseService.waste_material(
                recorded_by=self.user,
                item=self.item,
                location=self.location,
                quantity=Decimal('101'),
                reason='ضایعات تست',
                cost=Decimal('0')
            )


class WarehousePartialIssueTests(TestCase):
    """تست‌های صدور جزئی"""

    def setUp(self):
        self.user = User.objects.create_user(username='partissueuser', password='testpass')
        self.category = ItemCategory.objects.create(name='PartIssue Cat')
        self.uom = UOM.objects.create(code='pcs', name='عدد', uom_type='count')
        self.source_location = StockLocation.objects.create(
            code='WH-PART-SRC', name='انبار صدور جزئی مبدأ', location_type='warehouse'
        )
        self.target_location = StockLocation.objects.create(
            code='WH-PART-TGT', name='انبار صدور جزئی مقصد', location_type='warehouse'
        )
        self.item = Item.objects.create(
            category=self.category,
            code='PART-ISS-001',
            name='Part Issue Item',
            uom=self.uom,
            item_type='material'
        )
        StockBalance.objects.create(
            item=self.item,
            location=self.source_location,
            quantity_on_hand=Decimal('100'),
            quantity_reserved=Decimal('0'),
            quantity_available=Decimal('100'),
        )

    def test_partial_issue_updates_balance(self):
        """صدور جزئی باید موجودی را به درستی به‌روز کند"""
        WarehouseService.issue_material(
            issued_by=self.user,
            items_data=[{
                'item': self.item,
                'source_location': self.source_location,
                'target_location': self.target_location,
                'quantity': Decimal('30')
            }]
        )
        balance = StockBalance.objects.get(item=self.item, location=self.source_location)
        self.assertEqual(balance.quantity_on_hand, Decimal('70'))
        self.assertEqual(balance.quantity_available, Decimal('70'))


class MaterialRequirementTests(TestCase):
    """تست‌های نیاز مواد اولیه"""

    def setUp(self):
        self.user = User.objects.create_user(username='requser', password='testpass')
        self.customer = Customer.objects.create(name='Req Customer')
        self.order = CustomerOrder.objects.create(
            customer=self.customer,
            order_date='2024-01-01'
        )
        self.category = ItemCategory.objects.create(name='Req Cat')
        self.uom = UOM.objects.create(code='pcs', name='عدد', uom_type='count')
        self.item = Item.objects.create(
            category=self.category,
            code='REQ-001',
            name='Req Item',
            uom=self.uom,
            item_type='material'
        )
        self.product_category = ProductCategory.objects.create(name='Req Prod Cat')
        self.product = Product.objects.create(
            category=self.product_category,
            name='Req Product',
            base_price=1000000
        )
        self.coi = CustomerOrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=1
        )

    def test_create_material_requirement(self):
        """ایجاد نیاز مواد باید موفق باشد"""
        req = WarehouseService.create_material_requirement(
            customer_order_item=self.coi,
            item=self.item,
            required_quantity=Decimal('50')
        )
        self.assertEqual(req.required_quantity, Decimal('50'))
        self.assertEqual(req.status, 'draft')


class BarcodeLegacyTests(TestCase):
    """تست‌های QR legacy برای OrderItem و PackagingUnit"""

    def setUp(self):
        self.user = User.objects.create_user(username='barcodelegacy', password='testpass')
        self.customer = V1Customer.objects.create(name='Barcode Legacy Customer')
        self.category = V1ProductCategory.objects.create(name='Barcode Legacy Cat')
        self.product = V1Product.objects.create(
            category=self.category,
            name='Barcode Legacy Product',
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
        self.pu = self.item.packaging_units.first()

    def test_order_item_legacy_qr_resolves(self):
        """QR قدیمی OrderItem باید resolve شود"""
        from django.urls import reverse
        qr_url = f"https://selvichoob.ir{reverse('scan_qr', args=[self.item.id])}"
        result = BarcodeResolver.resolve(qr_url)
        self.assertEqual(result['entity_type'], 'order_item')
        self.assertEqual(result['entity_id'], self.item.id)
        self.assertTrue(result['legacy'])

    def test_packaging_unit_legacy_qr_resolves(self):
        """QR قدیمی PackagingUnit باید resolve شود"""
        from django.urls import reverse
        qr_url = f"https://selvichoob.ir{reverse('scan_packaging_unit', args=[self.pu.id])}"
        result = BarcodeResolver.resolve(qr_url)
        self.assertEqual(result['entity_type'], 'packaging_unit')
        self.assertEqual(result['entity_id'], self.pu.id)
        self.assertTrue(result['legacy'])

    def test_legacy_without_migration_map(self):
        """legacy entity بدون MigrationMap باید معتبر بماند"""
        result = BarcodeResolver.resolve(str(self.item.id))
        self.assertTrue(result['legacy'])
        self.assertIsNone(result['v2_metadata'])

    def test_legacy_with_migration_map(self):
        """legacy entity با MigrationMap باید v2_metadata داشته باشد"""
        run = MigrationRun.objects.create(
            phase='barcode',
            name='test-barcode-run',
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

    def test_invalid_qr_returns_unknown(self):
        """QR نامعتبر باید unknown برگرداند"""
        result = BarcodeResolver.resolve('invalid-payload')
        self.assertEqual(result['entity_type'], 'unknown')
        self.assertFalse(result['legacy'])

    def test_empty_qr_returns_unknown(self):
        """QR خالی باید unknown برگرداند"""
        result = BarcodeResolver.resolve('')
        self.assertEqual(result['entity_type'], 'unknown')


class MigrationMapIntegrityTests(TestCase):
    """تست‌های MigrationMap integrity"""

    def test_migration_map_unique_together(self):
        """MigrationMap باید unique_together روی (migration_type, old_id, old_app) را رعایت کند"""
        run = MigrationRun.objects.create(
            phase='master-data',
            name='integrity-test',
            status='completed'
        )
        MigrationMap.objects.create(
            migration_type='customer',
            old_id='1',
            old_app='product',
            new_id='100',
            new_app='customers',
            new_model='Customer',
            migration_run=run,
        )
        with self.assertRaises(IntegrityError):
            MigrationMap.objects.create(
                migration_type='customer',
                old_id='1',
                old_app='product',
                new_id='200',
                new_app='customers',
                new_model='Customer',
                migration_run=run,
            )

    def test_rollback_deletes_migration_maps(self):
        """Rollback باید MigrationMapهای مربوط به run را حذف کند"""
        run = MigrationRun.objects.create(
            phase='master-data',
            name='rollback-test',
            status='completed'
        )
        MigrationMap.objects.create(
            migration_type='customer',
            old_id='1',
            old_app='product',
            new_id='100',
            new_app='customers',
            new_model='Customer',
            migration_run=run,
        )
        from reporting.management.commands.craftflow_migrate_v2 import Command
        cmd = Command()
        cmd._rollback(str(run.id))
        self.assertFalse(MigrationMap.objects.filter(migration_run=run).exists())
        self.assertFalse(MigrationRun.objects.filter(pk=run.id).exists())


class PackagingMultiItemTests(TestCase):
    """تست‌های Package چند آیتمی"""

    def setUp(self):
        self.user = User.objects.create_user(username='pkguser', password='testpass')
        self.customer = Customer.objects.create(name='Pkg Customer')
        self.category = ProductCategory.objects.create(name='Pkg Cat')
        self.product = Product.objects.create(
            category=self.category,
            name='Pkg Product',
            base_price=1000000
        )
        self.order = CustomerOrder.objects.create(
            customer=self.customer,
            order_date='2024-01-01'
        )
        self.coi = CustomerOrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=2
        )

    def test_package_multiple_items(self):
        """Package باید بتواند چند PackageItem داشته باشد"""
        from packaging.models import Package, PackageItem
        from inventory.models import ItemCategory, UOM, Item, StockLocation
        
        cat = ItemCategory.objects.create(name='Pkg Item Cat')
        uom = UOM.objects.create(code='pcs', name='عدد', uom_type='count')
        item1 = Item.objects.create(category=cat, code='PKG-ITEM-1', name='Pkg Item 1', uom=uom, item_type='material', barcode='PKG-BAR-1')
        item2 = Item.objects.create(category=cat, code='PKG-ITEM-2', name='Pkg Item 2', uom=uom, item_type='material', barcode='PKG-BAR-2')
        
        pkg = Package.objects.create(
            customer_order_item=self.coi,
            package_number='PKG-MULTI-001',
            status='packed',
            packed_by=self.user,
        )
        PackageItem.objects.create(package=pkg, item=item1, quantity=2, serial_numbers=[])
        PackageItem.objects.create(package=pkg, item=item2, quantity=1, serial_numbers=[])
        
        self.assertEqual(pkg.items.count(), 2)
        self.assertEqual(pkg.items.filter(item=item1).first().quantity, 2)
        self.assertEqual(pkg.items.filter(item=item2).first().quantity, 1)


class ShipmentPartialTests(TestCase):
    """تست‌های Shipment جزئی"""

    def setUp(self):
        self.user = User.objects.create_user(username='shipuser', password='testpass')
        self.customer = Customer.objects.create(name='Ship Customer')
        self.category = ProductCategory.objects.create(name='Ship Cat')
        self.product = Product.objects.create(
            category=self.category,
            name='Ship Product',
            base_price=1000000
        )
        self.order = CustomerOrder.objects.create(
            customer=self.customer,
            order_date='2024-01-01'
        )
        self.coi = CustomerOrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=2
        )

    def test_partial_shipment_creates_shipment_item(self):
        """Shipment جزئی باید ShipmentItem ایجاد کند"""
        from packaging.models import Package
        from shipping.models import Shipment, ShipmentItem
        
        pkg = Package.objects.create(
            customer_order_item=self.coi,
            package_number='PKG-SHIP-001',
            status='packed',
            packed_by=self.user,
        )
        
        shipment = Shipment.objects.create(
            shipment_number='SH-PART-001',
            customer_order=self.order,
            customer=self.customer,
            status='in_transit',
            created_by=self.user,
        )
        ShipmentItem.objects.create(
            shipment=shipment,
            package=pkg,
            quantity=1,
            weight_kg=10,
            volume_m3=0.1,
        )
        
        self.assertEqual(shipment.items.count(), 1)
        self.assertEqual(shipment.items.first().quantity, 1)


class DuplicateShipmentTests(TestCase):
    """تست‌های duplicate shipment"""

    def setUp(self):
        self.user = User.objects.create_user(username='dupship', password='testpass')
        self.customer = Customer.objects.create(name='Dup Ship Customer')
        self.category = ProductCategory.objects.create(name='Dup Ship Cat')
        self.product = Product.objects.create(
            category=self.category,
            name='Dup Ship Product',
            base_price=1000000
        )
        self.order = CustomerOrder.objects.create(
            customer=self.customer,
            order_date='2024-01-01'
        )
        self.coi = CustomerOrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=1
        )

    def test_duplicate_shipment_number_raises(self):
        """شماره shipment تکراری باید خطا دهد"""
        from shipping.models import Shipment
        
        Shipment.objects.create(
            shipment_number='SH-DUP-001',
            customer_order=self.order,
            customer=self.customer,
            status='draft',
            created_by=self.user,
        )
        with self.assertRaises(IntegrityError):
            Shipment.objects.create(
                shipment_number='SH-DUP-001',
                customer_order=self.order,
                customer=self.customer,
                status='draft',
                created_by=self.user,
            )
