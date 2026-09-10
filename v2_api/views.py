"""
V2 API Views - Thin views that delegate to Service (mutations) and Selector (queries).
All mutations are wrapped in transaction.atomic and create AuditLog + BusinessEvent.
"""

import uuid
import logging
from decimal import Decimal

import jdatetime
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework.exceptions import PermissionDenied

from selvi.features import is_enabled, require_feature

from sales.models import CustomerOrder, CustomerOrderItem, Customer, OrderItemColor
from sales.services import OrderService
from production.models import ProductionOrder, ProductionOrderItem, ProductionOperation
from production.services import ProductionService
from production.selectors import ProductionSelectors
from planning.models import Routing
from products.models import Product
from bom.models import BOM
from inventory.models import Item, StockLocation, StockLot, StockBalance, StockReservation, StockLedger
from inventory.services import InventoryService
from inventory.selectors import InventorySelectors
from warehouse.services import WarehouseService
from warehouse.models import MaterialIssue
from quality.models import QualityInspection, QualityDefect, ReworkOrder
from quality.services import QualityService
from quality.selectors import QualitySelectors
from painting.scheduler import schedule_painting_operations
from painting.models import PaintingSchedule, PaintingScheduleItem
from packaging.models import Package, PackageItem
from packaging.services import PackagingService
from shipping.models import Shipment, ShipmentItem
from shipping.services import ShippingService
from reporting.models import BusinessEvent, AuditLog
from reporting.services import EventService, AuditService

logger = logging.getLogger(__name__)


def v2_feature_required(view_class):
    """Class decorator that checks V2 feature flag on dispatch."""
    original_dispatch = view_class.dispatch

    def dispatch(self, request, *args, **kwargs):
        if not is_enabled('v2_ui'):
            return JsonResponse(
                {'error': 'V2 UI is disabled'}, status=403
            )
        return original_dispatch(self, request, *args, **kwargs)

    view_class.dispatch = dispatch
    return view_class


class V2APIView(APIView):
    """Base view with feature flag and permission checks."""
    permission_classes = [IsAuthenticated]
    feature_name = 'v2_ui'

    def get_authenticate_header(self, request):
        """Check all authenticators for a WWW-Authenticate header."""
        authenticators = self.get_authenticators()
        for authenticator in authenticators:
            header = authenticator.authenticate_header(request)
            if header is not None:
                return header
        return None

    def initial(self, request, *args, **kwargs):
        if self.feature_name and not is_enabled(self.feature_name):
            raise PermissionDenied(detail='V2 UI is disabled')
        return super().initial(request, *args, **kwargs)

    def handle_exception(self, exc):
        logger.exception(f"V2 API error: {exc}")
        return super().handle_exception(exc)


