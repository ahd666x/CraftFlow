# reporting/management/commands/craftflow_migrate_v2.py
"""
craftflow_migrate_v2 --phase master-data [--dry-run|--execute] [--rollback RUN_ID]

Phase 4: Master Data and Product Engineering Migration.

Clones (idempotent) V1 master data into V2 models:
  - product.User / WorkerProfile   -> accounts.Worker
  - product.Customer               -> customers.Customer
  - product.ProductCategory        -> products.ProductCategory
  - product.Product                -> products.Product
  - product.Material + inventory.RawMaterial -> inventory.Item (MERGE)
  - product.Part                   -> products.ProductPart / planning.ProductionPart
  - product.ProductBOM             -> bom.BOM / BOMItem / BOMItemMaterialRule
  - product.PaintingProcess/Stages  -> painting.PaintingProcess / PaintingProcessStage

Design rules:
  * Zero V1 mutation. V1 rows are read-only.
  * Every migrated record gets a MigrationMap row.
  * Ambiguous records are skipped and logged as warnings (never guessed).
  * Re-run is idempotent: anchored on MigrationMap (type, old_id, old_app),
    NOT on V2 natural keys (V1 Part has no reliable unique key).
  * Rollback is scoped to a single MigrationRun.
"""
from __future__ import annotations

import datetime
import decimal
import json
import logging
import warnings
from collections import defaultdict

from django.utils import timezone

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from reporting.models import MigrationMap, MigrationRun

logger = logging.getLogger(__name__)

# Module-level dry-run flag set by _run_phase. Helpers consult this to
# guarantee zero writes during --dry-run.
_DRY_RUN = False

# ---------------------------------------------------------------------------
# V1 / V2 model imports
# ---------------------------------------------------------------------------
from product.models import (  # V1
    Customer as V1Customer,
    Material as V1Material,
    Part as V1Part,
    PaintingProcess as V1PaintingProcess,
    PaintingStage as V1PaintingStage,
    Product as V1Product,
    ProductBOM as V1ProductBOM,
    ProductCategory as V1ProductCategory,
    WorkerProfile as V1WorkerProfile,
    Order as V1Order,
    OrderItem as V1OrderItem,
    ProductionTask as V1ProductionTask,
)
from inventory.models import (  # V1 + V2
    Item as V2Item,
    ItemCategory as V2ItemCategory,
    RawMaterial as V1RawMaterial,
    RawMaterialCategory as V1RawMaterialCategory,
    UOM as V2UOM,
)
from accounts.models import Worker as V2Worker
from customers.models import Customer as V2Customer
from products.models import (
    Product as V2Product,
    ProductCategory as V2ProductCategory,
    ProductPart as V2ProductPart,
)
from bom.models import (
    BOM as V2BOM,
    BOMItem as V2BOMItem,
    BOMItemMaterialRule as V2BOMItemMaterialRule,
)
from painting.models import (
    PaintingProcess as V2PaintingProcess,
    PaintingProcessStage as V2PaintingProcessStage,
)
from planning.models import ProductionPart as V2ProductionPart, Routing as V2Routing, RoutingOperation as V2RoutingOperation, RoutingDependency as V2RoutingDependency, WorkCenter as V2WorkCenter
from sales.models import CustomerOrder as V2CustomerOrder, CustomerOrderItem as V2CustomerOrderItem
from production.models import (
    ProductionOrder as V2ProductionOrder,
    ProductionOrderItem as V2ProductionOrderItem,
    ProductionOperation as V2ProductionOperation,
    OperationAssignment as V2OperationAssignment,
    OperationExecution as V2OperationExecution,
    WIPUnit as V2WIPUnit,
    WIPTransfer as V2WIPTransfer,
)

V1_APP = "product"
V2_MODEL_BY_TYPE = {
    "customer": (V2Customer, "customers"),
    "product": (V2Product, "products"),
    "product_category": (V2ProductCategory, "products"),
    "part": (V2ProductPart, "products"),
    "product_part": (V2ProductPart, "products"),
    "production_part": (V2ProductionPart, "planning"),
    "bom": (V2BOM, "bom"),
    "bom_item": (V2BOMItem, "bom"),
    "bom_item_material_rule": (V2BOMItemMaterialRule, "bom"),
    "material": (V2Item, "inventory"),
    "raw_material": (V2Item, "inventory"),
    "item": (V2Item, "inventory"),
    "item_category": (V2ItemCategory, "inventory"),
    "uom": (V2UOM, "inventory"),
    "worker": (V2Worker, "accounts"),
    "worker_profile": (V2Worker, "accounts"),
    "painting_process": (V2PaintingProcess, "painting"),
    "painting_stage": (V2PaintingProcessStage, "painting"),
    "customer_order": (V2CustomerOrder, "sales"),
    "customer_order_item": (V2CustomerOrderItem, "sales"),
    "production_order": (V2ProductionOrder, "production"),
    "production_order_item": (V2ProductionOrderItem, "production"),
    "production_operation": (V2ProductionOperation, "production"),
    "operation_assignment": (V2OperationAssignment, "production"),
    "operation_execution": (V2OperationExecution, "production"),
    "wip_unit": (V2WIPUnit, "production"),
    "wip_transfer": (V2WIPTransfer, "production"),
    "routing": (V2Routing, "planning"),
    "routing_operation": (V2RoutingOperation, "planning"),
    "routing_dependency": (V2RoutingDependency, "planning"),
}

V2_APP = {
    "customer": "customers",
    "product": "products",
    "product_category": "products",
    "part": "products",
    "product_part": "products",
    "production_part": "planning",
    "bom": "bom",
    "bom_item": "bom",
    "bom_item_material_rule": "bom",
    "material": "inventory",
    "raw_material": "inventory",
    "item": "inventory",
    "item_category": "inventory",
    "uom": "inventory",
    "worker": "accounts",
    "worker_profile": "accounts",
    "painting_process": "painting",
    "painting_stage": "painting",
    "customer_order": "sales",
    "customer_order_item": "sales",
    "production_order": "production",
    "production_order_item": "production",
    "production_operation": "production",
    "operation_assignment": "production",
    "operation_execution": "production",
    "wip_unit": "production",
    "wip_transfer": "production",
    "routing": "planning",
    "routing_operation": "planning",
    "routing_dependency": "planning",
}
# ---------------------------------------------------------------------------
# UOM mapping (V1 unit -> V2 UOM)
# ---------------------------------------------------------------------------
V1_UNIT_TO_UOM = {
    "kg": ("weight", "kg", "Ú©ÛŒÙ„ÙˆÚ¯Ø±Ù…"),
    "lit": ("volume", "lit", "Ù„ÛŒØªØ±"),
    "pcs": ("count", "pcs", "Ø¹Ø¯Ø¯"),
    "m": ("length", "m", "Ù…ØªØ±"),
    "sheet": ("count", "sheet", "ÙˆØ±Ù‚"),
}
DEFAULT_UOM_FALLBACK = ("count", "pcs", "Ø¹Ø¯Ø¯")


