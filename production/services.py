from decimal import Decimal
from django.db import transaction
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
                routing=routing,
            )
            return poi

    @staticmethod
    def create_operations_for_order_item(production_order_item):
        with transaction.atomic():
            routing_operations = production_order_item.routing.operations.all().order_by('sequence')
            operations = []
            for idx, routing_op in enumerate(routing_operations, start=1):
                op = ProductionOperation.objects.create(
                    production_order=production_order_item.production_order,
                    production_order_item=production_order_item,
                    operation_name=routing_op.operation_name,
                    operation_code=routing_op.operation_code,
                    work_center=routing_op.work_center,
                    sequence=idx,
                    setup_time_minutes=routing_op.setup_time_minutes,
                    run_time_minutes=routing_op.run_time_per_unit_minutes * production_order_item.quantity,
                )
                operations.append(op)
            return operations

    @staticmethod
    def complete_operation(operation, completed_quantity, user=None, force_complete=False):
        """
        تکمیل یک عملیات تولید با Policy امن‌تر.

        - partial completion فقط در صورت force_complete=True یا رسیدن به quantity policy مجاز است.
        - فعال‌سازی مرحله بعدی فقط از طریق RoutingDependency انجام می‌شود.
        - اگر RoutingDependency برای این operation وجود نداشته باشد، مرحله بعدی خودکار ready نمی‌شود.
        """
        with transaction.atomic():
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