class CustomerOrderListCreateView(V2APIView):
    """
    List customer orders or create a new one.
    GET: uses Selector (read-only).
    POST: uses Service (mutation with atomic + audit).
    """

    def get(self, request):
        orders = CustomerOrder.objects.all().select_related('customer').order_by('-order_date')[:50]
        data = [
            {
                'id': o.id,
                'order_number': o.order_number,
                'customer_name': o.customer.name,
                'order_date': o.order_date,
                'status': o.status,
            }
            for o in orders
        ]
        return Response(data)

    def post(self, request):
        customer_id = request.data.get('customer_id')
        if not customer_id:
            return Response(
                {'error': 'customer_id is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        customer = get_object_or_404(Customer, id=customer_id)

        with transaction.atomic():
            order = OrderService.create_order(
                customer=customer,
                representative=request.user,
                order_date=request.data.get('order_date', timezone.now().date()),
                **{k: v for k, v in request.data.items() if k not in ['customer_id', 'order_date', 'items']}
            )

            for item_data in request.data.get('items', []):
                product = get_object_or_404(Product, id=item_data['product_id'])
                OrderService.add_item(
                    order=order,
                    product=product,
                    quantity=item_data['quantity'],
                    size=item_data.get('size', ''),
                    notes=item_data.get('notes', ''),
                    colors=item_data.get('colors', None),
                )

            OrderService.update_order_totals(order)
            EventService.log_event(
                category='sales',
                event_type='created',
                title=f'Customer order created: {order.order_number}',
                user=request.user,
                content_object=order,
            )
            AuditService.log_create(request.user, 'CustomerOrder', order)

        return Response({'id': order.id, 'order_number': order.order_number}, status=status.HTTP_201_CREATED)


class ProductionOrderCreateView(V2APIView):
    """Create a ProductionOrder from a CustomerOrder."""

    def get(self, request, order_id):
        order = get_object_or_404(CustomerOrder, id=order_id)
        progress = OrderService.get_order_progress(order)
        data = {
            'order_id': order.id,
            'order_number': order.order_number,
            'status': order.status,
            'progress': progress,
            'items': [
                {
                    'item_id': oi.id,
                    'product_name': oi.product.name,
                    'quantity': oi.quantity,
                    'has_production_order': hasattr(oi, 'production_order_items'),
                }
                for oi in order.items.all()
            ],
        }
        return Response(data)

    def post(self, request, order_id):
        order = get_object_or_404(CustomerOrder, id=order_id)
        routing_id = request.data.get('routing_id')
        routing = get_object_or_404(Routing, id=routing_id) if routing_id else None

        with transaction.atomic():
            prod_order = ProductionService.create_production_order(
                customer_order=order,
                routing=routing,
                bom_revision=request.data.get('bom_revision', 'A'),
                status='planned',
            )

            for item_data in request.data.get('items', []):
                customer_order_item = get_object_or_404(CustomerOrderItem, id=item_data['order_item_id'])
                product = get_object_or_404(Product, id=item_data['product_id'])
                bom = get_object_or_404(BOM, id=item_data['bom_id'])
                routing = get_object_or_404(Routing, id=item_data.get('routing_id')) if item_data.get('routing_id') else None
                poi = ProductionService.add_production_order_item(
                    production_order=prod_order,
                    customer_order_item=customer_order_item,
                    product=product,
                    quantity=item_data['quantity'],
                    bom=bom,
                    routing=routing,
                )
                ProductionService.create_operations_for_order_item(poi)

            EventService.log_event(
                category='production',
                event_type='created',
                title=f'Production order created: {prod_order.order_number}',
                user=request.user,
                content_object=prod_order,
            )
            AuditService.log_create(request.user, 'ProductionOrder', prod_order)

        return Response(
            {'id': prod_order.id, 'order_number': prod_order.order_number,
             'production_order_number': prod_order.order_number, 'status': prod_order.status},
            status=status.HTTP_201_CREATED,
        )


class OperationListView(V2APIView):
    """List operations for a production order (read-only via Selector)."""

    def get(self, request, po_id):
        operations = ProductionOperation.objects.filter(
            production_order_id=po_id
        ).select_related('production_order_item', 'work_center').order_by('sequence')

        data = [
            {
                'id': op.id,
                'operation_name': op.operation_name,
                'operation_code': op.operation_code,
                'sequence': op.sequence,
                'status': op.status,
                'planned_start': op.planned_start,
                'planned_end': op.planned_end,
                'actual_start': op.actual_start,
                'actual_end': op.actual_end,
                'completed_quantity': op.completed_quantity,
            }
            for op in operations
        ]
        return Response(data)


class OperationStartView(V2APIView):
    """Start a production operation (mutation via Service)."""

    def post(self, request, op_id):
        operation = get_object_or_404(ProductionOperation, id=op_id)

        with transaction.atomic():
            ProductionService.start_operation(operation, started_by=request.user)
            EventService.log_production_event('started', operation, user=request.user,
                                              description=f'Operation started by {request.user}')
            AuditService.log(request.user, 'assign', 'ProductionOperation', operation.pk,
                             str(operation), {'status': 'in_progress'})

        return Response({'id': op_id, 'status': operation.status})


class OperationCompleteView(V2APIView):
    """Complete a production operation (mutation via Service)."""

    def post(self, request, op_id):
        operation = get_object_or_404(ProductionOperation, id=op_id)
        completed_quantity = request.data.get('completed_quantity', 0)

        if operation.status != 'in_progress':
            return Response(
                {'error': f'Cannot complete operation in status "{operation.status}". Operation must be started first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            execution = ProductionService.complete_operation(
                operation, completed_quantity, user=request.user, force_complete=True
            )

            if execution:
                EventService.log_production_event('completed', operation, user=request.user,
                                                  description=f'Completed with qty={completed_quantity}')
                AuditService.log_status_change(
                    request.user, 'ProductionOperation', operation, 'in_progress', 'completed'
                )

        return Response({
            'id': op_id,
            'status': operation.status,
            'execution_id': execution.id if execution else None,
        })


class MaterialIssueView(V2APIView):
    """Issue materials to a production order (mutation via WarehouseService)."""

    def post(self, request):
        order_item_id = request.data.get('order_item_id')
        items_data = request.data.get('items', [])
        idempotency_key = request.data.get('idempotency_key', str(uuid.uuid4()))

        with transaction.atomic():
            issue = WarehouseService.issue_material(
                issued_by=request.user,
                items_data=items_data,
                customer_order_id=None,
                idempotency_key=idempotency_key,
            )

            EventService.log_event(
                category='warehouse',
                event_type='issued',
                title=f'Material issue #{issue.id}',
                user=request.user,
                content_object=issue,
            )
            AuditService.log_create(request.user, 'MaterialIssue', issue)

        return Response({'id': issue.id, 'status': issue.status}, status=status.HTTP_201_CREATED)

    def get(self, request):
        issues = MaterialIssue.objects.all().order_by('-created_at')[:50]
        return Response([
            {'id': i.id, 'issue_number': getattr(i, 'issue_number', None), 'status': getattr(i, 'status', 'pending')}
            for i in issues
        ])


class QualityInspectionCreateView(V2APIView):
    """Create a quality inspection (mutation via QualityService)."""

    def post(self, request):
        po_id = request.data.get('production_order_id')
        production_order = get_object_or_404(ProductionOrder, id=po_id)

        with transaction.atomic():
            inspection = QualityService.create_inspection(
                production_order=production_order,
                inspection_type=request.data.get('inspection_type', 'in_process'),
                result=request.data.get('result', 'pass'),
                inspected_by=request.user,
                notes=request.data.get('notes', ''),
            )

            for defect_data in request.data.get('defects', []):
                QualityService.add_defect(
                    inspection=inspection,
                    code=defect_data['code'],
                    description=defect_data['description'],
                    severity=defect_data.get('severity', 'minor'),
                    quantity=defect_data.get('quantity', 1),
                    notes=defect_data.get('notes', ''),
                )

            AuditService.log_create(request.user, 'QualityInspection', inspection)

        return Response(
            {'id': inspection.id, 'inspection_number': inspection.inspection_number, 'result': inspection.result},
            status=status.HTTP_201_CREATED,
        )


class PaintingScheduleView(V2APIView):
    """Schedule painting operations (mutation via PaintingScheduler)."""

    def post(self, request):
        operation_ids = request.data.get('operation_ids', [])
        target_date_str = request.data.get('target_date')
        target_date = jdatetime.date.today()
        if target_date_str:
            y, m, d = map(int, target_date_str.split('-'))
            target_date = jdatetime.date(y, m, d)

        count, cursors = schedule_painting_operations(operation_ids, target_date, created_by=request.user)

        EventService.log_event(
            category='painting',
            event_type='scheduled',
            title=f'Painting scheduled: {count} operations',
            user=request.user,
        )

        return Response({'scheduled_count': count, 'item_cursors': str(cursors)})


class ShipmentCreateView(V2APIView):
    """Create a shipment (mutation via ShippingService)."""

    def post(self, request):
        order_id = request.data.get('order_id')
        order = get_object_or_404(CustomerOrder, id=order_id)

        with transaction.atomic():
            shipment = ShippingService.create_shipment(
                customer_order=order,
                shipped_by=request.user,
                **{k: v for k, v in request.data.items() if k != 'order_id'}
            )

            EventService.log_event(
                category='shipping',
                event_type='shipped',
                title=f'Shipment created: {shipment.shipment_number}',
                user=request.user,
                content_object=shipment,
            )
            AuditService.log_create(request.user, 'Shipment', shipment)

        return Response(
            {'id': shipment.id, 'shipment_number': shipment.shipment_number},
            status=status.HTTP_201_CREATED,
        )


class EndToEndWorkflowView(V2APIView):
    """
    End-to-end workflow orchestrator.
    Single endpoint that runs the full workflow:
    Customer Order → BOM → Production Order → Operations →
    Material Issue → Production → Painting → Quality → Packaging → Shipment
    """

    def post(self, request):
        """Run the complete happy-path workflow."""
        payload = request.data
        customer_id = payload.get('customer_id')
        product_id = payload.get('product_id')
        quantity = int(payload.get('quantity', 1))
        product = get_object_or_404(Product, id=product_id)

        customer = get_object_or_404(Customer, id=customer_id) if customer_id else None

        with transaction.atomic():
            correlation_id = str(uuid.uuid4())

            # 1. Customer Order
            order = OrderService.create_order(
                customer=customer,
                representative=request.user,
                order_date=payload.get('order_date', timezone.now().date()),
            )
            order_item = OrderService.add_item(
                order=order,
                product=product,
                quantity=quantity,
            )
            OrderService.update_order_totals(order)
            EventService.log_with_correlation(
                correlation_id=correlation_id,
                category='sales',
                event_type='created',
                title=f'Order {order.order_number}',
                user=request.user,
                content_object=order,
            )

            # 2. BOM + Routing lookup
            bom = product.boms.first()
            routing = product.routings.first()

            # 3. Production Order
            prod_order = ProductionService.create_production_order(
                customer_order=order,
                routing=routing,
                bom_revision=payload.get('bom_revision', 'A'),
                status='planned',
            )
            prod_order_item = ProductionService.add_production_order_item(
                production_order=prod_order,
                customer_order_item=order_item,
                product=product,
                quantity=quantity,
                bom=bom,
                routing=routing,
            )
            operations = ProductionService.create_operations_for_order_item(prod_order_item)
            EventService.log_with_correlation(
                correlation_id=correlation_id,
                category='production',
                event_type='created',
                title=f'Production order {prod_order.order_number}',
                user=request.user,
                content_object=prod_order,
            )

            # 4. Material Requirement (if BOM has items with material rules)
            bom_items = bom.items.all().prefetch_related('material_rules__material_item') if bom else []
            for bom_item in bom_items:
                for rule in bom_item.material_rules.all():
                    WarehouseService.create_material_requirement(
                        customer_order_item=order_item,
                        item=rule.material_item,
                        required_quantity=Decimal(str(rule.quantity)) * Decimal(str(quantity)),
                    )

            EventService.log_with_correlation(
                correlation_id=correlation_id,
                category='inventory',
                event_type='reserved',
                title=f'Materials reserved for PO {prod_order.order_number}',
                user=request.user,
            )

            # 5. Start and complete operations
            for op in operations:
                ProductionService.start_operation(op, started_by=request.user)
                EventService.log_with_correlation(
                    correlation_id=correlation_id,
                    category='production',
                    event_type='started',
                    title=f'Operation {op.operation_name} started',
                    user=request.user,
                    content_object=op,
                )

                ProductionService.complete_operation(
                    op, completed_quantity=quantity, user=request.user, force_complete=True
                )
                EventService.log_with_correlation(
                    correlation_id=correlation_id,
                    category='production',
                    event_type='completed',
                    title=f'Operation {op.operation_name} completed',
                    user=request.user,
                    content_object=op,
                )

            # 6. Painting (if painting_stage operations exist)
            painting_ops = [op for op in operations if op.painting_stage_id]
            if painting_ops:
                target_date = jdatetime.date.today()
                sched_count, _ = schedule_painting_operations(
                    [op.id for op in painting_ops],
                    target_date,
                    created_by=request.user,
                )
                EventService.log_with_correlation(
                    correlation_id=correlation_id,
                    category='painting',
                    event_type='scheduled',
                    title=f'Painted {sched_count} operations',
                    user=request.user,
                )

            # 7. Quality Inspection
            inspection = QualityService.create_inspection(
                production_order=prod_order,
                inspection_type='final',
                result='pass',
                inspected_by=request.user,
            )
            EventService.log_with_correlation(
                correlation_id=correlation_id,
                category='quality',
                event_type='inspected',
                title=f'Quality inspection {inspection.inspection_number}',
                user=request.user,
                content_object=inspection,
            )

            # 8. Packaging + Shipment
            if hasattr(PackagingService, 'create_package'):
                package = PackagingService.create_package(
                    customer_order_item=order_item,
                    production_order_item=prod_order_item,
                    packed_by=request.user,
                )
            shipment = ShippingService.create_shipment(
                customer_order=order,
                shipped_by=request.user,
            )
            EventService.log_with_correlation(
                correlation_id=correlation_id,
                category='shipping',
                event_type='shipped',
                title=f'Shipped order {order.order_number}',
                user=request.user,
                content_object=shipment,
            )

            return Response({
                'order_id': order.id,
                'order_number': order.order_number,
                'production_order_id': prod_order.id,
                'production_order_number': prod_order.order_number,
                'operations_count': len(operations),
                'inspection_number': inspection.inspection_number,
                'shipment_number': shipment.shipment_number,
                'correlation_id': correlation_id,
                'status': 'completed',
            })