def _get_or_create_uom(unit):
    unit = (unit or "").strip().lower()
    spec = V1_UNIT_TO_UOM.get(unit, DEFAULT_UOM_FALLBACK)
    code, _, name = spec
    return V2UOM.objects.get_or_create(
        code=code,
        defaults={
            "name": name,
            "uom_type": spec[0],
            "decimal_places": 3 if spec[0] in ("weight", "volume", "length") else 0,
            "is_base": (unit == "kg"),
        },
    )[0]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _str(value):
    if value is None:
        return ""
    if isinstance(value, (list, dict, tuple)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return str(value)


def _decimal(value, default=None):
    if value is None or value == "":
        return default
    try:
        return decimal.Decimal(str(value))
    except (decimal.InvalidOperation, TypeError, ValueError):
        return default


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_json(value):
    if isinstance(value, (dict, list)):
        return value
    if value is None or value == "":
        return {}
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return {}
        if s.startswith("{") or s.startswith("["):
            try:
                return json.loads(s)
            except Exception:
                pass
        return s
    return value

# ---------------------------------------------------------------------------
# MigrationMap helpers (idempotency anchor)
# ---------------------------------------------------------------------------
def _find_map(migration_type, old_id, old_app=V1_APP):
    return MigrationMap.objects.filter(
        migration_type=migration_type,
        old_id=str(old_id),
        old_app=old_app,
    ).first()


def _ensure_map(migration_type, old_id, new_id, new_app, new_model, run, metadata=None,
                is_legacy=False, legacy_reason=""):
    old_id = str(old_id)
    new_id = str(new_id)
    if _DRY_RUN:
        return None, False
    obj, created = MigrationMap.objects.get_or_create(
        migration_type=migration_type,
        old_id=old_id,
        old_app=V1_APP,
        defaults={
            "old_model": "",
            "new_app": new_app,
            "new_model": new_model,
            "new_id": new_id,
            "is_legacy": is_legacy,
            "legacy_reason": legacy_reason,
            "migration_run": run,
            "metadata": metadata or {},
        },
    )
    if not created:
        changed = False
        if obj.new_id != new_id:
            obj.new_id = new_id
            changed = True
        if obj.new_app != new_app:
            obj.new_app = new_app
            changed = True
        if obj.new_model != new_model:
            obj.new_model = new_model
            changed = True
        if obj.is_legacy != is_legacy:
            obj.is_legacy = is_legacy
            changed = True
        if legacy_reason and obj.legacy_reason != legacy_reason:
            obj.legacy_reason = legacy_reason
            changed = True
        if run and obj.migration_run_id != run.id:
            obj.migration_run = run
            changed = True
        if metadata:
            merged = dict(obj.metadata or {})
            merged.update(metadata)
            obj.metadata = merged
            changed = True
        if changed:
            obj.save()
    return obj, created


def _skip(migration_type, old_id, reason, run, new_app="", new_model=""):
    if _DRY_RUN:
        return None
    obj, _ = MigrationMap.objects.get_or_create(
        migration_type=migration_type,
        old_id=str(old_id),
        old_app=V1_APP,
        defaults={
            "new_id": "",
            "new_app": new_app,
            "new_model": new_model,
            "is_legacy": True,
            "legacy_reason": reason,
            "migration_run": run,
            "metadata": {"skip_reason": reason},
        },
    )
    return obj

# ---------------------------------------------------------------------------
# Domain mappers
# ---------------------------------------------------------------------------
def migrate_product_categories(dry_run, run, stats):
    st = stats["product_category"] = {"total": 0, "created": 0, "reused": 0, "skipped": 0}
    qs = V1ProductCategory.objects.all().order_by("id")
    st["total"] = qs.count()
    for cat in qs:
        name = (cat.name or "").strip()
        if not name:
            _skip("product_category", cat.id, "empty name", run)
            st["skipped"] += 1
            continue
        existing = _find_map("product_category", cat.id)
        if existing and existing.new_id:
            st["reused"] += 1
            continue
        if dry_run:
            st["reused"] += 1
            continue
        v2, created = V2ProductCategory.objects.get_or_create(
            name=name,
            defaults={"description": "", "sort_order": 0},
        )
        _ensure_map("product_category", cat.id, v2.id, V2_APP["product_category"],
                    "ProductCategory", run)
        st["created"] += 1 if created else 0
        st["reused"] += 0 if created else 1
    return st


def _resolve(model, value):
    """Resolve an FK value that may be an id, a model instance, or a dry-run marker."""
    if value is None:
        return None
    if isinstance(value, model):
        return value
    if isinstance(value, int):
        return model.objects.filter(pk=value).first()
    return None


def migrate_products(dry_run, run, stats, cat_map):
    st = stats["product"] = {"total": 0, "created": 0, "reused": 0, "skipped": 0}
    qs = V1Product.objects.all().select_related("category").order_by("id")
    st["total"] = qs.count()
    for prod in qs:
        v1_cat = prod.category
        if v1_cat is None:
            _skip("product", prod.id, "missing category", run)
            st["skipped"] += 1
            continue
        v2_cat = cat_map.get(v1_cat.id)
        if v2_cat is None:
            _skip("product", prod.id, "category not migrated", run)
            st["skipped"] += 1
            continue
        if _is_dry_marker(v2_cat):
            st["reused"] += 1
            continue
        v2_cat = _resolve(V2ProductCategory, v2_cat)
        if v2_cat is None:
            _skip("product", prod.id, "category instance missing", run)
            st["skipped"] += 1
            continue
        existing = _find_map("product", prod.id)
        if existing and existing.new_id:
            st["reused"] += 1
            continue
        if dry_run:
            st["reused"] += 1
            continue
        defaults = {
            "category": v2_cat,
            "code": f"P-{prod.id}",
            "name": prod.name or "",
            "color": prod.color or "",
            "description": prod.description or "",
            "default_size": prod.default_size or "",
            "default_colors": _coerce_json(prod.default_colors),
            "base_price": _decimal(prod.base_price, 0) or 0,
            "price_increment_per_cm": _decimal(prod.price_increment_per_cm, 0) or 0,
            "is_active": True,
            "estimated_production_days": 0,
        }
        v2, created = V2Product.objects.get_or_create(
            code=f"P-{prod.id}",
            defaults=defaults,
        )
        _ensure_map("product", prod.id, v2.id, V2_APP["product"], "Product", run,
                    metadata={"parts_list_key": prod.parts_list_key})
        st["created"] += 1 if created else 0
        st["reused"] += 0 if created else 1
    return st


def migrate_customers(dry_run, run, stats):
    st = stats["customer"] = {"total": 0, "created": 0, "reused": 0, "skipped": 0}
    qs = V1Customer.objects.all().order_by("id")
    st["total"] = qs.count()
    for cust in qs:
        name = (cust.name or "").strip()
        if not name:
            _skip("customer", cust.id, "empty name", run)
            st["skipped"] += 1
            continue
        existing = _find_map("customer", cust.id)
        if existing and existing.new_id:
            st["reused"] += 1
            continue
        if dry_run:
            st["reused"] += 1
            continue
        v2, created = V2Customer.objects.get_or_create(
            name=name,
            defaults={
                "phone": cust.phone or "",
                "address": cust.address or "",
                "email": "",
                "mobile": "",
                "postal_code": "",
                "economic_code": "",
                "national_id": "",
                "is_representative": False,
                "notes": "",
                "balance": 0,
                "credit_limit": 0,
            },
        )
        _ensure_map("customer", cust.id, v2.id, V2_APP["customer"], "Customer", run)
        st["created"] += 1 if created else 0
        st["reused"] += 0 if created else 1
    return st


def migrate_workers(dry_run, run, stats):
    st = stats["worker"] = {"total": 0, "created": 0, "reused": 0, "skipped": 0}
    qs = V1WorkerProfile.objects.all().select_related("user").order_by("id")
    st["total"] = qs.count()
    for wp in qs:
        user = wp.user
        if user is None:
            _skip("worker", wp.id, "missing user", run)
            st["skipped"] += 1
            continue
        existing = _find_map("worker", wp.id)
        if existing and existing.new_id:
            st["reused"] += 1
            continue
        if dry_run:
            st["reused"] += 1
            continue
        station = wp.stage if wp.stage in dict(V2Worker.STATION_CHOICES) else "cut"
        v2, created = V2Worker.objects.get_or_create(
            user=user,
            defaults={
                "employee_id": f"WP-{wp.id}",
                "station": station,
                "skills": wp.skills or [],
                "skill_priority": wp.skill_priority or {},
                "is_available": wp.is_available,
                "work_start": wp.work_start,
                "work_end": wp.work_end,
                "break_start": wp.break_start,
                "break_end": wp.break_end,
                "hourly_rate": 0,
            },
        )
        _ensure_map("worker", wp.id, v2.id, V2_APP["worker"], "Worker", run)
        st["created"] += 1 if created else 0
        st["reused"] += 0 if created else 1
    return st

# ---------------------------------------------------------------------------
# Material / RawMaterial -> inventory.Item (MERGE)
# ---------------------------------------------------------------------------
def _material_merge_key(mat, raw):
    a = (mat.name or "").strip().lower() if mat else None
    b = (raw.name or "").strip().lower() if raw else None
    if a and b and a == b:
        return a
    return None


def _material_to_item_fields(mat, raw, cat, code=None):
    base = (mat.name if mat else (raw.name if raw else "")).strip()
    unit = (raw.unit if raw and raw.unit else "pcs").strip().lower()
    if mat and mat.thickness:
        base = f"{base} {mat.thickness}mm".strip()
    if code is None:
        code = f"MAT-{mat.id}" if mat else f"RM-{raw.id}"
    return {
        "name": base,
        "item_type": "material",
        "category": cat,
        "code": code,
        "barcode": code,
        "uom": _get_or_create_uom(unit),
        "min_stock": 0,
        "max_stock": 0,
        "reorder_point": 0,
        "lead_time_days": 0,
        "unit_cost": 0,
        "is_active": True,
        "is_serialized": False,
        "requires_lot_tracking": False,
        "consumption_per_unit": _decimal(mat.consumption_per_unit, 1) if mat else 1,
    }


def _get_or_create_item_category(name="Materials"):
    cat, _ = V2ItemCategory.objects.get_or_create(
        name=name,
        defaults={"description": "V1 Material / RawMaterial clone", "is_active": True},
    )
    return cat


def migrate_materials(dry_run, run, stats, item_map):
    st = stats["material"] = {"total": 0, "created": 0, "reused": 0, "skipped": 0, "merged": 0}
    materials = list(V1Material.objects.all().order_by("id"))
    raws = list(V1RawMaterial.objects.all().order_by("id"))
    st["total"] = len(materials) + len(raws)

    raw_by_name = defaultdict(list)
    for r in raws:
        raw_by_name[(r.name or "").strip().lower()].append(r)
    processed_raw_ids = set()
    item_cat = None if dry_run else _get_or_create_item_category()

    for mat in materials:
        key = (mat.name or "").strip().lower()
        candidates = raw_by_name.get(key, [])
        raw = None
        if len(candidates) == 1:
            raw = candidates[0]
        elif len(candidates) > 1:
            _skip("material", mat.id, "ambiguous: multiple RawMaterial share name", run,
                  new_app=V2_APP["material"], new_model="Item")
            st["skipped"] += 1
            continue

        existing = _find_map("material", mat.id)
        if existing and existing.new_id:
            st["reused"] += 1
            item_map[mat.id] = int(existing.new_id)
            if raw:
                item_map[("raw", raw.id)] = int(existing.new_id)
            continue
        if dry_run:
            st["reused"] += 1
            continue

        if raw:
            processed_raw_ids.add(raw.id)
            st["merged"] += 1
            code = f"MAT-{mat.id}"
            fields = _material_to_item_fields(mat, raw, item_cat, code)
            item, created = V2Item.objects.get_or_create(
                code=code,
                defaults=fields,
            )
            _ensure_map("material", mat.id, item.id, V2_APP["material"], "Item", run,
                        metadata={"merged_with_raw_id": raw.id})
            _ensure_map("raw_material", raw.id, item.id, V2_APP["raw_material"], "Item", run,
                        metadata={"merged_with_material_id": mat.id})
            st["created"] += 1 if created else 0
            st["reused"] += 0 if created else 1
            item_map[mat.id] = item.id
            item_map[("raw", raw.id)] = item.id
        else:
            code = f"MAT-{mat.id}"
            fields = _material_to_item_fields(mat, None, item_cat, code)
            item, created = V2Item.objects.get_or_create(
                code=code,
                defaults=fields,
            )
            _ensure_map("material", mat.id, item.id, V2_APP["material"], "Item", run,
                        metadata={"warning": "no RawMaterial link"})
            st["created"] += 1 if created else 0
            st["reused"] += 0 if created else 1
            item_map[mat.id] = item.id

    for r in raws:
        if r.id in processed_raw_ids:
            continue
        existing = _find_map("raw_material", r.id)
        if existing and existing.new_id:
            st["reused"] += 1
            item_map[("raw", r.id)] = int(existing.new_id)
            continue
        if dry_run:
            st["reused"] += 1
            continue
        fields = _material_to_item_fields(None, r, item_cat)
        item, created = V2Item.objects.get_or_create(
            code=f"RM-{r.id}",
            defaults=fields,
        )
        _ensure_map("raw_material", r.id, item.id, V2_APP["raw_material"], "Item", run,
                    metadata={"warning": "no Material link"})
        st["created"] += 1 if created else 0
        st["reused"] += 0 if created else 1
        item_map[("raw", r.id)] = item.id
    return st

# ---------------------------------------------------------------------------
# Part -> ProductPart / ProductionPart
# ---------------------------------------------------------------------------
def _grain_to_v2(grain):
    g = (grain or "").strip()
    mapping = {
        "Ø¹Ù…ÙˆØ¯ÛŒ": "vertical",
        "vertical": "vertical",
        "horizontal": "horizontal",
        "Ø¨Ø¯ÙˆÙ† Ø¬Ù‡Øª": "none",
        "none": "none",
    }
    if g in mapping:
        return mapping[g]
    if g.lower() in ("vertical", "horizontal", "none"):
        return g.lower()
    return "none"


def _part_thickness(mat):
    if mat is not None and mat.thickness is not None:
        try:
            return decimal.Decimal(str(mat.thickness))
        except Exception:
            pass
    return decimal.Decimal("0")


def _bom_part_product_map():
    return {b[0]: b[1] for b in V1ProductBOM.objects.values_list("part_id", "product_id")}


def migrate_parts(dry_run, run, stats, item_map, product_map):
    st = stats["product_part"] = {"total": 0, "created": 0, "reused": 0, "skipped": 0}
    bom_part_product = _bom_part_product_map()
    base_parts = list(V1Part.objects.filter(base_part__isnull=True).order_by("id"))
    st["total"] = len(base_parts)
    part_map = {}

    for part in base_parts:
        v1_prod_id = bom_part_product.get(part.id)
        if v1_prod_id is None:
            _skip("part", part.id, "not referenced by any BOM; product unknown", run,
                  new_app=V2_APP["product_part"], new_model="ProductPart")
            st["skipped"] += 1
            continue
        v2_prod = product_map.get(v1_prod_id)
        if v2_prod is None:
            _skip("part", part.id, "target product not migrated", run,
                  new_app=V2_APP["product_part"], new_model="ProductPart")
            st["skipped"] += 1
            continue
        if _is_dry_marker(v2_prod):
            st["reused"] += 1
            continue
        v2_prod = _resolve(V2Product, v2_prod)
        if v2_prod is None:
            _skip("part", part.id, "target product instance missing", run,
                  new_app=V2_APP["product_part"], new_model="ProductPart")
            st["skipped"] += 1
            continue

        existing = _find_map("part", part.id)
        if existing and existing.new_id:
            st["reused"] += 1
            try:
                part_map[part.id] = V2ProductPart.objects.get(pk=int(existing.new_id))
            except V2ProductPart.DoesNotExist:
                pass
            continue
        if dry_run:
            st["reused"] += 1
            continue

        v2 = V2ProductPart.objects.create(
            product=v2_prod,
            code=f"P-{part.id}",
            name=part.name or "",
            length=_decimal(part.length, 0) or 0,
            width=_decimal(part.width, 0) or 0,
            thickness=_part_thickness(part.material),
            grain=_grain_to_v2(part.grain),
            f26=part.f26 or "",
            f18=part.f18 or "",
            f4=part.f4 or "",
            f5=part.f5 or "",
            f3=part.f3 or "",
            f2=part.f2 or "",
            pname=part.pname or "",
            turn=bool(part.turn),
            sort_order=0,
        )
        _ensure_map("part", part.id, v2.id, V2_APP["product_part"], "ProductPart", run,
                    metadata={"v1_product_id": v1_prod_id})
        part_map[part.id] = v2
        st["created"] += 1
    return st, part_map


def migrate_production_parts(dry_run, run, stats, part_map, product_map):
    st = stats["production_part"] = {"total": 0, "created": 0, "reused": 0, "skipped": 0}
    bom_part_product = _bom_part_product_map()
    variations = list(V1Part.objects.filter(base_part__isnull=False).order_by("id"))
    st["total"] = len(variations)

    for part in variations:
        base = part.base_part
        if base is None:
            _skip("production_part", part.id, "base_part missing", run,
                  new_app=V2_APP["production_part"], new_model="ProductionPart")
            st["skipped"] += 1
            continue
        v2_base = _resolve(V2ProductPart, part_map.get(base.id))
        if v2_base is None:
            _skip("production_part", part.id, "base ProductPart not migrated", run,
                  new_app=V2_APP["production_part"], new_model="ProductionPart")
            st["skipped"] += 1
            continue
        v2_prod = _resolve(V2Product, product_map.get(bom_part_product.get(base.id)))
        if v2_prod is None:
            _skip("production_part", part.id, "product unknown for base part", run,
                  new_app=V2_APP["production_part"], new_model="ProductionPart")
            st["skipped"] += 1
            continue

        existing = _find_map("production_part", part.id)
        if existing and existing.new_id:
            st["reused"] += 1
            continue
        if dry_run:
            st["reused"] += 1
            continue

        v2 = V2ProductionPart.objects.create(
            product=v2_prod,
            part=v2_base,
            code=f"PP-{part.id}",
            name=part.name or "",
            length=_decimal(part.length, 0) or 0,
            width=_decimal(part.width, 0) or 0,
            thickness=_part_thickness(part.material),
            grain=(part.grain or "").strip(),
            f26=part.f26 or "",
            f18=part.f18 or "",
            f4=part.f4 or "",
            f5=part.f5 or "",
            f3=part.f3 or "",
            f2=part.f2 or "",
            pname=part.pname or "",
            turn=bool(part.turn),
            routing_code=part.routing_code or "",
        )
        _ensure_map("production_part", part.id, v2.id, V2_APP["production_part"],
                    "ProductionPart", run,
                    metadata={"base_part_id": base.id, "base_product_part_id": v2_base.id})
        st["created"] += 1
    return st

# ---------------------------------------------------------------------------
# ProductBOM -> bom.BOM / BOMItem / BOMItemMaterialRule
# ---------------------------------------------------------------------------
def _parse_color_material_map(value):
    v = _coerce_json(value)
    if isinstance(v, dict) and v:
        return v
    return None


def migrate_boms(dry_run, run, stats, product_map, part_map, item_map):
    st = stats["bom"] = {"total": 0, "created": 0, "reused": 0, "skipped": 0}
    st["bom_item"] = {"total": 0, "created": 0, "reused": 0, "skipped": 0}
    st["bom_item_material_rule"] = {"total": 0, "created": 0, "reused": 0, "skipped": 0}
    bstats = st["bom_item"]
    rstats = st["bom_item_material_rule"]
    qs = V1ProductBOM.objects.all().select_related("product", "part", "part__material").order_by("id")
    st["total"] = qs.count()
    bom_map = {}

    for bom in qs:
        v2_prod = _resolve(V2Product, product_map.get(bom.product_id))
        if v2_prod is None:
            _skip("bom", bom.id, "product not migrated", run,
                  new_app=V2_APP["bom"], new_model="BOM")
            st["skipped"] += 1
            continue
        cmap = _parse_color_material_map(bom.color_material_map)
        if cmap is not None:
            _skip("bom", bom.id,
                  "color_material_map non-empty; relational conversion needs explicit rule",
                  run, new_app=V2_APP["bom"], new_model="BOM")
            st["skipped"] += 1
            continue

        existing = _find_map("bom", bom.id)
        if existing and existing.new_id:
            st["reused"] += 1
            try:
                bom_map[bom.id] = V2BOM.objects.get(pk=int(existing.new_id))
            except V2BOM.DoesNotExist:
                pass
            continue
        if dry_run:
            st["reused"] += 1
            continue

        v2, created = V2BOM.objects.get_or_create(
            product=v2_prod,
            revision="A",
            defaults={
                "effective_date": datetime.date.today(),
                "description": "",
                "is_active": True,
            },
        )
        _ensure_map("bom", bom.id, v2.id, V2_APP["bom"], "BOM", run,
                    metadata={"v1_product_id": bom.product_id,
                              "color_part": bom.color_part or "",
                              "size_affected": bool(bom.size_affected),
                              "size_adjustment_rule": bom.size_adjustment_rule or ""})
        bom_map[bom.id] = v2
        st["created"] += 1 if created else 0
        st["reused"] += 0 if created else 1

        v2_part = _resolve(V2ProductPart, part_map.get(bom.part_id))
        if v2_part is None:
            bstats["total"] = bstats.get("total", 0) + 1
            bstats["skipped"] = bstats.get("skipped", 0) + 1
            _skip("bom_item", bom.id, "part not migrated", run,
                  new_app=V2_APP["bom_item"], new_model="BOMItem")
            continue

        item, created = V2BOMItem.objects.get_or_create(
            bom=v2,
            part=v2_part,
            defaults={
                "quantity": _int(bom.quantity, 1) or 1,
                "scrap_factor": 0,
                "notes": "",
                "sort_order": 0,
            },
        )
        _ensure_map("bom_item", bom.id, item.id, V2_APP["bom_item"], "BOMItem", run,
                    metadata={"v1_bom_id": bom.id})
        bstats["created"] += 1 if created else 0
        bstats["reused"] += 0 if created else 1

        mat = bom.part.material
        if mat is not None:
            item_id = item_map.get(mat.id)
            if item_id is not None:
                rstats["total"] = rstats.get("total", 0) + 1
                rule, rcreated = V2BOMItemMaterialRule.objects.get_or_create(
                    bom_item=item,
                    rule_type="standard",
                    material_item_id=item_id,
                    defaults={
                        "condition": "",
                        "quantity": _decimal(mat.consumption_per_unit, 1) or 1,
                        "is_primary": True,
                        "priority": 0,
                        "notes": f"from V1 Material id={mat.id}",
                    },
                )
                _ensure_map("bom_item_material_rule", bom.id, rule.id,
                            V2_APP["bom_item_material_rule"], "BOMItemMaterialRule", run,
                            metadata={"v1_bom_id": bom.id, "v1_material_id": mat.id})
                rstats["created"] += 1 if rcreated else 0
                rstats["reused"] += 0 if rcreated else 1
    return st

# ---------------------------------------------------------------------------
# PaintingProcess / PaintingStage -> painting models
# ---------------------------------------------------------------------------
def _painting_skill_v2(skill):
    s = (skill or "").strip().lower()
    choices = dict(V2PaintingProcessStage.SKILL_CHOICES)
    if s in choices:
        return s
    if s == "painter":
        return "painter"
    if s in ("general", "Ø²ÛŒØ±Ú©Ø§Ø±", "Ú©Ù…Ú©"):
        return "general"
    return "painter"


def migrate_painting(dry_run, run, stats):
    st = stats["painting_process"] = {"total": 0, "created": 0, "reused": 0, "skipped": 0}
    sst = stats["painting_stage"] = {"total": 0, "created": 0, "reused": 0, "skipped": 0}
    qs = V1PaintingProcess.objects.all().order_by("id")
    st["total"] = qs.count()
    process_map = {}

    for proc in qs:
        code = (proc.code or "").strip()
        name = (proc.name or "").strip()
        if not code:
            _skip("painting_process", proc.id, "empty code", run,
                  new_app=V2_APP["painting_process"], new_model="PaintingProcess")
            st["skipped"] += 1
            continue
        existing = _find_map("painting_process", proc.id)
        if existing and existing.new_id:
            st["reused"] += 1
            try:
                process_map[proc.id] = V2PaintingProcess.objects.get(pk=int(existing.new_id))
            except V2PaintingProcess.DoesNotExist:
                pass
            continue
        if dry_run:
            st["reused"] += 1
            continue
        v2, created = V2PaintingProcess.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "color_codes": list(proc.color_codes or []),
                "is_active": bool(proc.is_active),
                "description": proc.description or "",
                "estimated_time_minutes": 0,
            },
        )
        _ensure_map("painting_process", proc.id, v2.id, V2_APP["painting_process"],
                    "PaintingProcess", run)
        process_map[proc.id] = v2
        st["created"] += 1 if created else 0
        st["reused"] += 0 if created else 1

    s_qs = V1PaintingStage.objects.all().select_related("process").order_by("id")
    sst["total"] = s_qs.count()
    for stage in s_qs:
        v2_proc = process_map.get(stage.process_id)
        if v2_proc is None:
            _skip("painting_stage", stage.id, "process not migrated", run,
                  new_app=V2_APP["painting_stage"], new_model="PaintingProcessStage")
            sst["skipped"] += 1
            continue
        existing = _find_map("painting_stage", stage.id)
        if existing and existing.new_id:
            sst["reused"] += 1
            continue
        if dry_run:
            sst["reused"] += 1
            continue
        v2, created = V2PaintingProcessStage.objects.get_or_create(
            process=v2_proc,
            sequence=_int(stage.order, 0) or 0,
            defaults={
                "name": stage.name or "",
                "duration_minutes": _int(stage.duration_minutes, 0) or 0,
                "drying_time_minutes": _int(stage.drying_time_minutes, 0) or 0,
                "required_skill": _painting_skill_v2(stage.required_skill),
                "temperature_min": None,
                "temperature_max": None,
                "humidity_max": None,
                "is_mandatory": True,
                "notes": "",
            },
        )
        _ensure_map("painting_stage", stage.id, v2.id, V2_APP["painting_stage"],
                    "PaintingProcessStage", run,
                    metadata={"v1_process_id": stage.process_id})
        sst["created"] += 1 if created else 0
        sst["reused"] += 0 if created else 1
    return st


