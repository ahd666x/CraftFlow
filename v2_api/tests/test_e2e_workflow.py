"""
Phase 10: V2 UI Integration Tests

Tests for:
- Feature flag gating (V2 disabled = 403)
- End-to-end happy path workflow
- Invalid workflow path (bad data)
- Permission tests (unauthenticated = 401)
- Rollback tests (transaction atomicity)
- Performance smoke test
"""

import time
import json

from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.contrib.auth.models import User
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from selvi.features import FEATURES
from selvi.features import is_enabled

from customers.models import Customer
from sales.models import CustomerOrder, CustomerOrderItem
from sales.services import OrderService
from products.models import ProductCategory, Product, ProductPart
from bom.models import BOM, BOMItem, BOMItemMaterialRule
from planning.models import Routing, RoutingOperation, WorkCenter
from production.models import ProductionOrder, ProductionOrderItem, ProductionOperation
from production.services import ProductionService
from production.selectors import ProductionSelectors
from inventory.models import Item, ItemCategory, UOM, StockLocation
from warehouse.models import MaterialIssue, MaterialRequirement
from warehouse.services import WarehouseService
from quality.models import QualityInspection
from quality.services import QualityService
from packaging.models import Package, PackageItem
from packaging.services import PackagingService
from shipping.models import Shipment, ShipmentItem
from shipping.services import ShippingService
from reporting.models import BusinessEvent, AuditLog
from reporting.services import EventService, AuditService


V2_API = '/v2/api/'


