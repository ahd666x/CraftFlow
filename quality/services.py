from django.db import transaction
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType

from .models import QualityInspection, QualityDefect, ReworkOrder, ReworkOrderItem
from reporting.models import BusinessEvent, AuditLog


class QualityService:
    """Service layer for quality inspection and rework operations."""

    @staticmethod
    def create_inspection(production_order, inspection_type, result, inspected_by, **kwargs):
        with transaction.atomic():
            inspection = QualityInspection.objects.create(
                inspection_number=kwargs.pop('inspection_number', None) or QualityService._generate_inspection_number(),
                inspection_type=inspection_type,
                production_order=production_order,
                result=result,
                inspected_by=inspected_by,
                inspected_at=kwargs.pop('inspected_at', timezone.now()),
                **kwargs,
            )
            QualityService._log_event(inspection, 'created', inspected_by)
            return inspection

    @staticmethod
    def _generate_inspection_number():
        from django.db.models import Max
        prefix = 'QI-'
        today = timezone.now().strftime('%Y%m%d')
        last = QualityInspection.objects.filter(
            inspection_number__startswith=f'{prefix}{today}'
        ).aggregate(Max('inspection_number'))['inspection_number__max']
        seq = int(last.split('-')[-1]) + 1 if last else 1
        return f'{prefix}{today}-{seq:04d}'

    @staticmethod
    def add_defect(inspection, code, description, severity='minor', quantity=1, **kwargs):
        with transaction.atomic():
            defect = QualityDefect.objects.create(
                quality_inspection=inspection,
                code=code,
                description=description,
                severity=severity,
                quantity=quantity,
                **kwargs,
            )
            QualityService._log_event(defect, 'created', kwargs.get('created_by', None))
            return defect

    @staticmethod
    def create_rework_order(production_order, production_operation, quality_inspection,
                            defect_description, repair_description, quantity, assigned_to=None, **kwargs):
        with transaction.atomic():
            rework = ReworkOrder.objects.create(
                rework_number=kwargs.pop('rework_number', None) or QualityService._generate_rework_number(),
                production_order=production_order,
                production_operation=production_operation,
                quality_inspection=quality_inspection,
                defect_description=defect_description,
                repair_description=repair_description,
                quantity=quantity,
                assigned_to=assigned_to,
                **kwargs,
            )
            QualityService._log_event(rework, 'created', kwargs.get('created_by', None))
            return rework

    @staticmethod
    def _generate_rework_number():
        from django.db.models import Max
        prefix = 'RWO-'
        today = timezone.now().strftime('%Y%m%d')
        last = ReworkOrder.objects.filter(
            rework_number__startswith=f'{prefix}{today}'
        ).aggregate(Max('rework_number'))['rework_number__max']
        seq = int(last.split('-')[-1]) + 1 if last else 1
        return f'{prefix}{today}-{seq:04d}'

    @staticmethod
    def start_rework(rework_order, user):
        with transaction.atomic():
            rework_order.status = 'in_progress'
            rework_order.actual_start = timezone.now()
            rework_order.save(update_fields=['status', 'actual_start'])
            QualityService._log_event(rework_order, 'started', user)
            return rework_order

    @staticmethod
    def complete_rework(rework_order, user, completed_quantity):
        with transaction.atomic():
            if completed_quantity > rework_order.quantity:
                raise ValueError("completed_quantity cannot exceed quantity")
            rework_order.status = 'completed'
            rework_order.completed_quantity = completed_quantity
            rework_order.actual_end = timezone.now()
            rework_order.save(update_fields=['status', 'completed_quantity', 'actual_end'])
            QualityService._log_event(rework_order, 'completed', user)
            return rework_order

    @staticmethod
    def _log_event(content_object, event_type, user):
        BusinessEvent.objects.create(
            category='quality',
            event_type=event_type,
            title=f'{content_object.__class__.__name__} {event_type}',
            description=str(content_object),
            occurred_at=timezone.now(),
            created_by=user,
            content_object=content_object,
        )
