from decimal import Decimal
from django.db import transaction
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Item, StockLocation, StockLot, StockBalance, StockLedger, StockReservation, UOM

User = get_user_model()


class InventoryService:
    @staticmethod
    def create_item(category, code, name, uom, item_type='material', location=None, **kwargs):
        """
        ایجاد آیتم با موجودی اولیه.

        اگر location ارائه نشود، اولین Warehouse location به‌طور خودکار انتخاب می‌شود.
        اگر هیچ Warehouse location وجود نداشته باشد، خطای واضح داده می‌شود.
        """
        with transaction.atomic():
            if location is None:
                location = StockLocation.objects.filter(location_type='warehouse', is_active=True).first()
                if location is None:
                    raise ValidationError(
                        "هیچ مکان انباری فعالی تعریف نشده است. لطفاً ابتدا یک مکان با نوع 'warehouse' ایجاد کنید یا location را صراحتاً ارسال کنید."
                    )

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
                location=location,
                quantity_on_hand=Decimal('0'),
                quantity_reserved=Decimal('0'),
                quantity_available=Decimal('0'),
            )
            return item

    @staticmethod
    def receive_stock(item, location, quantity, lot_number, batch_number='', user=None, reference_document='', reference_id=''):
        """
        رسید موجودی با قفل‌گذاری pessimistic و ثبت در دفتر روزنامه.
        """
        with transaction.atomic():
            if quantity <= 0:
                raise ValidationError("مقدار رسید باید بزرگ‌تر از صفر باشد.")

            lot, created = StockLot.objects.get_or_create(
                item=item,
                location=location,
                lot_number=lot_number,
                defaults={
                    'batch_number': batch_number,
                    'quantity': Decimal('0'),
                    'received_date': timezone.now().date(),
                    'received_by': user,
                }
            )

            # Pessimistic lock
            balance = StockBalance.objects.select_for_update().get(item=item, location=location)

            lot.quantity += quantity
            lot.save(update_fields=['quantity'])

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
        """
        رزرو موجودی با قفل‌گذاری pessimistic.
        """
        with transaction.atomic():
            if quantity <= 0:
                raise ValidationError("مقدار رزرو باید بزرگ‌تر از صفر باشد.")

            balance = StockBalance.objects.select_for_update().get(item=item, location=location)
            if balance.quantity_available < quantity:
                raise ValidationError("موجودی کافی برای رزرو نیست")

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
    def release_reservation(item, location, quantity, reference_document, reference_id):
        """
        آزادسازی رزرو موجودی.
        """
        with transaction.atomic():
            if quantity <= 0:
                raise ValidationError("مقدار آزادسازی باید بزرگ‌تر از صفر باشد.")

            balance = StockBalance.objects.select_for_update().get(item=item, location=location)

            reservation = StockReservation.objects.filter(
                item=item,
                location=location,
                reference_document=reference_document,
                reference_id=reference_id,
                status='active',
            ).first()

            if not reservation:
                raise ValidationError("رزرو فعالی با این شناسه مرجع یافت نشد.")

            release_qty = min(quantity, reservation.quantity)
            reservation.quantity -= release_qty
            if reservation.quantity == 0:
                reservation.status = 'cancelled'
            reservation.save(update_fields=['quantity', 'status'])

            balance.quantity_available += release_qty
            balance.quantity_reserved -= release_qty
            balance.save(update_fields=['quantity_available', 'quantity_reserved'])

            return reservation

    @staticmethod
    def transfer_stock(item, from_location, to_location, quantity, lot_number=None, user=None, reference_document='', reference_id=''):
        """
        انتقال موجودی بین مکان‌ها با ثبت در دفتر روزنامه.
        """
        with transaction.atomic():
            if quantity <= 0:
                raise ValidationError("مقدار انتقال باید بزرگ‌تر از صفر باشد.")

            if from_location == to_location:
                raise ValidationError("مکان مبدأ و مقصد نمی‌توانند یکسان باشند.")

            # Lock both balances
            from_balance = StockBalance.objects.select_for_update().get(item=item, location=from_location)
            to_balance, _ = StockBalance.objects.select_for_update().get_or_create(
                item=item, location=to_location,
                defaults={
                    'quantity_on_hand': Decimal('0'),
                    'quantity_reserved': Decimal('0'),
                    'quantity_available': Decimal('0'),
                }
            )

            if from_balance.quantity_available < quantity:
                raise ValidationError("موجودی کافی در مکان مبدأ برای انتقال نیست.")

            from_balance.quantity_on_hand -= quantity
            from_balance.quantity_available -= quantity
            from_balance.save(update_fields=['quantity_on_hand', 'quantity_available'])

            to_balance.quantity_on_hand += quantity
            to_balance.quantity_available += quantity
            to_balance.last_movement = timezone.now()
            to_balance.save(update_fields=['quantity_on_hand', 'quantity_available', 'last_movement'])

            # Handle lot if provided
            lot = None
            if lot_number:
                from_lot = StockLot.objects.filter(item=item, location=from_location, lot_number=lot_number).first()
                if from_lot:
                    from_lot.quantity -= quantity
                    if from_lot.quantity <= 0:
                        from_lot.delete()
                    else:
                        from_lot.save(update_fields=['quantity'])

                    to_lot, _ = StockLot.objects.get_or_create(
                        item=item,
                        location=to_location,
                        lot_number=lot_number,
                        defaults={
                            'batch_number': from_lot.batch_number if from_lot else '',
                            'quantity': Decimal('0'),
                            'received_date': timezone.now().date(),
                            'received_by': user,
                        }
                    )
                    to_lot.quantity += quantity
                    to_lot.save(update_fields=['quantity'])
                    lot = to_lot

            # Ledger entries
            StockLedger.objects.create(
                item=item,
                location=from_location,
                lot=lot,
                ledger_type='transfer',
                quantity=-quantity,
                balance_after=from_balance.quantity_on_hand,
                reference_document=reference_document,
                reference_id=reference_id,
                created_by=user,
            )
            StockLedger.objects.create(
                item=item,
                location=to_location,
                lot=lot,
                ledger_type='transfer',
                quantity=quantity,
                balance_after=to_balance.quantity_on_hand,
                reference_document=reference_document,
                reference_id=reference_id,
                created_by=user,
            )

            return {'from_balance': from_balance, 'to_balance': to_balance}

    @staticmethod
    def adjust_stock(item, location, quantity_delta, user=None, reference_document='', reference_id='', reason=''):
        """
        اصلاحیه موجودی (افزایش/کاهش) با ثبت در دفتر روزنامه.
        """
        with transaction.atomic():
            if quantity_delta == 0:
                raise ValidationError("مقدار اصلاحیه نمی‌تواند صفر باشد.")

            balance = StockBalance.objects.select_for_update().get(item=item, location=location)
            new_quantity = balance.quantity_on_hand + quantity_delta
            if new_quantity < 0:
                raise ValidationError("موجودی بعد از اصلاحیه نمی‌تواند منفی باشد.")

            balance.quantity_on_hand = new_quantity
            balance.quantity_available = new_quantity - balance.quantity_reserved
            balance.last_movement = timezone.now()
            balance.save(update_fields=['quantity_on_hand', 'quantity_available', 'last_movement'])

            StockLedger.objects.create(
                item=item,
                location=location,
                ledger_type='adjustment',
                quantity=quantity_delta,
                balance_after=balance.quantity_on_hand,
                reference_document=reference_document,
                reference_id=reference_id,
                notes=reason,
                created_by=user,
            )
            return balance

    @staticmethod
    def get_available_quantity(item, location):
        try:
            balance = StockBalance.objects.get(item=item, location=location)
            return balance.quantity_available
        except StockBalance.DoesNotExist:
            return Decimal('0')
