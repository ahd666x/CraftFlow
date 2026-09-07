from django.db import transaction
from django.contrib.auth import get_user_model
from .models import MaterialRequirement, MaterialRequest, MaterialRequestItem, MaterialIssue, MaterialIssueItem, MaterialConsumption, MaterialReturn, MaterialReturnItem, MaterialWaste

User = get_user_model()


class WarehouseService:
    @staticmethod
    def create_material_requirement(customer_order_item, item, required_quantity, **kwargs):
        with transaction.atomic():
            req = MaterialRequirement.objects.create(
                customer_order_item=customer_order_item,
                item=item,
                required_quantity=required_quantity,
                **kwargs
            )
            return req

    @staticmethod
    def create_material_request(requested_by, items_data, **kwargs):
        with transaction.atomic():
            request_number = f"MR-{MaterialRequest.objects.count() + 1:06d}"
            material_request = MaterialRequest.objects.create(
                request_number=request_number,
                requested_by=requested_by,
                **kwargs
            )
            for item_data in items_data:
                MaterialRequestItem.objects.create(
                    material_request=material_request,
                    **item_data
                )
            return material_request

    @staticmethod
    def issue_material(issued_by, items_data, customer_order=None, **kwargs):
        with transaction.atomic():
            issue_number = f"MI-{MaterialIssue.objects.count() + 1:06d}"
            material_issue = MaterialIssue.objects.create(
                issue_number=issue_number,
                issued_by=issued_by,
                customer_order=customer_order,
                **kwargs
            )
            for item_data in items_data:
                MaterialIssueItem.objects.create(
                    material_issue=material_issue,
                    **item_data
                )
            return material_issue

    @staticmethod
    def consume_material(material_issue_item, quantity, consumed_by, production_order=None, production_operation=None, **kwargs):
        with transaction.atomic():
            consumption = MaterialConsumption.objects.create(
                material_issue_item=material_issue_item,
                item=material_issue_item.item,
                quantity=quantity,
                consumed_by=consumed_by,
                production_order=production_order,
                production_operation=production_operation,
                **kwargs
            )
            return consumption
