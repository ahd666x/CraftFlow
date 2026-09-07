from decimal import Decimal
from django.db import transaction
from django.contrib.auth import get_user_model
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
    def complete_operation(operation, completed_quantity, user=None):
        with transaction.atomic():
            operation.completed_quantity = completed_quantity
            operation.status = 'completed'
            operation.save(update_fields=['completed_quantity', 'status'])

            execution = OperationExecution.objects.create(
                operation=operation,
                worker=operation.assignments.filter(status='started').first().worker if operation.assignments.filter(status='started').exists() else None,
                started_at=operation.actual_start or operation.created_at,
                is_completed=True,
                quantity_produced=completed_quantity,
            )

            if operation.sequence < operation.production_order_item.operations.count():
                next_op = operation.production_order_item.operations.filter(sequence=operation.sequence + 1).first()
                if next_op:
                    next_op.status = 'ready'
                    next_op.save(update_fields=['status'])

            return execution
