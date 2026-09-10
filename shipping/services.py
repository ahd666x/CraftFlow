from django.db import transaction
from django.utils import timezone

from .models import Shipment, ShipmentItem


class ShippingService:
    """Service layer for shipping operations."""

    @staticmethod
    def create_shipment(customer_order, shipped_by=None, **kwargs):
        with transaction.atomic():
            shipment_number = kwargs.pop('shipment_number', None) or f'SO-{Shipment.objects.count() + 1:06d}'

            shipment = Shipment.objects.create(
                shipment_number=shipment_number,
                customer_order=customer_order,
                customer=getattr(customer_order, 'customer', None),
                status='ready',
                created_by=shipped_by,
                shipment_date=timezone.now().date() if shipped_by else None,
                **kwargs,
            )

            from reporting.services import EventService
            EventService.log_event(
                category='shipping',
                event_type='created',
                title=f'Shipment created: {shipment.shipment_number}',
                user=shipped_by,
                content_object=shipment,
            )
            return shipment

    @staticmethod
    def add_shipment_item(shipment, package, quantity, **kwargs):
        with transaction.atomic():
            return ShipmentItem.objects.create(
                shipment=shipment,
                package=package,
                quantity=quantity,
                **kwargs,
            )

    @staticmethod
    def mark_in_transit(shipment, tracking_number=None):
        with transaction.atomic():
            shipment.status = 'in_transit'
            if tracking_number:
                shipment.tracking_number = tracking_number
            shipment.save(update_fields=['status', 'tracking_number'])
            return shipment

    @staticmethod
    def mark_delivered(shipment):
        with transaction.atomic():
            shipment.status = 'delivered'
            shipment.delivery_date = timezone.now().date()
            shipment.save(update_fields=['status', 'delivery_date'])
            return shipment