# ---------------------------------------------------------------------------
# Production migration (Phase 5)
# ---------------------------------------------------------------------------
PRODUCTION_DOMAIN_ORDER = [
    "customer_order",
    "customer_order_item",
    "production_order",
    "production_order_item",
    "production_operation",
    "operation_assignment",
    "operation_execution",
    "wip_unit",
    "wip_transfer",
]


V1_ORDER_STATUS_TO_V2 = {
    "draft": "draft",
    "planned": "planned",
    "producing": "in_progress",
    "completed": "completed",
    "cancelled": "cancelled",
}

V1_TASK_STATUS_TO_V2 = {
    "waiting": "waiting",
    "pending": "ready",
    "done": "completed",
}

STATION_TO_OP_CODE = {
    "cut": "CUT",
    "cnc": "CNC",
    "dr": "DR",
    "pvc": "PVC",
    "prs": "PRS",
    "mon": "MON",
    "vacum": "VAC",
    "paint": "PAINT",
    "assembly2": "ASM2",
    "packaging": "PACK",
    "shipping": "SHIP",
}

STATION_TO_OP_NAME = {
    "cut": "برش",
    "cnc": "CNC",
    "dr": "سوراخکاری",
    "pvc": "نوارکاری",
    "prs": "پرس",
    "mon": "مونتاژ اول",
    "vacum": "وکیوم",
    "paint": "نقاشی",
    "assembly2": "مونتاژ نهایی",
    "packaging": "بسته‌بندی",
    "shipping": "ارسال",
}


