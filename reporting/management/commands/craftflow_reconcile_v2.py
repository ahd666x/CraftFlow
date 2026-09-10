"""Phase 11: V1-V2 Reconciliation command.

Compares V1 (product app) and V2 (decomposed apps) entity counts
and MigrationMap anchors to verify data integrity after migration.
"""
import json
from django.core.management.base import BaseCommand
from django.db.models import Count

from reporting.models import MigrationMap, MigrationRun, BusinessEvent, AuditLog


class Command(BaseCommand):
    help = 'Reconcile V1 and V2 data: compare counts and migration maps.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--json', action='store_true',
            help='Output reconciliation report as JSON',
        )

    def handle(self, *args, **options):
        report = self.generate_report()

        if options['json']:
            self.stdout.write(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            self.print_report(report)

    def generate_report(self):
        """Generate reconciliation report comparing V1 and V2 entities."""
        from product.models import (
            Customer as V1Customer, Product as V1Product,
            ProductBOM as V1BOM, Order as V1Order, OrderItem as V1OrderItem,
            ProductionTask as V1ProductionTask, Material as V1Material,
            PaintingProcess as V1PaintingProcess, ProductionEvent as V1ProductionEvent,
            ShipmentLog as V1ShipmentLog,
        )
        from customers.models import Customer as V2Customer
        from products.models import Product as V2Product
        from bom.models import BOM as V2BOM, BOMItem as V2BOMItem
        from sales.models import CustomerOrder as V2Order, CustomerOrderItem as V2OrderItem
        from production.models import ProductionOrder as V2ProdOrder, ProductionOrderItem as V2ProdOrderItem, ProductionOperation as V2ProdOperation
        from inventory.models import Item as V2Item, RawMaterial as V2RawMaterial
        from painting.models import PaintingSchedule as V2PaintingSchedule
        from shipping.models import Shipment as V2Shipment

        comparisons = [
            ('customer', 'Customer', V1Customer, V2Customer),
            ('product', 'Product', V1Product, V2Product),
            ('bom', 'BOM', V1BOM, V2BOM),
            ('order', 'Order', V1Order, V2Order),
            ('order_item', 'OrderItem', V1OrderItem, V2OrderItem),
            ('production_task', 'ProductionTask', V1ProductionTask, V2ProdOrder),
            ('material', 'Material', V1Material, V2RawMaterial),
            ('item', 'Item', V1Material, V2Item),
            ('painting_process', 'PaintingProcess', V1PaintingProcess, V2PaintingSchedule),
            ('production_event', 'ProductionEvent', V1ProductionEvent, BusinessEvent),
            ('shipment_log', 'ShipmentLog', V1ShipmentLog, V2Shipment),
        ]

        results = []
        for key, name, v1_model, v2_model in comparisons:
            v1_count = v1_model.objects.count()
            v2_count = v2_model.objects.count()

            map_count = MigrationMap.objects.filter(
                migration_type=key, is_legacy=True
            ).count()

            results.append({
                'entity': name,
                'key': key,
                'v1_count': v1_count,
                'v2_count': v2_count,
                'migration_map_entries': map_count,
                'reconciled': v1_count == v2_count,
            })

        # Check MigrationMap coverage
        all_map_types = list(MigrationMap.objects.values_list(
            'migration_type', flat=True
        ).distinct())
        expected_types = [
            'customer', 'order', 'order_item', 'product',
            'product_category', 'bom', 'bom_item', 'routing',
            'task', 'material', 'item', 'uom', 'painting_process',
            'painting_stage',
        ]
        missing_types = [t for t in expected_types if t not in all_map_types]

        # BusinessEvent category coverage
        v1_event_count = V1ProductionEvent.objects.count()
        v2_event_count = BusinessEvent.objects.filter(
            legacy_app='product', legacy_model='ProductionEvent'
        ).count()

        return {
            'entity_comparisons': results,
            'migration_map_types_found': all_map_types,
            'migration_map_types_missing': missing_types,
            'business_event_migration': {
                'v1_events': v1_event_count,
                'v2_events_tagged_legacy': v2_event_count,
            },
            'audit_log_count': AuditLog.objects.count(),
            'summary': self._summarize(results),
        }

    def _summarize(self, results):
        total_v1 = sum(r['v1_count'] for r in results)
        total_v2 = sum(r['v2_count'] for r in results)
        fully_reconciled = sum(1 for r in results if r['reconciled'])
        return {
            'total_v1_count': total_v1,
            'total_v2_count': total_v2,
            'fully_reconciled_entities': fully_reconciled,
            'total_entities': len(results),
        }

    def print_report(self, report):
        self.stdout.write(self.style.NOTICE('=== V1-V2 Reconciliation Report ==='))
        self.stdout.write('')

        self.stdout.write(self.style.WARNING('Entity Comparisons:'))
        for r in report['entity_comparisons']:
            status = self.style.SUCCESS('RECONCILED') if r['reconciled'] else self.style.ERROR('MISMATCH')
            self.stdout.write(
                f'  {r["entity"]:20s} V1: {r["v1_count"]:>8d}  V2: {r["v2_count"]:>8d}  '
                f'Map: {r["migration_map_entries"]:>6d}  {status}'
            )

        self.stdout.write('')
        if report['migration_map_types_missing']:
            self.stdout.write(self.style.ERROR(
                f'Missing migration map types: {report["migration_map_types_missing"]}'
            ))
        else:
            self.stdout.write(self.style.SUCCESS('All expected migration map types present.'))

        be = report['business_event_migration']
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('Business Event Migration:'))
        self.stdout.write(
            f'  V1 ProductionEvents: {be["v1_events"]}  '
            f'V2 Events (legacy-tagged): {be["v2_events_tagged_legacy"]}'
        )
        self.stdout.write(f'  AuditLog entries: {report["audit_log_count"]}')

        s = report['summary']
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Summary: {s["fully_reconciled_entities"]}/{s["total_entities"]} entities reconciled'
        ))
