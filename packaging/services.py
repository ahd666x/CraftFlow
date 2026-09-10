from django.db import transaction
from django.utils import timezone

from .models import Package, PackageItem


class PackagingService:
    """Service layer for packaging operations."""

    @staticmethod
    def create_package(customer_order_item=None, production_order_item=None,
                       wip_unit=None, package_number=None, packed_by=None, **kwargs):
        with transaction.atomic():
            if not package_number:
                count = Package.objects.count() + 1
                package_number = f'PKG-{count:06d}'

            package = Package.objects.create(
                customer_order_item=customer_order_item,
                production_order_item=production_order_item,
                wip_unit=wip_unit,
                package_number=package_number,
                packed_by=packed_by,
                packed_at=timezone.now(),
                status='packed',
                **kwargs,
            )

            from reporting.services import EventService
            EventService.log_event(
                category='packaging',
                event_type='created',
                title=f'Package created: {package.package_number}',
                user=packed_by,
                content_object=package,
            )
            return package

    @staticmethod
    def add_package_item(package, item, quantity, **kwargs):
        with transaction.atomic():
            return PackageItem.objects.create(
                package=package,
                item=item,
                quantity=quantity,
                **kwargs,
            )

    @staticmethod
    def get_package_by_id(package_id):
        from .selectors import PackagingSelectors
        return PackagingSelectors.get_package_with_items(package_id)

    @staticmethod
    def ship_package(package, shipped_by=None):
        with transaction.atomic():
            package.status = 'shipped'
            package.save(update_fields=['status'])
            return package
