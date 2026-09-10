from django.db.models import Prefetch, Q
from .models import Package, PackageItem


class PackagingSelectors:
    """Read-only selectors for packaging models."""

    @staticmethod
    def get_package_with_items(package_id):
        return Package.objects.filter(pk=package_id).prefetch_related(
            'items'
        ).select_related('customer_order_item', 'production_order_item').first()

    @staticmethod
    def get_packages_for_order_item(order_item_id, status=None):
        qs = Package.objects.filter(customer_order_item_id=order_item_id)
        if status:
            qs = qs.filter(status=status)
        return qs.select_related('customer_order_item').order_by('-created_at')

    @staticmethod
    def get_ready_to_ship_packages():
        return Package.objects.filter(status='packed').select_related(
            'customer_order_item'
        ).order_by('created_at')

    @staticmethod
    def get_packaging_specs_for_product(product):
        return PackagingSpecification.objects.filter(
            product=product, is_active=True
        ).order_by('package_type')