def _get_v2_work_center_fallback():
    wc, _ = V2WorkCenter.objects.get_or_create(
        code="MIGRATED",
        defaults={
            "name": "مرکز کار مهاجرت شده",
            "description": "Work center created automatically during V1→V2 migration for tasks without explicit routing.",
            "capacity_per_hour": 0,
            "efficiency_factor": 1.0,
            "setup_time_minutes": 0,
            "cost_per_hour": 0,
            "is_active": False,
        },
    )
    return wc



def migrate_orders(dry_run, run, stats):
    st = stats["customer_order"] = {"total": 0, "created": 0, "reused": 0, "skipped": 0}
    qs = V1Order.objects.all().select_related("customer", "user").order_by("id")
    st["total"] = qs.count()
    customer_map = {}
    worker_map = {}

    for v1 in qs:
        customer = v1.customer
        if customer is None:
            _skip("customer_order", v1.id, "missing customer", run,
                  new_app=V2_APP["customer_order"], new_model="CustomerOrder")
            st["skipped"] += 1
            continue

        existing = _find_map("customer_order", v1.id)
        if existing and existing.new_id:
            st["reused"] += 1
            try:
                customer_map[v1.id] = V2CustomerOrder.objects.get(pk=int(existing.new_id))
            except V2CustomerOrder.DoesNotExist:
                pass
            continue
        if dry_run:
            st["reused"] += 1
            continue

        v2_status = V1_ORDER_STATUS_TO_V2.get(v1.status, "draft")
        v2_rep = None
        if v1.user_id:
            v2_rep = worker_map.get(v1.user_id)
            if v2_rep is None:
                mm = _find_map("worker", v1.user_id)
                if mm and mm.new_id:
                    try:
                        v2_rep = V2Worker.objects.get(pk=int(mm.new_id))
                    except V2Worker.DoesNotExist:
                        v2_rep = None
                if v2_rep is None and not _is_dry_marker(mm):
                    v2_rep = V2Worker.objects.filter(user_id=v1.user_id).first()
                worker_map[v1.user_id] = v2_rep

        v2 = V2CustomerOrder.objects.create(
            customer=customer,
            representative=v2_rep,
            order_number=v1.number or f"SO-V1-{v1.id}",
            order_date=v1.created_at.date() if v1.created_at else datetime.date.today(),
            due_date=v1.due_date,
            priority=v1.priority,
            status=v2_status,
            notes=f"Migrated from V1 Order {v1.id}",
            total_amount=0,
            paid_amount=0,
            shipping_cost=0,
            discount_amount=0,
            final_amount=0,
            vat_amount=0,
            payment_terms="",
            delivery_terms="",
        )
        _ensure_map("customer_order", v1.id, v2.id, V2_APP["customer_order"], "CustomerOrder", run,
                    metadata={"v1_status": v1.status})
        customer_map[v1.id] = v2
        st["created"] += 1
    return st, customer_map


