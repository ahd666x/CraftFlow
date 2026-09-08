"""
Versioned BOM/Routing Service (Pilot).

Reads ProductBOM (V1) and converts it to a versioned V2 BOM snapshot.
Does NOT modify ProductBOM, color_material_map, or any V1 data.
"""

import logging
from decimal import Decimal

from django.db import transaction
from django.core.exceptions import ValidationError

from bom.models import BOM, BOMItem, BOMItemMaterialRule
from planning.models import Routing, RoutingOperation, RoutingDependency
from products.models import Product, ProductPart
from reporting.models import MigrationMap

logger = logging.getLogger(__name__)


def _v1_productbom_qs():
    """Lazy import to avoid circular dependency at module load."""
    from product.models import ProductBOM
    return ProductBOM.objects


class VersionedBOMService:
    """
    Build versioned V2 BOM/Routing snapshots from V1 ProductBOM.

    Rules:
    - V1 ProductBOM is read-only; never mutated.
    - color_material_map JSON is preserved as-is and converted to a relationship proposal.
    - Ambiguous mappings produce warnings, never guesses.
    - Each snapshot carries an explicit version + effective_date.
    """

    @staticmethod
    def build_bom_snapshot(product, revision=None, effective_date=None):
        """
        Build a versioned BOM snapshot for a product.

        Returns dict with:
            - product, revision, effective_date
            - parts: list of {part, quantity, color_part, material_rules}
            - warnings: list of ambiguity warnings
            - source: 'v1_productbom'
        """
        warnings = []
        parts_data = []

        v1_bom_entries = list(
            _v1_productbom_qs()
            .filter(product=product)
            .select_related('part', 'part__material')
        )

        if not v1_bom_entries:
            warnings.append(f"product {product.id} has no ProductBOM entries")

        for entry in v1_bom_entries:
            part_data = VersionedBOMService._convert_bom_entry(entry, warnings)
            parts_data.append(part_data)

        snapshot = {
            'product': product.id,
            'revision': revision or 'A',
            'effective_date': effective_date,
            'parts': parts_data,
            'warnings': warnings,
            'source': 'v1_productbom',
        }
        return snapshot

    @staticmethod
    def _convert_bom_entry(entry, warnings):
        """Convert a V1 ProductBOM entry to a V2 BOMItem proposal."""
        material_rules = []

        color_map = entry.color_material_map or {}
        if entry.allow_material_override and color_map:
            for color_code, material_ids in color_map.items():
                if not isinstance(material_ids, list):
                    warnings.append(
                        f"ambiguous color_material_map for part {entry.part.id}: "
                        f"expected list for color {color_code}, got {type(material_ids).__name__}"
                    )
                    continue
                for mid in material_ids:
                    material_rules.append({
                        'rule_type': 'color_override',
                        'condition': color_code,
                        'material_id': mid,
                        'is_primary': True,
                        'priority': 0,
                    })
        elif entry.allow_material_override and not color_map:
            warnings.append(
                f"part {entry.part.id} has allow_material_override=True but empty color_material_map"
            )

        return {
            'part': entry.part.id,
            'quantity': entry.quantity,
            'color_part': entry.color_part,
            'allow_material_override': entry.allow_material_override,
            'size_affected': entry.size_affected,
            'size_adjustment_rule': entry.size_adjustment_rule,
            'material_rules': material_rules,
        }

    @staticmethod
    def build_routing_snapshot(product, revision=None, effective_date=None):
        """
        Build a versioned Routing snapshot from V1 routing data.

        V1 has no explicit Routing model; routing is embedded in ProductBOM/part order.
        We derive a default linear routing from ProductBOM part order.
        """
        warnings = []
        operations = []

        v1_bom_entries = list(
            _v1_productbom_qs()
            .filter(product=product)
            .select_related('part')
            .order_by('id')
        )
        for idx, entry in enumerate(v1_bom_entries, start=1):
            operations.append({
                'sequence': idx,
                'operation_name': f"Process {entry.part.name}",
                'operation_code': f"OP-{idx:03d}",
                'part': entry.part.id,
                'quantity': entry.quantity,
            })

        snapshot = {
            'product': product.id,
            'revision': revision or 'A',
            'effective_date': effective_date,
            'operations': operations,
            'dependencies': [],
            'warnings': warnings,
            'source': 'v1_productbom_derived',
        }
        return snapshot

    @staticmethod
    def get_active_bom_revision(product):
        """Return the active BOM revision for a product, or None."""
        return BOM.objects.filter(product=product, is_active=True).order_by('-effective_date').first()

    @staticmethod
    def activate_revision(bom, user=None):
        """Activate a BOM revision; deactivates others for same product."""
        with transaction.atomic():
            BOM.objects.filter(product=bom.product).update(is_active=False)
            bom.is_active = True
            bom.save(update_fields=['is_active'])
            return bom

    @staticmethod
    def deactivate_revision(bom):
        """Deactivate a BOM revision."""
        bom.is_active = False
        bom.save(update_fields=['is_active'])
        return bom

    @staticmethod
    def create_bom_revision(product, revision, effective_date, description='', user=None):
        """Create a new BOM revision snapshot in V2 bom.BOM model."""
        with transaction.atomic():
            snapshot = VersionedBOMService.build_bom_snapshot(
                product, revision=revision, effective_date=effective_date
            )
            bom = BOM.objects.create(
                product=product,
                revision=revision,
                effective_date=effective_date,
                description=description,
                is_active=False,
                created_by=user,
            )
            for part_data in snapshot['parts']:
                bom_item = BOMItem.objects.create(
                    bom=bom,
                    part=ProductPart.objects.get(pk=part_data['part']),
                    quantity=part_data['quantity'],
                )
                for rule in part_data['material_rules']:
                    BOMItemMaterialRule.objects.create(
                        bom_item=bom_item,
                        rule_type=rule['rule_type'],
                        condition=rule.get('condition', ''),
                        material_id=rule['material_id'],
                        quantity=Decimal('1'),
                        is_primary=rule.get('is_primary', True),
                        priority=rule.get('priority', 0),
                    )
            return bom, snapshot

    @staticmethod
    def create_routing_revision(product, revision, effective_date, description='', user=None):
        """Create a new Routing revision snapshot in V2 planning.Routing model."""
        with transaction.atomic():
            snapshot = VersionedBOMService.build_routing_snapshot(
                product, revision=revision, effective_date=effective_date
            )
            routing = Routing.objects.create(
                product=product,
                revision=revision,
                name=f"Routing {revision}",
                effective_date=effective_date,
                status='draft',
                description=description,
                created_by=user,
            )
            for op_data in snapshot['operations']:
                RoutingOperation.objects.create(
                    routing=routing,
                    sequence=op_data['sequence'],
                    operation_name=op_data['operation_name'],
                    operation_code=op_data['operation_code'],
                    work_center=None,
                )
            return routing, snapshot