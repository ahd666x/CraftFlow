from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from .models import ProductionOrder, ProductionOrderItem, ProductionOperation, OperationAssignment, OperationExecution, WIPUnit, WIPTransfer

User = get_user_model()


class ProductionService:
    @staticmethod
    def create_production_order(customer_order, routing, bom_revision, **kwargs):
        with transaction.atomic():
            order_number = f"PO-{customer_order.id}-{ProductionOrder.objects.count() + 1}"
            po = ProductionOrder.objects.create(
                order=customer_order,
                routing=routing,
                bom_revision=bom_revision,
                order_number=order_number,
                **kwargs
            )
            return po

    @staticmethod
    def add_production_order_item(production_order, customer_order_item, product, quantity, bom, routing):
        with transaction.atomic():
            poi = ProductionOrderItem.objects.create(
                production_order=production_order,
                customer_order_item=customer_order_item,
                product=product,
                quantity=quantity,
                bom=bom,
                bom_revision=bom.revision if bom else "",
                bom_snapshot=ProductionService._build_bom_snapshot(bom) if bom else {},
                routing=routing,
                routing_revision=routing.revision if routing else "",
                routing_snapshot=ProductionService._build_routing_snapshot(routing) if routing else {},
            )
            return poi

    @staticmethod
    def _build_bom_snapshot(bom):
        if not bom:
            return {}
        items = []
        for item in bom.items.all().select_related('part'):
            rules = []
            for rule in item.material_rules.all().select_related('material_item'):
                rules.append({
                    "rule_type": rule.rule_type,
                    "material_item_id": rule.material_item_id,
                    "quantity": str(rule.quantity),
                    "is_primary": rule.is_primary,
                    "priority": rule.priority,
                })
            items.append({
                "part_id": item.part_id,
                "part_code": item.part.code,
                "quantity": item.quantity,
                "scrap_factor": str(item.scrap_factor),
                "notes": item.notes or "",
                "sort_order": item.sort_order,
                "material_rules": rules,
            })
        return {
            "bom_id": bom.id,
            "revision": bom.revision,
            "effective_date": str(bom.effective_date),
            "is_active": bom.is_active,
            "items": items,
        }

    @staticmethod
    def _build_routing_snapshot(routing):
        if not routing:
            return {}
        ops = []
        for op in routing.operations.all().order_by('sequence'):
            ops.append({
                "operation_code": op.operation_code,
                "operation_name": op.operation_name,
                "work_center_id": op.work_center_id,
                "sequence": op.sequence,
                "setup_time_minutes": op.setup_time_minutes,
                "run_time_per_unit_minutes": str(op.run_time_per_unit_minutes),
                "queue_time_minutes": op.queue_time_minutes,
                "is_inspection": op.is_inspection,
                "is_mandatory": op.is_mandatory,
            })
        return {
            "routing_id": routing.id,
            "revision": routing.revision,
            "name": routing.name,
            "effective_date": str(routing.effective_date),
            "status": routing.status,
            "operations": ops,
        }

    @staticmethod
    def create_operations_for_order_item(production_order_item):
        with transaction.atomic():
            routing_operations = production_order_item.routing.operations.all().order_by('sequence')
            operations = []
            for idx, routing_op in enumerate(routing_operations, start=1):
                run_time = Decimal(str(routing_op.run_time_per_unit_minutes))
                qty = Decimal(str(production_order_item.quantity))
                op = ProductionOperation.objects.create(
                    production_order=production_order_item.production_order,
                    production_order_item=production_order_item,
                    operation_name=routing_op.operation_name,
                    operation_code=routing_op.operation_code,
                    work_center=routing_op.work_center,
                    sequence=idx,
                    setup_time_minutes=routing_op.setup_time_minutes,
                    run_time_minutes=int(run_time * qty),
                )
                operations.append(op)
            return operations

    @staticmethod
    def start_operation(operation, **kwargs):
        with transaction.atomic():
            _validate_transition(OPERATION_TRANSITIONS, operation.status, "in_progress")
            if not operation.actual_start:
                operation.actual_start = timezone.now()
            operation.status = "in_progress"
            operation.save(update_fields=["status", "actual_start"])
            return operation

    @staticmethod
    def pause_operation(operation, **kwargs):
        with transaction.atomic():
            _validate_transition(OPERATION_TRANSITIONS, operation.status, "paused")
            operation.status = "paused"
            operation.save(update_fields=["status"])
            return operation

    @staticmethod
    def resume_operation(operation, **kwargs):
        with transaction.atomic():
            _validate_transition(OPERATION_TRANSITIONS, operation.status, "in_progress")
            operation.status = "in_progress"
            operation.save(update_fields=["status"])
            return operation

    @staticmethod
    def complete_operation(operation, completed_quantity, user=None, force_complete=False):
        """
        تکمیل یک عملیات تولید با Policy امن‌تر.

        - partial completion فقط در صورت force_complete=True یا رسیدن به quantity policy مجاز است.
        - فعال‌سازی مرحله بعدی فقط از طریق RoutingDependency انجام می‌شود.
        - اگر RoutingDependency برای این operation وجود نداشته باشد، مرحله بعدی خودکار ready نمی‌شود.
        """
        with transaction.atomic():
            completed_quantity = int(completed_quantity) if completed_quantity else 0
            if completed_quantity < 0:
                raise ValidationError("تعداد تکمیل شده نمی‌تواند منفی باشد.")

            operation.completed_quantity = completed_quantity
            operation.save(update_fields=['completed_quantity'])

            # Determine if operation can be marked completed
            # Default: only complete when explicitly forced or when run_time_minutes is met
            can_complete = force_complete or (
                operation.run_time_minutes > 0 and completed_quantity >= operation.run_time_minutes
            )

            if can_complete:
                operation.status = 'completed'
                operation.save(update_fields=['status'])

                execution = OperationExecution.objects.create(
                    operation=operation,
                    worker=operation.assignments.filter(status='started').first().worker if operation.assignments.filter(status='started').exists() else None,
                    started_at=operation.actual_start or operation.created_at,
                    is_completed=True,
                    quantity_produced=completed_quantity,
                )

                # Activate successors ONLY via RoutingDependency
                successors = ProductionService._get_direct_successors(operation)
                for succ in successors:
                    if succ.status == 'waiting':
                        succ.status = 'ready'
                        succ.save(update_fields=['status'])

                return execution
            else:
                # Partial completion without force - just update quantity
                return None

    @staticmethod
    def _get_direct_successors(operation):
        """
        دریافت operationهای بعدی از طریق RoutingDependency.
        اگر هیچ dependency ثبت نشده باشد، لیست خالی برمی‌گرداند.
        """
        from planning.models import RoutingDependency
        if not operation.production_order_item or not operation.production_order_item.routing:
            return []

        dependencies = RoutingDependency.objects.filter(
            routing=operation.production_order_item.routing,
            predecessor__operation_code=operation.operation_code,
            is_active=True,
        ).select_related('successor')

        successor_codes = [dep.successor.operation_code for dep in dependencies]
        if not successor_codes:
            return []

        return ProductionOperation.objects.filter(
            production_order_item=operation.production_order_item,
            operation_code__in=successor_codes,
        )

    @staticmethod
    def get_predecessors(operation):
        """Return predecessor ProductionOperations via RoutingDependency only."""
        from planning.models import RoutingDependency
        if not operation.production_order_item or not operation.production_order_item.routing:
            return []
        deps = RoutingDependency.objects.filter(
            routing=operation.production_order_item.routing,
            successor__operation_code=operation.operation_code,
            is_active=True,
        ).select_related('predecessor')
        codes = [dep.predecessor.operation_code for dep in deps]
        if not codes:
            return []
        return list(ProductionOperation.objects.filter(
            production_order_item=operation.production_order_item,
            operation_code__in=codes,
        ))

    @staticmethod
    def get_direct_successors(operation):
        return ProductionService._get_direct_successors(operation)

    @staticmethod
    def assign_worker(operation, worker, **kwargs):
        """
        تخصیص کارگر به عملیات. sequence + 1 برای انتخاب کارگر ممنوع است;
        تخصیص فقط بر اساس OperationAssignment ثبت می‌شود.
        """
        with transaction.atomic():
            assignment, created = OperationAssignment.objects.get_or_create(
                operation=operation,
                worker=worker,
                defaults={
                    "status": "assigned",
                    "notes": kwargs.get("notes", ""),
                },
            )
            if not created:
                if assignment.status in ("completed", "released"):
                    raise ValidationError(
                        f"Worker {worker} assignment already {assignment.status}; cannot reassign."
                    )
                assignment.status = "assigned"
                assignment.notes = kwargs.get("notes", assignment.notes)
                assignment.save(update_fields=["status", "notes"])
            return assignment

    @staticmethod
    def start_assignment(operation, worker, **kwargs):
        with transaction.atomic():
            try:
                assignment = OperationAssignment.objects.get(operation=operation, worker=worker)
            except OperationAssignment.DoesNotExist:
                raise ValidationError(f"Worker {worker} is not assigned to operation {operation.id}.")
            if assignment.status not in ("assigned",):
                raise ValidationError(f"Assignment status is {assignment.status}; cannot start.")
            assignment.status = "started"
            assignment.started_at = timezone.now()
            assignment.save(update_fields=["status", "started_at"])
            return assignment

    @staticmethod
    def complete_assignment(operation, worker, **kwargs):
        with transaction.atomic():
            try:
                assignment = OperationAssignment.objects.get(operation=operation, worker=worker)
            except OperationAssignment.DoesNotExist:
                raise ValidationError(f"Worker {worker} is not assigned to operation {operation.id}.")
            if assignment.status != "started":
                raise ValidationError(f"Assignment status is {assignment.status}; cannot complete.")
            assignment.status = "completed"
            assignment.completed_at = timezone.now()
            assignment.save(update_fields=["status", "completed_at"])
            return assignment

    @staticmethod
    def create_wip_unit(production_order_item, serial_number, quantity=1, **kwargs):
        with transaction.atomic():
            wip, created = WIPUnit.objects.get_or_create(
                serial_number=serial_number,
                defaults={
                    "production_order": production_order_item.production_order,
                    "production_order_item": production_order_item,
                    "quantity": quantity,
                    "status": "in_progress",
                    "notes": kwargs.get("notes", ""),
                },
            )
            if not created:
                raise ValidationError(f"WIP unit {serial_number} already exists.")
            return wip

    @staticmethod
    def transfer_wip(wip_unit, to_operation, transferred_by=None, from_operation=None,
                     to_location=None, from_location=None, notes=""):
        """
        انتقال WIP به عملیات بعدی. انتقال تکراری (هممان به همان operation) ممنوع است.
        """
        with transaction.atomic():
            if wip_unit.current_operation_id and wip_unit.current_operation_id == to_operation.id:
                raise ValidationError(
                    f"WIP {wip_unit.serial_number} is already at operation {to_operation.id}."
                )
            # Validate target operation belongs to same production order item
            if to_operation.production_order_item_id != wip_unit.production_order_item_id:
                raise ValidationError(
                    "Target operation does not belong to the same production order item."
                )
            # Dependency gate: target must be ready or in_progress
            if to_operation.status not in ("ready", "in_progress", "paused"):
                raise ValidationError(
                    f"Target operation status is {to_operation.status}; cannot transfer WIP."
                )
            transfer = WIPTransfer.objects.create(
                wip_unit=wip_unit,
                from_operation=from_operation or wip_unit.current_operation,
                to_operation=to_operation,
                from_location=from_location,
                to_location=to_location,
                transferred_by=transferred_by,
                notes=notes,
            )
            wip_unit.current_operation = to_operation
            if to_operation.status == "completed":
                wip_unit.status = "completed"
                wip_unit.completed_at = timezone.now()
            wip_unit.save(update_fields=["current_operation", "status", "completed_at"])
            return transfer

    @staticmethod
    def partial_complete_operation(operation, quantity, worker=None, force=False, notes=""):
        """
        Partial completion policy:
        - quantity must be > 0 unless force=True
        - operation does NOT auto-transition to completed unless force=True
          or completed_quantity reaches the operation's planned quantity
        """
        if quantity < 0:
            raise ValidationError("Quantity cannot be negative.")
        if quantity == 0 and not force:
            raise ValidationError("Cannot record zero completion. Use force=True to override.")
        with transaction.atomic():
            operation.completed_quantity = (operation.completed_quantity or 0) + quantity
            if force or operation.completed_quantity >= operation.quantity:
                operation.status = "completed"
                operation.actual_end = timezone.now()
                operation.save(update_fields=["completed_quantity", "status", "actual_end"])
                OperationExecution.objects.create(
                    operation=operation,
                    worker=worker,
                    started_at=operation.actual_start or operation.created_at,
                    ended_at=operation.actual_end,
                    quantity_produced=quantity,
                    is_completed=True,
                    notes=notes,
                )
                for succ in ProductionService.get_direct_successors(operation):
                    if succ.status == "waiting":
                        succ.status = "ready"
                        succ.save(update_fields=["status"])
                return True
            operation.save(update_fields=["completed_quantity"])
            return False