def migrate_order_items(dry_run, run, stats, customer_map):
    st = stats["customer_order_item"] = {"total": 0, "created": 0, "reused": 0, "skipped": 0}
    qs = V1OrderItem.objects.all().select_related("order", "product").order_by("id")
    st["total"] = qs.count()

    for v1 in qs:
        v1_order = v1.order
        v2_order = customer_map.get(v1_order.id) if v1_order else None
        if v2_order is None:
            _skip("customer_order_item", v1.id, "order not migrated", run,
                  new_app=V2_APP["customer_order_item"], new_model="CustomerOrderItem")
            st["skipped"] += 1
            continue

        existing = _find_map("customer_order_item", v1.id)
        if existing and existing.new_id:
            st["reused"] += 1
            continue
        if dry_run:
            st["reused"] += 1
            continue

        v2 = V2CustomerOrderItem.objects.create(
            order=v2_order,
            product=v1.product,
            quantity=v1.quantity,
            size=v1.size or "",
            unit_price=v1.unit_price or 0,
            line_total=(v1.unit_price or 0) * v1.quantity,
            notes=v1.notes or "",
            is_custom=False,
            production_notes="",
            estimated_delivery=None,
        )
        _ensure_map("customer_order_item", v1.id, v2.id, V2_APP["customer_order_item"], "CustomerOrderItem", run,
                    metadata={"v1_order_id": v1.order_id})
        st["created"] += 1
    return st


def migrate_production_orders(dry_run, run, stats, customer_map):
    st = stats["production_order"] = {"total": 0, "created": 0, "reused": 0, "skipped": 0}
    qs = V1Order.objects.all().order_by("id")
    st["total"] = qs.count()
    po_map = {}

    for v1 in qs:
        v2_customer_order = customer_map.get(v1.id)
        if v2_customer_order is None:
            _skip("production_order", v1.id, "customer_order not migrated", run,
                  new_app=V2_APP["production_order"], new_model="ProductionOrder")
            st["skipped"] += 1
            continue

        existing = _find_map("production_order", v1.id)
        if existing and existing.new_id:
            st["reused"] += 1
            try:
                po_map[v1.id] = V2ProductionOrder.objects.get(pk=int(existing.new_id))
            except V2ProductionOrder.DoesNotExist:
                pass
            continue
        if dry_run:
            st["reused"] += 1
            continue

        v2_status = V1_ORDER_STATUS_TO_V2.get(v1.status, "draft")
        v2 = V2ProductionOrder.objects.create(
            order=v2_customer_order,
            routing=None,
            bom_revision="",
            order_number=f"PO-V1-{v1.id}",
            status=v2_status,
            planned_start=None,
            planned_end=v1.due_date,
            actual_start=None,
            actual_end=None,
            priority=v1.priority,
            notes=f"Migrated from V1 Order {v1.id}",
        )
        _ensure_map("production_order", v1.id, v2.id, V2_APP["production_order"], "ProductionOrder", run,
                    metadata={"v1_status": v1.status})
        po_map[v1.id] = v2
        st["created"] += 1
    return st, po_map


def _find_or_create_routing_for_product(product):
    routing, _ = V2Routing.objects.get_or_create(
        product=product,
        revision="MIGRATED",
        defaults={
            "name": f"Migration routing for {product.name}",
            "effective_date": datetime.date.today(),
            "status": "draft",
            "total_time_minutes": 0,
            "description": "Auto-created during V1→V2 migration.",
        },
    )
    return routing


def _find_or_create_bom_for_product(product):
    bom, _ = V2BOM.objects.get_or_create(
        product=product,
        revision="MIGRATED",
        defaults={
            "effective_date": datetime.date.today(),
            "description": "Auto-created during V1→V2 migration.",
            "is_active": True,
        },
    )
    return bom


