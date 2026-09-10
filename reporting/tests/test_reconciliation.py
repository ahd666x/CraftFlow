"""
Phase 11: V1-V2 Reconciliation Tests

Tests for the craftflow_reconcile_v2 management command that compares
V1 (product app) and V2 (decomposed apps) entity counts.
"""
import json
from io import StringIO

from django.test import TestCase
from django.core.management import call_command

from reporting.models import MigrationMap
from customers.models import Customer
from products.models import Product, ProductCategory as V2ProductCategory
from product.models import (
    Customer as V1Customer,
    Product as V1Product,
    Order as V1Order,
    ProductionTask as V1ProductionTask,
    ProductCategory as V1ProductCategory,
)
from sales.models import CustomerOrder


class V1V2ReconciliationTest(TestCase):
    """Test the reconciliation command produces correct report structure."""

    def setUp(self):
        self.v2_category = V2ProductCategory.objects.create(name='Recon V2')
        self.v1_category = V1ProductCategory.objects.create(name='Recon V1')
        self.v2_product = Product.objects.create(
            category=self.v2_category, name='V2 Product', code='V2P1', base_price=1000,
        )
        self.v2_customer = Customer.objects.create(name='V2 Customer')
        self.v2_order = CustomerOrder.objects.create(
            customer=self.v2_customer, order_date='2024-01-01',
        )

        self.v1_product = V1Product.objects.create(
            category=self.v1_category, name='V1 Product', base_price=1000,
        )
        self.v1_customer = V1Customer.objects.create(name='V1 Customer')
        self.v1_order = V1Order.objects.create(
            customer=self.v1_customer,
        )
        self.v1_task = V1ProductionTask.objects.create(
            order=self.v1_order,
            quantity=1,
            step_order=0,
            station_name='Test Station',
            color_part='',
            status='new',
        )

    def test_reconcile_json_output(self):
        """Reconciliation command produces valid JSON with expected keys."""
        out = StringIO()
        call_command('craftflow_reconcile_v2', '--json', stdout=out)

        report = json.loads(out.getvalue())

        self.assertIn('entity_comparisons', report)
        self.assertIn('migration_map_types_found', report)
        self.assertIn('migration_map_types_missing', report)
        self.assertIn('business_event_migration', report)
        self.assertIn('audit_log_count', report)
        self.assertIn('summary', report)

    def test_customer_reconciliation(self):
        """Customer counts should be compared."""
        out = StringIO()
        call_command('craftflow_reconcile_v2', '--json', stdout=out)
        report = json.loads(out.getvalue())

        customer_comparison = next(
            (r for r in report['entity_comparisons'] if r['key'] == 'customer'), None
        )
        self.assertIsNotNone(customer_comparison)
        self.assertEqual(customer_comparison['v1_count'], 1)
        self.assertEqual(customer_comparison['v2_count'], 1)
        self.assertTrue(customer_comparison['reconciled'])

    def test_product_reconciliation(self):
        """Product counts should be compared."""
        out = StringIO()
        call_command('craftflow_reconcile_v2', '--json', stdout=out)
        report = json.loads(out.getvalue())

        product_comparison = next(
            (r for r in report['entity_comparisons'] if r['key'] == 'product'), None
        )
        self.assertIsNotNone(product_comparison)
        self.assertEqual(product_comparison['v1_count'], 1)
        self.assertEqual(product_comparison['v2_count'], 1)
        self.assertTrue(product_comparison['reconciled'])

    def test_order_reconciliation(self):
        """Order counts should be compared."""
        out = StringIO()
        call_command('craftflow_reconcile_v2', '--json', stdout=out)
        report = json.loads(out.getvalue())

        order_comparison = next(
            (r for r in report['entity_comparisons'] if r['key'] == 'order'), None
        )
        self.assertIsNotNone(order_comparison)
        self.assertEqual(order_comparison['v1_count'], 1)
        self.assertEqual(order_comparison['v2_count'], 1)

    def test_task_reconciliation(self):
        """ProductionTask counts should be compared."""
        out = StringIO()
        call_command('craftflow_reconcile_v2', '--json', stdout=out)
        report = json.loads(out.getvalue())

        task_comparison = next(
            (r for r in report['entity_comparisons'] if r['key'] == 'production_task'), None
        )
        self.assertIsNotNone(task_comparison)
        self.assertEqual(task_comparison['v1_count'], 1)
        self.assertEqual(task_comparison['v2_count'], 0)
        self.assertFalse(task_comparison['reconciled'])

    def test_mismatch_detection(self):
        """When V1 and V2 counts differ, reconciliation should flag it."""
        out = StringIO()
        call_command('craftflow_reconcile_v2', '--json', stdout=out)
        report = json.loads(out.getvalue())

        mismatches = [r for r in report['entity_comparisons'] if not r['reconciled']]
        self.assertGreater(len(mismatches), 0)

    def test_migration_map_types(self):
        """The report should list which migration map types are present."""
        MigrationMap.objects.create(
            migration_type='customer',
            old_id='1', new_id='1', is_legacy=True,
        )
        out = StringIO()
        call_command('craftflow_reconcile_v2', '--json', stdout=out)
        report = json.loads(out.getvalue())

        self.assertIn('customer', report['migration_map_types_found'])

    def test_text_output(self):
        """Text output should produce human-readable report."""
        out = StringIO()
        call_command('craftflow_reconcile_v2', stdout=out)
        output = out.getvalue()

        self.assertIn('V1-V2 Reconciliation Report', output)
        self.assertIn('Entity Comparisons', output)
        self.assertIn('Summary', output)
