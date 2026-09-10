from django.urls import path
from .views import (
    CustomerOrderListCreateView,
    ProductionOrderCreateView,
    OperationListView,
    OperationStartView,
    OperationCompleteView,
    MaterialIssueView,
    QualityInspectionCreateView,
    PaintingScheduleView,
    ShipmentCreateView,
    EndToEndWorkflowView,
)

app_name = 'v2_api'

urlpatterns = [
    path('orders/', CustomerOrderListCreateView.as_view(), name='orders'),
    path('orders/<int:order_id>/production/', ProductionOrderCreateView.as_view(), name='create_production'),
    path('production/<int:po_id>/operations/', OperationListView.as_view(), name='operations'),
    path('operations/<int:op_id>/start/', OperationStartView.as_view(), name='start_operation'),
    path('operations/<int:op_id>/complete/', OperationCompleteView.as_view(), name='complete_operation'),
    path('warehouse/issue/', MaterialIssueView.as_view(), name='material_issue'),
    path('quality/inspection/', QualityInspectionCreateView.as_view(), name='quality_inspection'),
    path('painting/schedule/', PaintingScheduleView.as_view(), name='painting_schedule'),
    path('shipping/shipment/', ShipmentCreateView.as_view(), name='shipment_create'),
    path('workflow/e2e/', EndToEndWorkflowView.as_view(), name='e2e_workflow'),
]