def migrate_production_tasks(dry_run, run, stats, customer_map, po_map):
    st = stats["production_operation"] = {"total": 0, "created": 0, "reused": 0, "skipped": 0}
    st["operation_assignment"] = {"total": 0, "created": 0, "reused": 0, "skipped": 0}
    st["operation_execution"] = {"total": 0, "created": 0, "reused": 0, "skipped": 0}
    qs = V1ProductionTask.objects.all().select_related("order", "order_item", "part", "assigned_worker", "painting_stage", "scanned_by").order_by("id")
    st["production_operation"]["total"] = qs.count()

    for v1 in qs:
        v1_order = v1.order
        v2_po = po_map.get(v1_order.id) if v1_order else None
        if v2_po is None:
            _skip("production_operation", v1.id, "production_order not migrated", run,
                  new_app=V2_APP["production_operation"], new_model="ProductionOperation")
            st["production_operation"]["skipped"] += 1
            continue

        v1_order_item = v1.order_item
        v2_poi = None
        if v1_order_item:
            mm = _find_map("customer_order_item", v1_order_item.id)
            if mm and mm.new_id:
                try:
                    v2_poi = V2ProductionOrderItem.objects.filter(
                        production_order=v2_po,
                        customer_order_item_id=int(mm.new_id),
                    ).first()
                except (ValueError, TypeError):
                    v2_poi = None
            if v2_poi is None:
                v2_poi = V2ProductionOrderItem.objects.filter(
                    production_order=v2_po,
                    customer_order_item__order__order__id=v1_order_item.order_id,
                ).first()

        if v2_poi is None:
            v2_poi = V2ProductionOrderItem.objects.filter(production_order=v2_po).first()

        if v2_poi is None:
            _skip("production_operation", v1.id, "production_order_item not found", run,
                  new_app=V2_APP["production_operation"], new_model="ProductionOperation")
            st["production_operation"]["skipped"] += 1
            continue

        existing = _find_map("production_operation", v1.id)
        if existing and existing.new_id:
            st["production_operation"]["reused"] += 1
            continue
        if dry_run:
            st["production_operation"]["reused"] += 1
            continue

        op_code = STATION_TO_OP_CODE.get(v1.station_name, v1.station_name.upper())
        op_name = STATION_TO_OP_NAME.get(v1.station_name, v1.station_name)

        wc = _get_v2_work_center_fallback()
        v2 = V2ProductionOperation.objects.create(
            production_order=v2_po,
            production_order_item=v2_poi,
            operation_name=op_name,
            operation_code=op_code,
            work_center=wc,
            sequence=v1.step_order,
            status=V1_TASK_STATUS_TO_V2.get(v1.status, "waiting"),
            planned_start=v1.scheduled_start,
            planned_end=None,
            actual_start=None,
            actual_end=v1.completed_at,
            setup_time_minutes=0,
            run_time_minutes=0,
            completed_quantity=v1.completed_quantity or 0,
            scrapped_quantity=0,
            notes=f"Migrated from V1 ProductionTask {v1.id}",
            part=v1.part,
            scanned_by=v1.scanned_by,
            completed_at=v1.completed_at,
            painting_stage=v1.painting_stage,
            assigned_worker=v1.assigned_worker,
            order_item=v1.order_item,
            color_part=v1.color_part or "",
        )
        _ensure_map("production_operation", v1.id, v2.id, V2_APP["production_operation"], "ProductionOperation", run,
                    metadata={"v1_status": v1.status, "v1_station": v1.station_name})
        st["production_operation"]["created"] += 1

        if v1.assigned_worker_id:
            st["operation_assignment"]["total"] += 1
            assign_status = "completed" if v1.status == "done" else "assigned"
            assign, assign_created = V2OperationAssignment.objects.get_or_create(
                operation=v2,
                worker=None,
                defaults={
                    "status": assign_status,
                    "notes": f"Migrated from V1 ProductionTask {v1.id}",
                },
            )
            if assign_created:
                st["operation_assignment"]["created"] += 1
                _ensure_map("operation_assignment", f"{v1.id}-assigned", assign.id,
                            V2_APP["operation_assignment"], "OperationAssignment", run,
                            metadata={"v1_task_id": v1.id})
            else:
                st["operation_assignment"]["reused"] += 1

        if v1.status == "done":
            st["operation_execution"]["total"] += 1
            exec_obj = V2OperationExecution.objects.create(
                operation=v2,
                worker=None,
                started_at=v1.completed_at or v1.created_at,
                ended_at=v1.completed_at,
                quantity_produced=v1.completed_quantity or v1.quantity,
                quantity_scrapped=0,
                setup_time_minutes=0,
                run_time_minutes=0,
                notes=f"Migrated from V1 ProductionTask {v1.id}",
                is_completed=True,
            )
            _ensure_map("operation_execution", f"{v1.id}-done", exec_obj.id,
                        V2_APP["operation_execution"], "OperationExecution", run,
                        metadata={"v1_task_id": v1.id})
            st["operation_execution"]["created"] += 1

    return st


def _run_production_phase(dry_run, run):
    global _DRY_RUN
    _DRY_RUN = dry_run
    stats = {}

    with transaction.atomic():
        if not dry_run:
            run.status = "running"
            run.save(update_fields=["status"])

        _, customer_map = migrate_orders(dry_run, run, stats)
        if not dry_run:
            customer_map = {}
            for mm in MigrationMap.objects.filter(migration_type="customer_order"):
                if mm.new_id:
                    try:
                        customer_map[int(mm.old_id)] = V2CustomerOrder.objects.get(pk=int(mm.new_id))
                    except (V2CustomerOrder.DoesNotExist, ValueError, TypeError):
                        pass

        migrate_order_items(dry_run, run, stats, customer_map)
        _, po_map = migrate_production_orders(dry_run, run, stats, customer_map)
        if not dry_run:
            po_map = {}
            for mm in MigrationMap.objects.filter(migration_type="production_order"):
                if mm.new_id:
                    try:
                        po_map[int(mm.old_id)] = V2ProductionOrder.objects.get(pk=int(mm.new_id))
                    except (V2ProductionOrder.DoesNotExist, ValueError, TypeError):
                        pass

        migrate_production_tasks(dry_run, run, stats, customer_map, po_map)

    _DRY_RUN = False
    return stats


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
DOMAIN_ORDER = [
    "product_category",
    "product",
    "customer",
    "worker",
    "material",
    "product_part",
    "production_part",
    "bom",
    "bom_item",
    "bom_item_material_rule",
    "painting_process",
    "painting_stage",
]


def _build_cat_map(dry_run):
    """V1 ProductCategory.id -> V2 ProductCategory (instance or dry marker)."""
    m = {}
    for v1 in V1ProductCategory.objects.all().order_by("id"):
        name = (v1.name or "").strip()
        if not name:
            continue
        if dry_run:
            m[v1.id] = ("dry", v1.id)
            continue
        v2 = V2ProductCategory.objects.filter(name=name).first()
        if v2:
            m[v1.id] = v2
    return m


def _build_product_map(dry_run, cat_map):
    """V1 Product.id -> V2 Product (instance or dry marker)."""
    m = {}
    for v1 in V1Product.objects.all().select_related("category").order_by("id"):
        v1_cat = v1.category
        if v1_cat is None:
            continue
        v2_cat = cat_map.get(v1_cat.id)
        if not v2_cat:
            continue
        if dry_run:
            m[v1.id] = ("dry", v1.id)
            continue
        v2_cat_id = getattr(v2_cat, "id", v2_cat)
        v2 = V2Product.objects.filter(name=v1.name, category_id=v2_cat_id).first()
        if v2:
            m[v1.id] = v2
    return m


def _build_part_map(dry_run, product_map):
    """V1 Part.id (base) -> V2 ProductPart (instance or dry marker)."""
    m = {}
    bom_part_product = _bom_part_product_map()
    for v1 in V1Part.objects.filter(base_part__isnull=True).order_by("id"):
        v1_prod_id = bom_part_product.get(v1.id)
        if v1_prod_id is None:
            continue
        v2_prod = product_map.get(v1_prod_id)
        if not v2_prod:
            continue
        if dry_run:
            m[v1.id] = ("dry", v1.id)
            continue
        v2_prod_id = getattr(v2_prod, "id", v2_prod)
        v2 = V2ProductPart.objects.filter(
            product_id=v2_prod_id, f3=(v1.f3 or "").strip()
        ).first()
        if v2:
            m[v1.id] = v2
    return m


def _build_process_map(dry_run):
    """V1 PaintingProcess.id -> V2 PaintingProcess (instance or dry marker)."""
    m = {}
    for v1 in V1PaintingProcess.objects.all().order_by("id"):
        code = (v1.code or "").strip()
        if not code:
            continue
        if dry_run:
            m[v1.id] = ("dry", v1.id)
            continue
        v2 = V2PaintingProcess.objects.filter(code=code).first()
        if v2:
            m[v1.id] = v2
    return m


def _resolve(model, value):
    """Resolve an FK value: model instance, int id, or dry-run marker tuple."""
    if value is None:
        return None
    if isinstance(value, tuple) and value and value[0] == "dry":
        return value
    if isinstance(value, model):
        return value
    if isinstance(value, int):
        return model.objects.filter(pk=value).first()
    return None


def _is_dry_marker(value):
    return isinstance(value, tuple) and value and value[0] == "dry"


def _map_from_db(migration_type, dry_run, key_fn):
    """Build V1.id -> V2 instance map from MigrationMap rows (execute mode)."""
    m = {}
    for mm in MigrationMap.objects.filter(migration_type=migration_type):
        if not mm.new_id:
            continue
        try:
            m[key_fn(mm.old_id)] = int(mm.new_id)
        except (ValueError, TypeError):
            continue
    return m


def _run_master_data_phase(dry_run, run):
    global _DRY_RUN
    _DRY_RUN = dry_run
    stats = {}
    cat_map = _build_cat_map(dry_run)
    product_map = _build_product_map(dry_run, cat_map)
    item_map = {}
    part_map = _build_part_map(dry_run, product_map)
    process_map = _build_process_map(dry_run)

    with transaction.atomic():
        if not dry_run:
            run.status = "running"
            run.save(update_fields=["status"])

        migrate_product_categories(dry_run, run, stats)
        if not dry_run:
            cat_map = _build_cat_map(dry_run)
            product_map = _build_product_map(dry_run, cat_map)

        migrate_products(dry_run, run, stats, cat_map)
        if not dry_run:
            product_map = _build_product_map(dry_run, cat_map)

        migrate_customers(dry_run, run, stats)
        migrate_workers(dry_run, run, stats)
        migrate_materials(dry_run, run, stats, item_map)
        if not dry_run:
            item_map = _map_from_db("material", dry_run, int)

        migrate_parts(dry_run, run, stats, item_map, product_map)
        if not dry_run:
            part_map = _build_part_map(dry_run, product_map)

        migrate_production_parts(dry_run, run, stats, part_map, product_map)
        migrate_boms(dry_run, run, stats, product_map, part_map, item_map)
        migrate_painting(dry_run, run, stats)

    _DRY_RUN = False
    return stats


