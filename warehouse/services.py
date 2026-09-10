from decimal import Decimal
from django.db import transaction, DatabaseError
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from inventory.models import Item, StockLocation, StockLot, StockBalance, StockLedger
from inventory.services import InventoryService
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
    def issue_material(issued_by, items_data, customer_order=None, idempotency_key=None, **kwargs):
        """
        صدور مواد با کلید idempotency و به‌روزرسانی StockBalance/StockLedger.

        هر آیتم باید شامل item, source_location, target_location, quantity, lot (اختیاری) باشد.
        """
        with transaction.atomic():
            if idempotency_key:
                existing = MaterialIssue.objects.filter(idempotency_key=idempotency_key).first()
                if existing:
                    raise ValidationError(f"صدور مواد با کلید idempotency '{idempotency_key}' قبلاً ثبت شده است.")

            issue_number = f"MI-{MaterialIssue.objects.count() + 1:06d}"
            material_issue = MaterialIssue.objects.create(
                issue_number=issue_number,
                issued_by=issued_by,
                customer_order=customer_order,
                idempotency_key=idempotency_key or '',
                notes=kwargs.get('notes', ''),
                **{k: v for k, v in kwargs.items() if k != 'notes'}
            )
            for item_data in items_data:
                item = item_data.get('item')
                source_location = item_data.get('source_location')
                target_location = item_data.get('target_location')
                quantity = item_data.get('quantity', Decimal('0'))
                lot = item_data.get('lot')

                if not item or not source_location or not target_location:
                    raise ValidationError("Item، مکان مبدأ و مقصد برای صدور مواد اجباری هستند.")

                if quantity <= 0:
                    raise ValidationError("مقدار صدور باید بزرگ‌تر از صفر باشد.")

                mii = MaterialIssueItem.objects.create(
                    material_issue=material_issue,
                    item=item,
                    source_location=source_location,
                    target_location=target_location,
                    quantity=quantity,
                    lot=lot,
                    notes=item_data.get('notes', ''),
                    material_request_item=item_data.get('material_request_item'),
                )

                source_balance = StockBalance.objects.select_for_update().get(item=item, location=source_location)
                if source_balance.quantity_available < quantity:
                    raise ValidationError(f"موجودی کافی در انبار برای {item.code} وجود ندارد.")

                source_balance.quantity_on_hand -= quantity
                source_balance.quantity_available -= quantity
                source_balance.last_movement = timezone.now()
                source_balance.save(update_fields=['quantity_on_hand', 'quantity_available', 'last_movement'])

                target_balance, _ = StockBalance.objects.select_for_update().get_or_create(
                    item=item, location=target_location,
                    defaults={
                        'quantity_on_hand': Decimal('0'),
                        'quantity_reserved': Decimal('0'),
                        'quantity_available': Decimal('0'),
                    }
                )
                target_balance.quantity_on_hand += quantity
                target_balance.quantity_available += quantity
                target_balance.last_movement = timezone.now()
                target_balance.save(update_fields=['quantity_on_hand', 'quantity_available', 'last_movement'])

                StockLedger.objects.create(
                    item=item,
                    location=source_location,
                    lot=lot,
                    ledger_type='issue',
                    quantity=-quantity,
                    balance_after=source_balance.quantity_on_hand,
                    reference_document=f"MaterialIssue:{material_issue.issue_number}",
                    reference_id=str(material_issue.id),
                    created_by=issued_by,
                )
                StockLedger.objects.create(
                    item=item,
                    location=target_location,
                    lot=lot,
                    ledger_type='receipt',
                    quantity=quantity,
                    balance_after=target_balance.quantity_on_hand,
                    reference_document=f"MaterialIssue:{material_issue.issue_number}",
                    reference_id=str(material_issue.id),
                    created_by=issued_by,
                )

                if lot:
                    from_lot = StockLot.objects.select_for_update().filter(item=item, location=source_location, lot_number=lot.lot_number).first()
                    if from_lot:
                        from_lot.quantity -= quantity
                        if from_lot.quantity <= 0:
                            from_lot.delete()
                        else:
                            from_lot.save(update_fields=['quantity'])

                    to_lot, _ = StockLot.objects.select_for_update().get_or_create(
                        item=item,
                        location=target_location,
                        lot_number=lot.lot_number,
                        defaults={
                            'batch_number': getattr(lot, 'batch_number', ''),
                            'quantity': Decimal('0'),
                            'received_date': timezone.now().date(),
                            'received_by': issued_by,
                        }
                    )
                    to_lot.quantity += quantity
                    to_lot.save(update_fields=['quantity'])

            return material_issue

    @staticmethod
    def consume_material(item, quantity, consumed_by, production_order=None, production_operation=None, location=None, lot=None, idempotency_key=None, material_issue_item=None, **kwargs):
        """
        مصرف مواد با کلید idempotency و به‌روزرسانی StockBalance/StockLedger.

        مصرف مستقل از صدور است؛ item، location و lot باید صراحتاً ارائه شوند.
        """
        with transaction.atomic():
            if quantity <= 0:
                raise ValidationError("مقدار مصرف باید بزرگ‌تر از صفر باشد.")

            if not item or not location:
                raise ValidationError("Item و مکان برای مصرف مواد اجباری هستند.")

            if idempotency_key:
                existing = MaterialConsumption.objects.filter(
                    idempotency_key=idempotency_key
                ).first()
                if existing:
                    raise ValidationError(f"مصرف مواد با کلید idempotency '{idempotency_key}' قبلاً ثبت شده است.")

            balance = StockBalance.objects.select_for_update().get(item=item, location=location)
            if balance.quantity_available < quantity:
                raise ValidationError(f"موجودی کافی در انبار برای مصرف {item.code} وجود ندارد.")

            balance.quantity_on_hand -= quantity
            balance.quantity_available -= quantity
            balance.last_movement = timezone.now()
            balance.save(update_fields=['quantity_on_hand', 'quantity_available', 'last_movement'])

            StockLedger.objects.create(
                item=item,
                location=location,
                lot=lot,
                ledger_type='consumption',
                quantity=-quantity,
                balance_after=balance.quantity_on_hand,
                reference_document=f"MaterialConsumption:{idempotency_key or 'direct'}",
                reference_id=idempotency_key or str(hash((item.id, quantity, timezone.now()))),
                created_by=consumed_by,
            )

            consumption = MaterialConsumption.objects.create(
                material_issue_item=material_issue_item,
                item=item,
                quantity=quantity,
                consumption_date=timezone.now(),
                consumed_by=consumed_by,
                production_order=production_order,
                production_operation=production_operation,
                idempotency_key=idempotency_key or '',
                notes=f"{kwargs.get('notes', '')} [idempotency_key:{idempotency_key}]".strip() if idempotency_key else kwargs.get('notes', ''),
                **{k: v for k, v in kwargs.items() if k != 'notes'}
            )
            return consumption

    @staticmethod
    def return_material(returned_by, items_data, customer_order=None, **kwargs):
        """
        مرجوعی مواد با به‌روزرسانی StockBalance/StockLedger.
        """
        with transaction.atomic():
            return_number = f"MRT-{MaterialReturn.objects.count() + 1:06d}"
            material_return = MaterialReturn.objects.create(
                return_number=return_number,
                returned_by=returned_by,
                customer_order=customer_order,
                notes=kwargs.get('notes', ''),
                **{k: v for k, v in kwargs.items() if k != 'notes'}
            )
            for item_data in items_data:
                item = item_data.get('item')
                source_location = item_data.get('source_location')
                target_location = item_data.get('target_location')
                quantity = item_data.get('quantity', Decimal('0'))
                lot = item_data.get('lot')

                if not item or not source_location or not target_location:
                    raise ValidationError("Item، مکان مبدأ و مقصد برای مرجوعی مواد اجباری هستند.")

                if quantity <= 0:
                    raise ValidationError("مقدار مرجوعی باید بزرگ‌تر از صفر باشد.")

                MaterialReturnItem.objects.create(
                    material_return=material_return,
                    item=item,
                    source_location=source_location,
                    target_location=target_location,
                    quantity=quantity,
                    lot=lot,
                    reason=item_data.get('reason', ''),
                    notes=item_data.get('notes', ''),
                    material_issue_item=item_data.get('material_issue_item'),
                )

                to_balance = StockBalance.objects.select_for_update().get(item=item, location=target_location)
                to_balance.quantity_on_hand += quantity
                to_balance.quantity_available += quantity
                to_balance.last_movement = timezone.now()
                to_balance.save(update_fields=['quantity_on_hand', 'quantity_available', 'last_movement'])

                StockLedger.objects.create(
                    item=item,
                    location=target_location,
                    lot=lot,
                    ledger_type='return',
                    quantity=quantity,
                    balance_after=to_balance.quantity_on_hand,
                    reference_document=f"MaterialReturn:{material_return.return_number}",
                    reference_id=str(material_return.id),
                    created_by=returned_by,
                )

            return material_return

    @staticmethod
    def waste_material(recorded_by, item, location, quantity, reason, disposal_method='', cost=Decimal('0'), lot=None, **kwargs):
        """
        ضایعات مواد با به‌روزرسانی StockBalance/StockLedger.
        """
        with transaction.atomic():
            if not item or not location:
                raise ValidationError("Item و مکان برای ضایعات مواد اجباری هستند.")

            if quantity <= 0:
                raise ValidationError("مقدار ضایعات باید بزرگ‌تر از صفر باشد.")

            balance = StockBalance.objects.select_for_update().get(item=item, location=location)
            if balance.quantity_available < quantity:
                raise ValidationError(f"موجودی کافی در انبار برای ضایعات {item.code} وجود ندارد.")

            balance.quantity_on_hand -= quantity
            balance.quantity_available -= quantity
            balance.last_movement = timezone.now()
            balance.save(update_fields=['quantity_on_hand', 'quantity_available', 'last_movement'])

            StockLedger.objects.create(
                item=item,
                location=location,
                lot=lot,
                ledger_type='waste',
                quantity=-quantity,
                balance_after=balance.quantity_on_hand,
                reference_document=f"MaterialWaste:{hash((item.id, quantity, timezone.now()))}",
                reference_id=str(hash((item.id, quantity, timezone.now()))),
                created_by=recorded_by,
                notes=reason,
            )

            waste = MaterialWaste.objects.create(
                item=item,
                location=location,
                quantity=quantity,
                waste_date=timezone.now(),
                recorded_by=recorded_by,
                reason=reason,
                disposal_method=disposal_method,
                cost=cost,
                notes=kwargs.get('notes', ''),
                **{k: v for k, v in kwargs.items() if k != 'notes'}
            )
            return waste
