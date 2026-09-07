from django.conf import settings
from django.db import models
from customers.models import Customer
from products.models import Product


class CustomerOrder(models.Model):
    ORDER_STATUS = [
        ('draft', 'پیش‌نویس'),
        ('planned', 'برنامه‌ریزی شده'),
        ('producing', 'در حال تولید'),
        ('completed', 'تکمیل شده'),
        ('cancelled', 'لغو شده'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='orders', verbose_name="مشتری")
    representative = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='represented_orders', verbose_name="نماینده")
    order_number = models.CharField(max_length=50, unique=True, blank=True, verbose_name="شماره سفارش")
    order_date = models.DateField(verbose_name="تاریخ سفارش")
    due_date = models.DateField(null=True, blank=True, verbose_name="تاریخ تحویل")
    priority = models.PositiveSmallIntegerField(default=3, choices=[(1, 'بسیار بالا'), (2, 'بالا'), (3, 'متوسط'), (4, 'پایین')], verbose_name="اولویت")
    status = models.CharField(max_length=20, choices=ORDER_STATUS, default='draft', verbose_name="وضعیت")
    notes = models.TextField(blank=True, verbose_name="یادداشت‌ها")
    total_amount = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name="مبلغ کل")
    paid_amount = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name="مبلغ پرداخت‌شده")
    shipping_cost = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="هزینه حمل")
    discount_amount = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="تخفیف")
    final_amount = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name="مبلغ نهایی")
    vat_amount = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="مالیات ارزش افزوده")
    payment_terms = models.CharField(max_length=100, blank=True, verbose_name="شرایط پرداخت")
    delivery_terms = models.CharField(max_length=100, blank=True, verbose_name="شرایط تحویل")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_sales_orders', verbose_name="ایجادکننده")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='updated_sales_orders', verbose_name="به‌روزرسانی‌کننده")

    class Meta:
        verbose_name = "سفارش مشتری"
        verbose_name_plural = "سفارش‌های مشتری"
        ordering = ['-order_date', '-id']

    def __str__(self):
        return f"SO-{self.order_number or self.id}"


class CustomerOrderItem(models.Model):
    order = models.ForeignKey(CustomerOrder, on_delete=models.CASCADE, related_name='items', verbose_name="سفارش")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='order_items', verbose_name="محصول")
    quantity = models.PositiveIntegerField(default=1, verbose_name="تعداد")
    size = models.CharField(max_length=100, blank=True, verbose_name="اندازه")
    unit_price = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="قیمت واحد")
    line_total = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name="جمع خط")
    notes = models.CharField(max_length=200, blank=True, verbose_name="توضیحات")
    qr_code = models.ImageField(upload_to='qr/', blank=True, null=True, verbose_name="QR کد")
    is_custom = models.BooleanField(default=False, verbose_name="سفارشی")
    production_notes = models.TextField(blank=True, verbose_name="یادداشت‌های تولید")
    estimated_delivery = models.DateField(null=True, blank=True, verbose_name="تحویل پیش‌بینی شده")

    class Meta:
        verbose_name = "آیتم سفارش مشتری"
        verbose_name_plural = "آیتم‌های سفارش مشتری"
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.order.order_number} - {self.product.name} x{self.quantity}"


class OrderItemColor(models.Model):
    PART_CHOICES = [
        ('بدنه', 'بدنه'),
        ('درب', 'درب'),
        ('دستگیره', 'دستگیره'),
        ('پایه', 'پایه'),
        ('صفحه', 'صفحه'),
        ('رینگ', 'رینگ'),
    ]
    CODE_CHOICES = [(str(i), str(i)) for i in range(1, 11)] + [('جناغی', 'جناغی'), ('بتنی', 'بتنی')]

    order_item = models.ForeignKey(CustomerOrderItem, on_delete=models.CASCADE, related_name='colors', verbose_name="آیتم سفارش")
    part = models.CharField(max_length=20, choices=PART_CHOICES, verbose_name="قطعه")
    code = models.CharField(max_length=20, choices=CODE_CHOICES, verbose_name="کد رنگ")

    class Meta:
        verbose_name = "رنگ آیتم سفارش"
        verbose_name_plural = "رنگ‌های آیتم سفارش"
        unique_together = ['order_item', 'part']

    def __str__(self):
        return f"{self.order_item} - {self.part}:{self.code}"


class SalesQuotation(models.Model):
    QUOTE_STATUS = [
        ('draft', 'پیش‌نویس'),
        ('sent', 'ارسال شده'),
        ('accepted', 'تایید شده'),
        ('rejected', 'رد شده'),
        ('expired', 'منقضی شده'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='quotations', verbose_name="مشتری")
    quote_number = models.CharField(max_length=50, unique=True, verbose_name="شماره پیش‌فاکتور")
    quote_date = models.DateField(verbose_name="تاریخ پیش‌فاکتور")
    valid_until = models.DateField(verbose_name="معتبر تا")
    status = models.CharField(max_length=20, choices=QUOTE_STATUS, default='draft', verbose_name="وضعیت")
    notes = models.TextField(blank=True, verbose_name="یادداشت‌ها")
    total_amount = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name="مبلغ کل")
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="درصد تخفیف")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name="ایجادکننده")

    class Meta:
        verbose_name = "پیش‌فاکتور"
        verbose_name_plural = "پیش‌فاکتورها"
        ordering = ['-quote_date']

    def __str__(self):
        return f"Q-{self.quote_number}"


class SalesQuotationItem(models.Model):
    quotation = models.ForeignKey(SalesQuotation, on_delete=models.CASCADE, related_name='items', verbose_name="پیش‌فاکتور")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name="محصول")
    quantity = models.PositiveIntegerField(default=1, verbose_name="تعداد")
    unit_price = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="قیمت واحد")
    discount_amount = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="تخفیف")
    line_total = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name="جمع خط")
    notes = models.CharField(max_length=200, blank=True, verbose_name="توضیحات")

    class Meta:
        verbose_name = "آیتم پیش‌فاکتور"
        verbose_name_plural = "آیتم‌های پیش‌فاکتور"
        ordering = ['quotation', 'id']

    def __str__(self):
        return f"{self.quotation.quote_number} - {self.product.name}"