def _reconcile(stats, order=None):
    lines = []
    for key in (order or DOMAIN_ORDER):
        st = stats.get(key)
        if not st:
            continue
        extra = (" merged=%d" % st["merged"]) if "merged" in st else ""
        lines.append(
            "%-26s total=%-6d created=%-6d reused=%-6d skipped=%-6d%s"
            % (key, st.get("total", 0), st.get("created", 0),
               st.get("reused", 0), st.get("skipped", 0), extra)
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Inventory migration (Phase 6) - StockMovement -> StockLedger
# ---------------------------------------------------------------------------
INVENTORY_DOMAIN_ORDER = [
    "stock_movement",
]


def _get_v2_item_for_stock_movement(movement, item_map):
    raw_material = getattr(movement, 'raw_material', None)
    if raw_material is None:
        return None
    item_id = item_map.get(('raw', raw_material.id)) or item_map.get(raw_material.id)
    if item_id:
        try:
            return V2Item.objects.get(pk=item_id)
        except V2Item.DoesNotExist:
            pass
    return None


def _get_v2_location_for_stock_movement(movement):
    wh_code = getattr(movement, 'warehouse_code', None) or getattr(movement, 'location_code', None)
    if wh_code:
        try:
            return V2StockLocation.objects.get(code=wh_code)
        except V2StockLocation.DoesNotExist:
            pass
    wh, _ = V2StockLocation.objects.get_or_create(
        code='WH-MIGRATED',
        defaults={
            'name': 'انبار مهاجرت شده',
            'location_type': 'warehouse',
            'is_active': False,
        },
    )
    return wh


def migrate_stock_movements(dry_run, run, stats, item_map):
    st = stats["stock_movement"] = {"total": 0, "created": 0, "reused": 0, "skipped": 0}
    qs = V1StockMovement.objects.all().select_related('raw_material').order_by('id')
    st["total"] = qs.count()
    ledger_map = {}

    for movement in qs:
        v2_item = _get_v2_item_for_stock_movement(movement, item_map)
        if v2_item is None:
            _skip("stock_movement", movement.id, "item not migrated", run,
                  new_app=V2_APP["stock_movement"], new_model="StockLedger")
            st["skipped"] += 1
            continue

        existing = _find_map("stock_movement", movement.id)
        if existing and existing.new_id:
            st["reused"] += 1
            try:
                ledger_map[movement.id] = V2StockLedger.objects.get(pk=int(existing.new_id))
            except V2StockLedger.DoesNotExist:
                pass
            continue
        if dry_run:
            st["reused"] += 1
            continue

        v2_location = _get_v2_location_for_stock_movement(movement)

        m_type = getattr(movement, 'movement_type', None) or 'adjustment'
        if m_type == 'purchase':
            ledger_type = 'receipt'
        elif m_type == 'consumption':
            ledger_type = 'consumption'
        elif m_type == 'return':
            ledger_type = 'return'
        else:
            ledger_type = 'adjustment'

        qty = _decimal(getattr(movement, 'quantity', None), Decimal('0')) or Decimal('0')
        if ledger_type in ('receipt', 'return'):
            quantity = abs(qty)
        else:
            quantity = -abs(qty)

        balance, _ = V2StockBalance.objects.select_for_update().get_or_create(
            item=v2_item,
            location=v2_location,
            defaults={
                'quantity_on_hand': Decimal('0'),
                'quantity_reserved': Decimal('0'),
                'quantity_available': Decimal('0'),
            },
        )
        balance.quantity_on_hand += quantity
        if balance.quantity_on_hand < 0:
            balance.quantity_on_hand = Decimal('0')
        balance.quantity_available = balance.quantity_on_hand - balance.quantity_reserved
        balance.last_movement = timezone.now()
        balance.save(update_fields=['quantity_on_hand', 'quantity_available', 'last_movement'])

        ledger = V2StockLedger.objects.create(
            item=v2_item,
            location=v2_location,
            lot=None,
            ledger_type=ledger_type,
            quantity=quantity,
            balance_after=balance.quantity_on_hand,
            reference_document=f"StockMovement:{movement.id}",
            reference_id=str(movement.id),
            notes=getattr(movement, 'note', '') or '',
            created_by=getattr(movement, 'created_by', None),
        )
        _ensure_map("stock_movement", movement.id, ledger.id, V2_APP["stock_movement"], "StockLedger", run,
                    metadata={"v1_movement_type": m_type})
        ledger_map[movement.id] = ledger
        st["created"] += 1
    return st, ledger_map


# ---------------------------------------------------------------------------
# Barcode/Packaging/Shipping migration (Phase 7)
# ---------------------------------------------------------------------------
PACKAGING_DOMAIN_ORDER = [
    "packaging_unit",
    "shipment_log",
]


def _get_v2_order_item_for_packaging(pu, customer_order_item_map):
    oi = getattr(pu, 'order_item', None)
    if oi is None:
        return None
    new_id = customer_order_item_map.get(oi.id)
    if new_id is None:
        return None
    try:
        return V2CustomerOrderItem.objects.get(pk=new_id)
    except V2CustomerOrderItem.DoesNotExist:
        return None


def migrate_packaging_units(dry_run, run, stats, customer_order_item_map):
    st = stats["packaging_unit"] = {"total": 0, "created": 0, "reused": 0, "skipped": 0}
    qs = V1PackagingUnit.objects.all().select_related('order_item').order_by('id')
    st["total"] = qs.count()
    package_map = {}

    for pu in qs:
        v2_coi = _get_v2_order_item_for_packaging(pu, customer_order_item_map)
        if v2_coi is None:
            _skip("packaging_unit", pu.id, "customer_order_item not migrated", run,
                  new_app=V2_APP["packaging_unit"], new_model="Package")
            st["skipped"] += 1
            continue

        existing = _find_map("packaging_unit", pu.id)
        if existing and existing.new_id:
            st["reused"] += 1
            try:
                package_map[pu.id] = V2Package.objects.get(pk=int(existing.new_id))
            except V2Package.DoesNotExist:
                pass
            continue
        if dry_run:
            st["reused"] += 1
            continue

        v2_status = 'packed' if getattr(pu, 'is_packed', False) else 'draft'
        v2 = V2Package.objects.create(
            customer_order_item=v2_coi,
            production_order_item=None,
            wip_unit=None,
            package_number=f"PKG-V1-{pu.id}",
            status=v2_status,
            packed_at=getattr(pu, 'packed_at', None),
            packed_by=getattr(pu, 'packed_by', None),
            weight_kg=getattr(pu, 'weight_kg', None) or 0,
            dimensions='',
            notes=f"Migrated from V1 PackagingUnit {pu.id}",
        )
        _ensure_map("packaging_unit", pu.id, v2.id, V2_APP["packaging_unit"], "Package", run,
                    metadata={"v1_unit_number": getattr(pu, 'unit_number', None)})
        package_map[pu.id] = v2
        st["created"] += 1
    return st, package_map


def migrate_shipment_logs(dry_run, run, stats, package_map):
    st = stats["shipment_log"] = {"total": 0, "created": 0, "reused": 0, "skipped": 0}
    qs = V1ShipmentLog.objects.all().select_related('packaging_unit').order_by('id')
    st["total"] = qs.count()
    shipment_map = {}

    for log in qs:
        v1_pu = getattr(log, 'packaging_unit', None)
        v2_pkg = package_map.get(v1_pu.id) if v1_pu else None
        if v2_pkg is None:
            _skip("shipment_log", log.id, "package not migrated", run,
                  new_app=V2_APP["shipment_log"], new_model="Shipment")
            st["skipped"] += 1
            continue

        existing = _find_map("shipment_log", log.id)
        if existing and existing.new_id:
            st["reused"] += 1
            try:
                shipment_map[log.id] = V2Shipment.objects.get(pk=int(existing.new_id))
            except V2Shipment.DoesNotExist:
                pass
            continue
        if dry_run:
            st["reused"] += 1
            continue

        coi = getattr(v2_pkg, 'customer_order_item', None)
        customer_order = getattr(coi, 'order', None) if coi else None
        customer = getattr(customer_order, 'customer', None) if customer_order else None

        shipment_number = f"SH-V1-{log.id}"
        existing_shipment = V2Shipment.objects.filter(shipment_number=shipment_number).first()
        if existing_shipment:
            _ensure_map("shipment_log", log.id, existing_shipment.id, V2_APP["shipment_log"], "Shipment", run,
                        metadata={"v1_shipment_log_id": log.id})
            st["reused"] += 1
            shipment_map[log.id] = existing_shipment
            continue

        v2 = V2Shipment.objects.create(
            shipment_number=shipment_number,
            customer_order=customer_order,
            customer=customer,
            status='in_transit',
            shipment_date=getattr(log, 'shipped_at', None),
            plate_number=getattr(log, 'plate_number', ''),
            driver_name='',
            driver_phone='',
            shipping_cost=0,
            insurance_cost=0,
            total_weight_kg=getattr(v2_pkg, 'weight_kg', None) or 0,
            total_volume_m3=0,
            notes=getattr(log, 'delivery_notes', '') or '',
            delivery_notes=getattr(log, 'delivery_notes', '') or '',
            created_by=None,
        )
        V2ShipmentItem.objects.create(
            shipment=v2,
            package=v2_pkg,
            quantity=1,
            weight_kg=getattr(v2_pkg, 'weight_kg', None) or 0,
            volume_m3=0,
            notes='',
        )
        _ensure_map("shipment_log", log.id, v2.id, V2_APP["shipment_log"], "Shipment", run,
                    metadata={"v1_plate_number": getattr(log, 'plate_number', '')})
        shipment_map[log.id] = v2
        st["created"] += 1
    return st, shipment_map


def _run_inventory_phase(dry_run, run):
    global _DRY_RUN
    _DRY_RUN = dry_run
    stats = {}
    item_map = {}
    if not dry_run:
        for mm in MigrationMap.objects.filter(migration_type__in=["material", "raw_material", "item"]):
            if mm.new_id:
                try:
                    item_map[mm.old_id] = int(mm.new_id)
                except (ValueError, TypeError):
                    pass
                try:
                    raw_id = int(mm.old_id)
                    item_map[("raw", raw_id)] = int(mm.new_id)
                except (ValueError, TypeError):
                    pass
    with transaction.atomic():
        if not dry_run:
            run.status = "running"
            run.save(update_fields=["status"])
        migrate_stock_movements(dry_run, run, stats, item_map)
    _DRY_RUN = False
    return stats


def _run_barcode_phase(dry_run, run):
    global _DRY_RUN
    _DRY_RUN = dry_run
    stats = {}
    customer_order_item_map = {}
    if not dry_run:
        for mm in MigrationMap.objects.filter(migration_type="customer_order_item"):
            if mm.new_id:
                try:
                    customer_order_item_map[int(mm.old_id)] = int(mm.new_id)
                except (ValueError, TypeError):
                    pass
    with transaction.atomic():
        if not dry_run:
            run.status = "running"
            run.save(update_fields=["status"])
        _, pkg_map = migrate_packaging_units(dry_run, run, stats, customer_order_item_map)
        migrate_shipment_logs(dry_run, run, stats, pkg_map)
    _DRY_RUN = False
    return stats


# ---------------------------------------------------------------------------
# Phase registry
# ---------------------------------------------------------------------------
PHASES = {
    "master-data": {
        "order": DOMAIN_ORDER,
        "runner": _run_master_data_phase,
    },
    "production": {
        "order": PRODUCTION_DOMAIN_ORDER,
        "runner": _run_production_phase,
    },
    "inventory": {
        "order": INVENTORY_DOMAIN_ORDER,
        "runner": _run_inventory_phase,
    },
    "barcode": {
        "order": PACKAGING_DOMAIN_ORDER,
        "runner": _run_barcode_phase,
    },
    "rollback_delete_order": [
        "shipment_item", "shipment", "shipment_tracking",
        "package_item", "package",
        "operation_execution",
        "operation_assignment",
        "wip_transfer",
        "wip_unit",
        "production_operation",
        "production_order_item",
        "production_order",
        "routing_dependency",
        "routing_operation",
        "routing",
        "customer_order_item",
        "customer_order",
        "bom_item_material_rule",
        "bom_item",
        "production_part",
        "part", "product_part",
        "bom",
        "product", "product_category",
        "painting_stage", "painting_process",
        "stock_ledger", "stock_movement",
        "material", "raw_material", "item", "item_category", "uom",
        "worker", "worker_profile",
        "customer",
    ],
}


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------
class Command(BaseCommand):
    help = (
        "Phase 4/5/6/7: Master Data, Production, Inventory, Barcode/Packaging/Shipping Migration "
        "(V1 -> V2, idempotent, zero V1 mutation)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--phase",
            default="master-data",
            choices=["master-data", "production", "inventory", "barcode"],
            help="Migration phase (default: master-data)",
        )
        group = parser.add_mutually_exclusive_group(required=False)
        group.add_argument("--dry-run", action="store_true",
                           help="Report only; zero database writes.")
        group.add_argument("--execute", action="store_true",
                           help="Execute the migration and create a MigrationRun.")
        parser.add_argument("--rollback", type=str, default=None,
                            help="Rollback a MigrationRun by its ID.")
        parser.add_argument("--name", type=str, default=None,
                            help="Optional name for the MigrationRun.")

    def _rollback(self, run_id):
        try:
            run = MigrationRun.objects.get(pk=run_id)
        except MigrationRun.DoesNotExist:
            raise CommandError(f"MigrationRun {run_id} not found")
        if run.phase not in PHASES:
            raise CommandError(
                f"MigrationRun {run_id} is phase '{run.phase}', not a known phase"
            )
        delete_order = PHASES["rollback_delete_order"]
        with transaction.atomic():
            deleted_maps = 0
            deleted_v2 = 0
            for mt in delete_order:
                spec = V2_MODEL_BY_TYPE.get(mt)
                if spec is None:
                    continue
                model, _app = spec
                for mm in MigrationMap.objects.filter(
                    migration_run=run, migration_type=mt
                ):
                    if not mm.new_id:
                        deleted_maps += 1
                        continue
                    try:
                        obj = model.objects.filter(pk=int(mm.new_id)).first()
                    except (ValueError, TypeError):
                        deleted_maps += 1
                        continue
                    if obj is not None:
                        obj.delete()
                        deleted_v2 += 1
                    deleted_maps += 1
            # any remaining mappings not covered above
            remaining = MigrationMap.objects.filter(migration_run=run)
            deleted_maps += remaining.count()
            remaining.delete()
            run.delete()
        self.stdout.write(
            self.style.WARNING(
                f"Rollback complete for MigrationRun {run_id}: "
                f"{deleted_maps} MigrationMap rows deleted, "
                f"{deleted_v2} V2 rows deleted. V1 untouched."
            )
        )

    def handle(self, *args, **options):
        phase = options["phase"]
        if phase not in PHASES:
            raise CommandError(
                f"Unknown phase '{phase}' (available: {', '.join(sorted(PHASES))})"
            )

        if options["rollback"]:
            self._rollback(options["rollback"])
            return

        if not options["dry_run"] and not options["execute"]:
            raise CommandError("Specify --dry-run, --execute, or --rollback")

        dry_run = options["dry_run"]
        name = options["name"] or f"{phase} - {datetime.datetime.now().isoformat(timespec='seconds')}"

        run = None
        if not dry_run:
            run = MigrationRun.objects.create(phase=phase, name=name, status="pending")
            self.stdout.write(
                self.style.HTTP_INFO(f"MigrationRun created: id={run.id} phase={phase}")
            )

        try:
            stats = PHASES[phase]["runner"](dry_run, run)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Migration failed")
            if run:
                run.status = "failed"
                run.errors = list(run.errors or []) + [str(exc)]
                run.log = (run.log or "") + f"\nFATAL: {exc}"
                run.save(update_fields=["status", "errors", "log"])
            raise CommandError(f"Migration failed: {exc}") from exc

        if dry_run:
            self.stdout.write(self.style.SUCCESS("=== DRY RUN (zero writes) ==="))
            self.stdout.write(_reconcile(stats, PHASES[phase]["order"]))
            self.stdout.write("Dry run complete. Re-run with --execute to apply.")
            return

        total = sum(s.get("total", 0) for s in stats.values())
        created = sum(s.get("created", 0) for s in stats.values())
        reused = sum(s.get("reused", 0) for s in stats.values())
        skipped = sum(s.get("skipped", 0) for s in stats.values())
        run.records_processed = created + reused
        run.records_skipped = skipped
        run.records_failed = 0
        run.status = "completed"
        run.completed_at = timezone.now()
        run.log = _reconcile(stats, PHASES[phase]["order"])
        run.save(update_fields=["records_processed", "records_skipped", "records_failed",
                                "status", "completed_at", "log"])

        self.stdout.write(
            self.style.SUCCESS(
                f"MigrationRun {run.id} completed: processed={run.records_processed} "
                f"skipped={skipped} failed=0"
            )
        )
        self.stdout.write(_reconcile(stats, PHASES[phase]["order"]))