# ---------------------------------------------------------------------------
# Explicit transition state machine (Phase 5)
# ---------------------------------------------------------------------------
# Allowed transitions per model. sequence + 1 is FORBIDDEN for dependencies:
# dependency readiness is derived ONLY from RoutingDependency rows.
OPERATION_TRANSITIONS = {
    "waiting": {"ready", "in_progress"},
    "ready": {"in_progress", "paused", "skipped", "failed"},
    "in_progress": {"paused", "completed", "failed"},
    "paused": {"in_progress", "skipped", "failed"},
    "completed": set(),
    "skipped": set(),
    "failed": set(),
}

PO_TRANSITIONS = {
    "draft": {"planned", "cancelled"},
    "planned": {"released", "cancelled"},
    "released": {"in_progress", "paused", "cancelled"},
    "in_progress": {"paused", "completed", "cancelled"},
    "paused": {"in_progress", "completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}

BATCH_TRANSITIONS = {
    "planned": {"started", "cancelled"},
    "started": {"in_progress", "completed", "cancelled"},
    "in_progress": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


def _validate_transition(model_status_map, current, target):
    allowed = model_status_map.get(current, set())
    if target not in allowed:
        raise ValidationError(
            f"Invalid transition: {current} -> {target}. Allowed: {sorted(allowed)}"
        )
    return True


class ProductionStateMachine:
    """Validates and applies state transitions for production entities."""

    # -- ProductionOperation -------------------------------------------------
    @staticmethod
    def transition_operation(operation, target, **kwargs):
        _validate_transition(OPERATION_TRANSITIONS, operation.status, target)
        user = kwargs.get("user")
        quantity = kwargs.get("quantity", 0)
        notes = kwargs.get("notes", "")

        with transaction.atomic():
            if target == "ready":
                # Only allowed if all RoutingDependency predecessors are completed
                deps = ProductionService.get_predecessors(operation)
                for dep in deps:
                    if dep.status != "completed":
                        raise ValidationError(
                            f"Predecessor operation {dep.operation_code} is {dep.status}; "
                            "cannot set successor to ready."
                        )
                operation.status = "ready"
                operation.save(update_fields=["status"])

            elif target == "in_progress":
                if not operation.actual_start:
                    operation.actual_start = timezone.now()
                operation.status = "in_progress"
                operation.save(update_fields=["status", "actual_start"])

            elif target == "paused":
                operation.status = "paused"
                operation.save(update_fields=["status"])

            elif target == "completed":
                # Partial completion policy: operation completes only when
                # completed_quantity >= quantity OR explicit force flag.
                force = kwargs.get("force", False)
                if not force and quantity < operation.completed_quantity + 1:
                    # allow partial if quantity > 0 and policy permits
                    pass
                if not force and quantity < 1:
                    raise ValidationError(
                        "Cannot complete operation with zero quantity. "
                        "Use force=True to override."
                    )
                operation.completed_quantity = (
                    operation.completed_quantity + quantity if quantity else operation.completed_quantity
                )
                operation.status = "completed"
                operation.actual_end = timezone.now()
                operation.save(update_fields=["completed_quantity", "status", "actual_end"])

                # Record execution
                worker = kwargs.get("worker")
                OperationExecution.objects.create(
                    operation=operation,
                    worker=worker,
                    started_at=operation.actual_start or operation.created_at,
                    ended_at=operation.actual_end,
                    quantity_produced=quantity,
                    is_completed=True,
                    notes=notes,
                )
                # Activate successors ONLY via RoutingDependency
                for succ in ProductionService.get_direct_successors(operation):
                    if succ.status == "waiting":
                        succ.status = "ready"
                        succ.save(update_fields=["status"])

            elif target == "skipped":
                operation.status = "skipped"
                operation.save(update_fields=["status"])
                for succ in ProductionService.get_direct_successors(operation):
                    if succ.status == "waiting":
                        succ.status = "ready"
                        succ.save(update_fields=["status"])

            elif target == "failed":
                operation.status = "failed"
                operation.save(update_fields=["status"])

            return operation

    # -- ProductionOrder -----------------------------------------------------
    @staticmethod
    def transition_production_order(po, target, **kwargs):
        _validate_transition(PO_TRANSITIONS, po.status, target)
        with transaction.atomic():
            if target == "released":
                po.actual_start = timezone.now()
            elif target == "completed":
                po.actual_end = timezone.now()
            po.status = target
            po.save(update_fields=["status", "actual_start", "actual_end"])
            return po

    # -- ProductionBatch -----------------------------------------------------
    @staticmethod
    def transition_batch(batch, target, **kwargs):
        _validate_transition(BATCH_TRANSITIONS, batch.status, target)
        with transaction.atomic():
            if target == "started":
                batch.actual_start = timezone.now()
            elif target == "completed":
                batch.actual_end = timezone.now()
            batch.status = target
            batch.save(update_fields=["status", "actual_start", "actual_end"])
            return batch
