from decimal import Decimal
from django.db import transaction
from django.contrib.auth import get_user_model
from .models import CustomerOrder, CustomerOrderItem, OrderItemColor

User = get_user_model()


class OrderService:
    @staticmethod
    def calculate_item_price(product, size=''):
        if not product:
            return Decimal('0')
        order_size_str = size or product.default_size
        default_size_str = product.default_size
        if not order_size_str or not default_size_str:
            return Decimal(str(product.base_price or 0))
        import re
        order_numbers = re.findall(r'\d+', order_size_str)
        default_numbers = re.findall(r'\d+', default_size_str)
        if not order_numbers or not default_numbers:
            return Decimal(str(product.base_price or 0))
        order_length = int(order_numbers[0])
        default_length = int(default_numbers[0])
        if default_length == 0:
            return Decimal(str(product.base_price or 0))
        base_price = Decimal(str(product.base_price or 0))
        increment = Decimal(str(product.price_increment_per_cm or 0))
        diff_percent = Decimal(order_length - default_length) * increment / Decimal('100')
        price_increase = base_price * diff_percent
        final_price = base_price + price_increase
        if final_price < 0:
            return Decimal('0')
        return final_price.quantize(Decimal('1'))

    @staticmethod
    def create_order(customer, representative=None, **kwargs):
        with transaction.atomic():
            order = CustomerOrder.objects.create(
                customer=customer,
                representative=representative,
                **kwargs
            )
            return order

    @staticmethod
    def add_item(order, product, quantity, size='', notes='', colors=None):
        with transaction.atomic():
            unit_price = OrderService.calculate_item_price(product, size)
            item = CustomerOrderItem.objects.create(
                order=order,
                product=product,
                quantity=quantity,
                size=size,
                notes=notes,
                unit_price=unit_price,
            )
            if colors:
                for part, code in colors.items():
                    if code:
                        OrderItemColor.objects.create(
                            order_item=item,
                            part=part,
                            code=code,
                        )
            return item

    @staticmethod
    def update_order_totals(order):
        with transaction.atomic():
            total = sum(item.line_total for item in order.items.all())
            order.total_amount = total
            order.final_amount = total + order.shipping_cost - order.discount_amount + order.vat_amount
            order.save(update_fields=['total_amount', 'final_amount'])
            return order

    @staticmethod
    def get_order_progress(order):
        total_items = order.items.count()
        packed_items = sum(1 for item in order.items.all() if item.is_fully_packed)
        shipped_items = sum(1 for item in order.items.all() if item.is_fully_shipped)
        painting_complete = sum(1 for item in order.items.all() if item.is_painting_complete)
        return {
            'total_items': total_items,
            'packed_items': packed_items,
            'shipped_items': shipped_items,
            'painting_complete': painting_complete,
            'progress_percent': (shipped_items / total_items * 100) if total_items > 0 else 0,
        }
