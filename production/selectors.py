from django.db.models import Count, Q, F, Case, When, Value, DecimalField
from decimal import Decimal
from .models import ProductionOrder, ProductionOrderItem, ProductionOperation, OperationAssignment, WIPUnit

class ProductionSelectors:
    @staticmethod
    def get_production_queue():
        return ProductionOrder.objects.filter(
            status__in=['planned', 'released', 'in_progress']
        ).select_related('order', 'routing').prefetch_related('items__product')

    @staticmethod
    def get_ready_operations():
        return ProductionOperation.objects.filter(
            status='ready'
        ).select_related(
            'production_order', 'production_order_item', 'work_center'
        ).order_by('planned_start')

    @staticmethod
    def get_worker_schedule(worker, date_from, date_to):
        return OperationAssignment.objects.filter(
            worker=worker,
            operation__planned_start__date__gte=date_from,
            operation__planned_start__date__lte=date_to,
        ).select_related('operation', 'operation__production_order').order_by('operation__planned_start')

    @staticmethod
    def get_order_timeline(production_order):
        operations = ProductionOperation.objects.filter(
            production_order=production_order
        ).select_related('work_center').prefetch_related('assignments__worker')
        return operations.order_by('sequence')

    @staticmethod
    def get_wip_summary():
        return WIPUnit.objects.values('production_order__order__customer__name').annotate(
            total=Count('id'),
            in_progress=Count('id', filter=Q(status='in_progress')),
            completed=Count('id', filter=Q(status='completed')),
            scrapped=Count('id', filter=Q(status='scrapped')),
        )