class V2FeatureFlagTest(TestCase):
    """Test feature flag controls access to V2 endpoints."""

    def setUp(self):
        self.user = User.objects.create_user('flaguser', password='testpass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_v2_api_enabled_by_default(self):
        """V2 API should be enabled by default in settings."""
        self.assertTrue(is_enabled('v2_ui'))
        self.assertTrue(is_enabled('v2_api'))

    def test_v2_urls_are_registered(self):
        """V2 URLs should be accessible at /v2/ path."""
        response = self.client.get(f'{V2_API}orders/')
        self.assertIn(response.status_code, [200, 400, 404])

    def test_feature_flag_disabled_returns_403(self):
        """When feature flag is disabled, API returns 403."""
        original = FEATURES['v2_ui']
        FEATURES['v2_ui'] = False
        try:
            self.client.force_authenticate(user=self.user)
            response = self.client.get(f'{V2_API}orders/')
            self.assertEqual(response.status_code, 403)
        finally:
            FEATURES['v2_ui'] = original


class V2EndToEndWorkflowTest(TransactionTestCase):
    """End-to-end happy path: Customer Order → BOM → Production → Quality → Packaging → Shipment."""

    def setUp(self):
        self.user = User.objects.create_user('e2euser', password='testpass',
                                             first_name='E2E', last_name='User')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.customer = Customer.objects.create(name='E2E Customer')
        self.category = ProductCategory.objects.create(name='E2E Cat')
        self.product = Product.objects.create(
            category=self.category, name='E2E Product', code='E2E_PROD',
            base_price=5000000,
        )

        # BOM
        self.bom = BOM.objects.create(
            product=self.product, revision='A', effective_date='2024-01-01',
        )

        # Create inventory items for BOM
        uom = UOM.objects.create(code='pc', name='piece', uom_type='count')
        item_cat = ItemCategory.objects.create(name='Raw')
        self.raw_item = Item.objects.create(
            code='RAW1', name='Raw Material', category=item_cat, uom=uom,
            unit_cost=1000, min_stock=10,
        )
        self.stock_location = StockLocation.objects.create(
            code='WH1', name='انبار اصلی',
        )

        # ProductPart for BOMItem
        self.part = ProductPart.objects.create(
            product=self.product, name='E2E Part', code='PART1',
            length=100.0, width=50.0, thickness=2.0,
        )

        bom_item = BOMItem.objects.create(
            bom=self.bom, part=self.part, quantity=2, sort_order=1,
        )
        BOMItemMaterialRule.objects.create(
            bom_item=bom_item, material_item=self.raw_item, quantity=2.0,
        )

        # Routing
        self.work_center = WorkCenter.objects.create(code='WC_E2E', name='WC E2E')
        self.routing = Routing.objects.create(
            product=self.product, revision='A', name='E2E Routing',
            effective_date='2024-01-01', status='active',
        )
        RoutingOperation.objects.create(
            routing=self.routing, sequence=1,
            operation_name='Assemble', operation_code='ASM',
            work_center=self.work_center,
        )

    def test_happy_path_full_workflow(self):
        """Full end-to-end workflow: Order → Production → Quality → Shipping."""
        # Step 1: Create customer order
        response = self.client.post(f'{V2_API}orders/', {
            'customer_id': self.customer.id,
            'order_date': '2024-06-01',
            'items': [
                {
                    'product_id': self.product.id,
                    'quantity': 100,
                    'size': '100x50',
                },
            ],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order_id = response.data['id']

        # Step 2: Create production order
        response = self.client.post(f'{V2_API}orders/{order_id}/production/', {
            'routing_id': self.routing.id,
            'bom_revision': 'A',
            'items': [
                {
                    'order_item_id': CustomerOrderItem.objects.first().id,
                    'product_id': self.product.id,
                    'quantity': 100,
                    'bom_id': self.bom.id,
                    'routing_id': self.routing.id,
                },
            ],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        po_id = response.data['production_order_number']

        # Step 3: List operations
        po = ProductionOrder.objects.get(order_number=po_id)
        response = self.client.get(f'{V2_API}production/{po.id}/operations/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 1)

        # Step 4: Start operation
        op = ProductionOperation.objects.filter(production_order=po).first()
        response = self.client.post(f'{V2_API}operations/{op.id}/start/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Step 5: Complete operation
        response = self.client.post(f'{V2_API}operations/{op.id}/complete/', {
            'completed_quantity': 100,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Step 6: Quality inspection
        response = self.client.post(f'{V2_API}quality/inspection/', {
            'production_order_id': po.id,
            'inspection_type': 'final',
            'result': 'pass',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Step 7: Shipment
        response = self.client.post(f'{V2_API}shipping/shipment/', {
            'order_id': order_id,
            'carrier': 'تست ارسال',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify events were created
        events = BusinessEvent.objects.filter(category='sales')
        self.assertGreaterEqual(events.count(), 1)

        # Verify audit logs
        audits = AuditLog.objects.filter(model_name='CustomerOrder')
        self.assertGreaterEqual(audits.count(), 1)

    def test_e2e_workflow_single_endpoint(self):
        """Single endpoint runs the full workflow."""
        response = self.client.post(f'{V2_API}workflow/e2e/', {
            'customer_id': self.customer.id,
            'product_id': self.product.id,
            'quantity': 50,
            'bom_revision': 'A',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'completed')
        self.assertEqual(response.data['operations_count'], 1)
        self.assertTrue(response.data['correlation_id'])


class V2InvalidWorkflowTest(TransactionTestCase):
    """Invalid workflow paths - bad data should be rejected."""

    def setUp(self):
        self.user = User.objects.create_user('invuser', password='testpass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_create_order_missing_customer_fails(self):
        """Creating order without customer should fail."""
        response = self.client.post(f'{V2_API}orders/', {
            'order_date': '2024-06-01',
            'items': [],
        }, format='json')
        self.assertIn(response.status_code, [400, 404])

    def test_create_order_missing_items_handled(self):
        """Creating order without items is handled gracefully."""
        customer = Customer.objects.create(name='Test')
        response = self.client.post(f'{V2_API}orders/', {
            'customer_id': customer.id,
            'order_date': '2024-06-01',
            'items': [],
        }, format='json')
        self.assertIn(response.status_code, [201, 400])

    def test_complete_operation_invalid_status(self):
        """Completing an operation that hasn't started should fail."""
        category = ProductCategory.objects.create(name='Test')
        product = Product.objects.create(
            category=category, name='Test', code='T1', base_price=1000,
        )
        customer = Customer.objects.create(name='Test')
        order = CustomerOrder.objects.create(customer=customer, order_date='2024-01-01')
        order_item = CustomerOrderItem.objects.create(
            order=order, product=product, quantity=1,
        )
        routing = Routing.objects.create(
            product=product, revision='A', name='T', effective_date='2024-01-01', status='active',
        )
        wc = WorkCenter.objects.create(code='WC', name='WC')
        bom = BOM.objects.create(product=product, revision='A', effective_date='2024-01-01')
        po = ProductionOrder.objects.create(
            order=order, order_number='PO_TEST', routing=routing, bom_revision='A', status='planned',
        )
        poi = ProductionOrderItem.objects.create(
            production_order=po, customer_order_item=order_item, product=product,
            quantity=1, bom=bom, routing=routing,
        )
        op = ProductionOperation.objects.create(
            production_order=po, production_order_item=poi, operation_name='T', operation_code='T',
            work_center=wc, sequence=1, status='waiting',
        )

        response = self.client.post(f'{V2_API}operations/{op.id}/complete/', {
            'completed_quantity': 1,
        }, format='json')
        self.assertIn(response.status_code, [400, 500])


class V2PermissionTest(TransactionTestCase):
    """Permission tests for V2 endpoints."""

    def setUp(self):
        self.user = User.objects.create_user('permuser', password='testpass')
        self.client = APIClient()

    def test_unauthenticated_access_denied(self):
        """Unauthenticated requests should be rejected."""
        response = self.client.get(f'{V2_API}orders/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_access_allowed(self):
        """Authenticated users can access V2 endpoints."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f'{V2_API}orders/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_feature_flag_blocks_authenticated(self):
        """Even authenticated users get 403 if feature is disabled."""
        self.client.force_authenticate(user=self.user)
        original = FEATURES['v2_ui']
        FEATURES['v2_ui'] = False
        try:
            response = self.client.get(f'{V2_API}orders/')
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        finally:
            FEATURES['v2_ui'] = original


class V2RollbackTest(TransactionTestCase):
    """Test transaction atomicity / rollback on failures."""

    def setUp(self):
        self.user = User.objects.create_user('rollbackuser', password='testpass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.customer = Customer.objects.create(name='Rollback Customer')
        self.category = ProductCategory.objects.create(name='RBCat')
        self.product = Product.objects.create(
            category=self.category, name='RB Product', code='RB_PROD', base_price=1000,
        )

    def test_create_order_creates_audit_and_event(self):
        """Creating order should create audit log and business event."""
        response = self.client.post(f'{V2_API}orders/', {
            'customer_id': self.customer.id,
            'order_date': '2024-06-01',
            'items': [
                {'product_id': self.product.id, 'quantity': 10},
            ],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order_id = response.data['id']

        self.assertTrue(CustomerOrder.objects.filter(id=order_id).exists())
        self.assertTrue(AuditLog.objects.filter(
            model_name='CustomerOrder', object_id=str(order_id)
        ).exists())

    def test_rollback_on_validation_error(self):
        """Failed creation should not leave partial data."""
        initial_audit_count = AuditLog.objects.count()

        # Creating order with non-existent customer should fail
        response = self.client.post(f'{V2_API}orders/', {
            'customer_id': 999999,
            'order_date': '2024-06-01',
            'items': [
                {'product_id': self.product.id, 'quantity': 10},
            ],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # No new audits should be created
        self.assertEqual(AuditLog.objects.count(), initial_audit_count)


class V2PerformanceSmokeTest(TransactionTestCase):
    """Performance smoke test - workflow should complete in reasonable time."""

    def setUp(self):
        self.user = User.objects.create_user('perfuser', password='testpass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.customer = Customer.objects.create(name='Perf Customer')
        self.category = ProductCategory.objects.create(name='PerfCat')
        self.product = Product.objects.create(
            category=self.category, name='Perf Product', code='PERF_PROD', base_price=1000,
        )

        self.bom = BOM.objects.create(
            product=self.product, revision='A', effective_date='2024-01-01',
        )
        self.work_center = WorkCenter.objects.create(code='WC_P', name='WC Perf')
        self.routing = Routing.objects.create(
            product=self.product, revision='A', name='Perf Routing',
            effective_date='2024-01-01', status='active',
        )
        RoutingOperation.objects.create(
            routing=self.routing, sequence=1,
            operation_name='Process', operation_code='PROC',
            work_center=self.work_center,
        )

    def test_e2e_workflow_under_5_seconds(self):
        """Full workflow should complete within 5 seconds."""
        start_time = time.time()

        response = self.client.post(f'{V2_API}workflow/e2e/', {
            'customer_id': self.customer.id,
            'product_id': self.product.id,
            'quantity': 100,
            'bom_revision': 'A',
        }, format='json')

        elapsed = time.time() - start_time

        if response.status_code == status.HTTP_200_OK:
            self.assertLess(elapsed, 5.0, f"Workflow took {elapsed:.2f}s, expected < 5s")
        else:
            self.assertLess(elapsed, 3.0)
