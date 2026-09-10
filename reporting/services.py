from django.db import transaction
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType

from .models import BusinessEvent, AuditLog


class EventService:
    """Service for creating and managing business events."""

    @staticmethod
    def log_event(category, event_type, title, user=None, content_object=None,
                  description='', metadata=None, correlation_id='', **kwargs):
        with transaction.atomic():
            event = BusinessEvent.objects.create(
                category=category,
                event_type=event_type,
                title=title,
                description=description,
                occurred_at=kwargs.pop('occurred_at', timezone.now()),
                created_by=user,
                metadata=metadata or {},
                correlation_id=correlation_id,
                content_object=content_object,
            )
            return event

    @staticmethod
    def log_production_event(event_type, operation, user=None, **kwargs):
        return EventService.log_event(
            category='production',
            event_type=event_type,
            title=f'Production {event_type}: {operation}',
            description=kwargs.get('description', ''),
            user=user,
            content_object=operation,
        )

    @staticmethod
    def log_inventory_event(event_type, item, user=None, **kwargs):
        return EventService.log_event(
            category='inventory',
            event_type=event_type,
            title=f'Inventory {event_type}: {item}',
            description=kwargs.get('description', ''),
            user=user,
            content_object=item,
        )

    @staticmethod
    def log_quality_event(event_type, inspection, user=None, **kwargs):
        return EventService.log_event(
            category='quality',
            event_type=event_type,
            title=f'Quality {event_type}: {inspection}',
            description=kwargs.get('description', ''),
            user=user,
            content_object=inspection,
        )

    @staticmethod
    def log_painting_event(event_type, operation, user=None, **kwargs):
        return EventService.log_event(
            category='painting',
            event_type=event_type,
            title=f'Painting {event_type}: {operation}',
            description=kwargs.get('description', ''),
            user=user,
            content_object=operation,
        )

    @staticmethod
    def log_shipping_event(event_type, shipment, user=None, **kwargs):
        return EventService.log_event(
            category='shipping',
            event_type=event_type,
            title=f'Shipping {event_type}: {shipment}',
            description=kwargs.get('description', ''),
            user=user,
            content_object=shipment,
        )

    @staticmethod
    def log_with_correlation(correlation_id, category, event_type, title, user=None,
                             content_object=None, **kwargs):
        return EventService.log_event(
            category=category,
            event_type=event_type,
            title=title,
            user=user,
            content_object=content_object,
            correlation_id=correlation_id,
            **kwargs,
        )


class AuditService:
    """Service for creating audit log entries."""

    @staticmethod
    def log(user, action, model_name, object_id, object_repr='', changes=None,
            ip_address='', user_agent='', **kwargs):
        with transaction.atomic():
            audit = AuditLog.objects.create(
                user=user,
                action=action,
                model_name=model_name,
                object_id=str(object_id) if object_id else '',
                object_repr=object_repr,
                changes=changes or {},
                ip_address=ip_address or None,
                user_agent=user_agent,
            )
            return audit

    @staticmethod
    def log_create(user, model_name, instance, changes=None, ip_address='', user_agent=''):
        return AuditService.log(
            user=user,
            action='create',
            model_name=model_name,
            object_id=instance.pk,
            object_repr=str(instance),
            changes=changes or {},
            ip_address=ip_address,
            user_agent=user_agent,
        )

    @staticmethod
    def log_update(user, model_name, instance, changes, ip_address='', user_agent=''):
        return AuditService.log(
            user=user,
            action='update',
            model_name=model_name,
            object_id=instance.pk,
            object_repr=str(instance),
            changes=changes,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    @staticmethod
    def log_delete(user, model_name, object_repr, object_id, ip_address='', user_agent=''):
        return AuditService.log(
            user=user,
            action='delete',
            model_name=model_name,
            object_id=object_id,
            object_repr=object_repr,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    @staticmethod
    def log_status_change(user, model_name, instance, old_status, new_status, ip_address='', user_agent=''):
        changes = {'old_status': old_status, 'new_status': new_status}
        return AuditService.log(
            user=user,
            action='update',
            model_name=model_name,
            object_id=instance.pk,
            object_repr=str(instance),
            changes=changes,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    @staticmethod
    def log_assignment(user, model_name, instance, old_worker=None, new_worker=None, ip_address='', user_agent=''):
        changes = {}
        if old_worker is not None:
            changes['old_worker'] = str(old_worker)
        if new_worker is not None:
            changes['new_worker'] = str(new_worker)
        return AuditService.log(
            user=user,
            action='assign',
            model_name=model_name,
            object_id=instance.pk,
            object_repr=str(instance),
            changes=changes,
            ip_address=ip_address,
            user_agent=user_agent,
        )
