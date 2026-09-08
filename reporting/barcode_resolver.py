"""
Legacy-compatible Barcode/QR Resolver.

This module resolves QR codes and barcodes to their target entities.
It preserves all legacy QR formats without regenerating or modifying them.

Legacy QR contracts:
- OrderItem QR: {SCAN_BASE_URL}/scan/{OrderItem.id}/
- PackagingUnit QR: {SCAN_BASE_URL}/scan/packaging_unit/{PackagingUnit.id}/?next=/item_detail/{OrderItem.id}/

The resolver is read-only: it never mutates inventory, production, or WIP.
"""

import logging
from django.urls import reverse, NoReverseMatch
from django.http import Http404

from product.models import OrderItem, PackagingUnit
from reporting.models import MigrationMap

logger = logging.getLogger(__name__)


class BarcodeResolver:
    """
    Resolve barcode/QR payloads to their target entities.

    Resolution order:
    1. Legacy OrderItem QR URL
    2. Legacy PackagingUnit QR URL
    3. Direct ID scan (fallback)
    4. MigrationMap lookup for V2 entity metadata
    """

    # Known legacy URL patterns
    LEGACY_ORDER_ITEM_PATTERN = '/scan/'
    LEGACY_PACKAGING_UNIT_PATTERN = '/scan/packaging_unit/'

    @staticmethod
    def resolve(payload):
        """
        Resolve a barcode/QR payload to entity information.

        Args:
            payload: str - The QR data (URL, ID, or raw payload)

        Returns:
            dict with keys:
                - 'entity_type': 'order_item' | 'packaging_unit' | 'unknown'
                - 'entity_id': int or None
                - 'entity': model instance or None
                - 'legacy': bool
                - 'v2_metadata': dict or None (if MigrationMap exists)
                - 'resolved_url': str or None
        """
        result = {
            'entity_type': 'unknown',
            'entity_id': None,
            'entity': None,
            'legacy': False,
            'v2_metadata': None,
            'resolved_url': None,
        }

        if not payload:
            return result

        # Try legacy OrderItem URL pattern
        order_item_id = BarcodeResolver._extract_order_item_id(payload)
        if order_item_id:
            try:
                item = OrderItem.objects.get(pk=order_item_id)
                result['entity_type'] = 'order_item'
                result['entity_id'] = item.id
                result['entity'] = item
                result['legacy'] = True
                result['resolved_url'] = reverse('scan_qr', args=[item.id])
                result['v2_metadata'] = BarcodeResolver._get_v2_metadata('order_item', item.id)
                return result
            except OrderItem.DoesNotExist:
                pass

        # Try legacy PackagingUnit URL pattern
        packaging_unit_id = BarcodeResolver._extract_packaging_unit_id(payload)
        if packaging_unit_id:
            try:
                pu = PackagingUnit.objects.get(pk=packaging_unit_id)
                result['entity_type'] = 'packaging_unit'
                result['entity_id'] = pu.id
                result['entity'] = pu
                result['legacy'] = True
                result['resolved_url'] = reverse('scan_packaging_unit', args=[pu.id])
                result['v2_metadata'] = BarcodeResolver._get_v2_metadata('packaging_unit', pu.id)
                return result
            except PackagingUnit.DoesNotExist:
                pass

        # Try direct integer ID fallback (for raw QR data that's just an ID)
        try:
            raw_id = int(payload.strip())
            # Try OrderItem first
            try:
                item = OrderItem.objects.get(pk=raw_id)
                result['entity_type'] = 'order_item'
                result['entity_id'] = item.id
                result['entity'] = item
                result['legacy'] = True
                result['resolved_url'] = reverse('scan_qr', args=[item.id])
                result['v2_metadata'] = BarcodeResolver._get_v2_metadata('order_item', item.id)
                return result
            except OrderItem.DoesNotExist:
                pass

            # Try PackagingUnit
            try:
                pu = PackagingUnit.objects.get(pk=raw_id)
                result['entity_type'] = 'packaging_unit'
                result['entity_id'] = pu.id
                result['entity'] = pu
                result['legacy'] = True
                result['resolved_url'] = reverse('scan_packaging_unit', args=[pu.id])
                result['v2_metadata'] = BarcodeResolver._get_v2_metadata('packaging_unit', pu.id)
                return result
            except PackagingUnit.DoesNotExist:
                pass
        except (ValueError, TypeError):
            pass

        return result

    @staticmethod
    def _extract_order_item_id(payload):
        """Extract OrderItem ID from legacy scan URL."""
        if not isinstance(payload, str):
            return None
        # Pattern: /scan/{id}/ or {base}/scan/{id}/
        import re
        match = re.search(r'/scan/(\d+)/?$', payload)
        if match:
            return int(match.group(1))
        return None

    @staticmethod
    def _extract_packaging_unit_id(payload):
        """Extract PackagingUnit ID from legacy scan URL."""
        if not isinstance(payload, str):
            return None
        import re
        match = re.search(r'/scan/packaging_unit/(\d+)/?', payload)
        if match:
            return int(match.group(1))
        return None

    @staticmethod
    def _get_v2_metadata(entity_type, legacy_id):
        """Look up MigrationMap for V2 metadata."""
        try:
            mapping = MigrationMap.objects.filter(
                migration_type=entity_type,
                old_id=legacy_id,
                is_legacy=True,
            ).first()
            if mapping:
                return {
                    'v2_model': mapping.new_model,
                    'v2_id': mapping.new_id,
                    'migration_run': str(mapping.migration_run) if mapping.migration_run else None,
                }
        except Exception:
            pass
        return None

    @staticmethod
    def is_legacy_payload(payload):
        """Check if payload matches any known legacy QR format."""
        result = BarcodeResolver.resolve(payload)
        return result['legacy']

    @staticmethod
    def get_scan_url(entity_type, entity_id):
        """Get the scan URL for a given entity type and ID."""
        if entity_type == 'order_item':
            return reverse('scan_qr', args=[entity_id])
        elif entity_type == 'packaging_unit':
            return reverse('scan_packaging_unit', args=[entity_id])
        return None