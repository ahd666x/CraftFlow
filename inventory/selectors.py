from django.db.models import Sum, F, Value, DecimalField, Case, When, Q
from decimal import Decimal
from .models import Item, StockLocation, StockBalance, StockLedger, StockReservation, StockLot

class InventorySelectors:
    @staticmethod
    def get_stock_summary(item=None, location=None):
        qs = StockBalance.objects.all()
        if item:
            qs = qs.filter(item=item)
        if location:
            qs = qs.filter(location=location)
        return qs.select_related('item', 'item__uom', 'location').annotate(
            total_value=F('quantity_on_hand') * F('item__unit_cost')
        )

    @staticmethod
    def get_low_stock_items():
        return Item.objects.filter(
            is_active=True
        ).annotate(
            total_stock=Sum('stock_balances__quantity_on_hand')
        ).filter(
            Q(total_stock__lte=F('min_stock')) | Q(total_stock__isnull=True)
        )

    @staticmethod
    def get_stock_movements(item=None, date_from=None, date_to=None):
        qs = StockLedger.objects.all()
        if item:
            qs = qs.filter(item=item)
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        return qs.select_related('item', 'location', 'created_by').order_by('-created_at')

    @staticmethod
    def get_active_reservations():
        return StockReservation.objects.filter(
            status='active'
        ).select_related('item', 'location', 'reserved_by')
