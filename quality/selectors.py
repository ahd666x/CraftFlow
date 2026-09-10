from django.db.models import Prefetch, Q
from django.utils import timezone
from datetime import timedelta

from .models import QualityInspection, QualityDefect, ReworkOrder, ReworkOrderItem
from production.models import ProductionOperation


class QualitySelectors:
    """Read-only selectors for quality models."""

    @staticmethod
    def get_inspections_for_order(production_order, inspection_type=None, result=None):
        qs = QualityInspection.objects.filter(production_order=production_order)
        if inspection_type:
            qs = qs.filter(inspection_type=inspection_type)
        if result:
            qs = qs.filter(result=result)
        return qs.select_related('production_order', 'inspected_by')

    @staticmethod
    def get_inspection_with_defects(inspection_id):
        return QualityInspection.objects.filter(pk=inspection_id).prefetch_related(
            Prefetch('defects', queryset=QualityDefect.objects.order_by('-severity', 'code'))
        ).first()

    @staticmethod
    def get_rework_orders_for_order(production_order, status=None):
        qs = ReworkOrder.objects.filter(production_order=production_order)
        if status:
            qs = qs.filter(status=status)
        return qs.select_related('production_order', 'assigned_to')

    @staticmethod
    def get_rework_order_with_items(rework_order_id):
        return ReworkOrder.objects.filter(pk=rework_order_id).prefetch_related(
            Prefetch('items', queryset=ReworkOrderItem.objects.select_related('quality_defect'))
        ).first()

    @staticmethod
    def get_defective_operations(production_order):
        """Get operations that have had quality defects."""
        return ProductionOperation.objects.filter(
            quality_inspections__result='fail'
        ).distinct()

    @staticmethod
    def get_recent_inspections(days=7, result=None):
        cutoff = timezone.now() - timedelta(days=days)
        qs = QualityInspection.objects.filter(inspected_at__gte=cutoff)
        if result:
            qs = qs.filter(result=result)
        return qs.select_related('production_order').order_by('-inspected_at')

    @staticmethod
    def get_defect_summary(production_order):
        """Aggregate defect counts by severity for an order."""
        from django.db.models import Count
        return (
            QualityInspection.objects
            .filter(production_order=production_order)
            .values('defects__severity')
            .annotate(count=Count('defects'))
            .order_by('defects__severity')
        )
