from decimal import Decimal
from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Item, StockLocation, StockLot, StockBalance, StockLedger, StockReservation, UOM

User = get_user_model()


class InventoryService:
    @staticmethod
    def create_item(category, code, name, uom, item_type='material', **kwargs):
        with transaction.atomic():
            item = Item.objects.create(
                category=category,
                code=code,
                name=name,
                uom=uom,
                item_type=item_type,
                **kwargs
            )
            StockBalance.objects.create(
                item=item,
                location=StockLocation.objects.filter(location_type='warehouse').first(),
                quantity_on_hand=0,
                quantity_reserved=0,
                quantity_available=0,
            )
            return item

    @staticmethod
    def receive_stock(item, location, quantity, lot_number, batch_number='', user=None, reference_document='', reference_id=''):
        with transaction.atomic():
            lot, created = StockLot.objects.get_or_create(
                item=item,
                location=location,
                lot_number=lot_number,
                defaults={
                    'batch_number': batch_number,
                    'quantity': quantity,
                    'received_date': timezone.now().date(),
                    'received_by': user,
                }
            )
            if not created:
                lot.quantity += quantity
                lot.save(update_fields=['quantity'])

            balance, _ = StockBalance.objects.get_or_create(item=item, location=location)
            balance.quantity_on_hand += quantity
            balance.quantity_available += quantity
            balance.last_movement = timezone.now()
            balance.save(update_fields=['quantity_on_hand', 'quantity_available', 'last_movement'])

            ledger = StockLedger.objects.create(
                item=item,
                location=location,
                lot=lot,
                ledger_type='receipt',
                quantity=quantity,
                balance_after=balance.quantity_on_hand,
                reference_document=reference_document,
                reference_id=reference_id,
                created_by=user,
            )
            return ledger

    @staticmethod
    def reserve_stock(item, location, quantity, reference_document, reference_id, user=None, expires_at=None):
        with transaction.atomic():
            balance = StockBalance.objects.get(item=item, location=location)
            if balance.quantity_available < quantity:
                raise ValueError("موجودی کافی برای رزرو نیست")
            balance.quantity_available -= quantity
            balance.quantity_reserved += quantity
            balance.save(update_fields=['quantity_available', 'quantity_reserved'])

            reservation = StockReservation.objects.create(
                item=item,
                location=location,
                quantity=quantity,
                reserved_by=user,
                reference_document=reference_document,
                reference_id=reference_id,
                expires_at=expires_at,
            )
            return reservation

    @staticmethod
    def get_available_quantity(item, location):
        try:
            balance = StockBalance.objects.get(item=item, location=location)
            return balance.quantity_available
        except StockBalance.DoesNotExist:
            return Decimal('0')
