from django.conf import settings
from django.db import models
from sales.models import CustomerOrder, CustomerOrderItem
from packaging.models import Package


class Shipment(models.Model):
    SHIPMENT_STATUS = [
        ('draft', 'پیش‌نویس'),
        ('ready', 'آماده ارسال'),
        ('in_transit', 'در حال حمل'),
        ('delivered', 'تحویل داده شده'),
        ('returned', 'مرجوع شده'),
        ('cancelled', 'لغو شده'),
    ]

    shipment_number = models.CharField(max_length=50, unique=True, verbose_name="شماره ارسال")
    customer_order = models.ForeignKey(CustomerOrder, on_delete=models.PROTECT, related_name='shipments', verbose_name="سفارش مشتری")
    customer = models.ForeignKey('customers.Customer', on_delete=models.PROTECT, related_name='shipments', verbose_name="مشتری")
    status = models.CharField(max_length=20, choices=SHIPMENT_STATUS, default='draft', verbose_name="وضعیت")
    shipment_date = models.DateField(null=True, blank=True, verbose_name="تاریخ ارسال")
    delivery_date = models.DateField(null=True, blank=True, verbose_name="تاریخ تحویل")
    carrier = models.CharField(max_length=100, blank=True, verbose_name="حمل‌ونقل")
    tracking_number = models.CharField(max_length=100, blank=True, verbose_name="شماره پیگیری")
    plate_number = models.CharField(max_length=50, blank=True, verbose_name="شماره پلاک")
    driver_name = models.CharField(max_length=100, blank=True, verbose_name="نام راننده")
    driver_phone = models.CharField(max_length=20, blank=True, verbose_name="تلفن راننده")
    shipping_cost = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="هزینه حمل")
    insurance_cost = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="هزینه بیمه")
    total_weight_kg = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="وزن کل (کیلوگرم)")
    total_volume_m3 = models.DecimalField(max_digits=10, decimal_places=4, default=0, verbose_name="حجم کل (متر مکعب)")
    notes = models.TextField(blank=True, verbose_name="یادداشت‌ها")
    delivery_notes = models.TextField(blank=True, verbose_name="یادداشت‌های تحویل")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name="ایجادکننده")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاریخ به‌روزرسانی")

    class Meta:
        verbose_name = "ارسال"
        verbose_name_plural = "ارسال‌ها"
        ordering = ['-shipment_date', '-created_at']

    def __str__(self):
        return f"SH-{self.shipment_number}"


class ShipmentItem(models.Model):
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name='items', verbose_name="ارسال")
    package = models.ForeignKey(Package, on_delete=models.CASCADE, verbose_name="بسته")
    quantity = models.PositiveIntegerField(verbose_name="تعداد")
    weight_kg = models.DecimalField(max_digits=8, decimal_places=2, default=0, verbose_name="وزن (کیلوگرم)")
    volume_m3 = models.DecimalField(max_digits=8, decimal_places=4, default=0, verbose_name="حجم (متر مکعب)")
    notes = models.CharField(max_length=255, blank=True, verbose_name="یادداشت")

    class Meta:
        verbose_name = "آیتم ارسال"
        verbose_name_plural = "آیتم‌های ارسال"
        ordering = ['shipment', 'id']

    def __str__(self):
        return f"{self.shipment.shipment_number} - {self.package.package_number}"


class ShipmentTracking(models.Model):
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name='tracking_entries', verbose_name="ارسال")
    status = models.CharField(max_length=20, verbose_name="وضعیت")
    location = models.CharField(max_length=100, blank=True, verbose_name="موقعیت")
    timestamp = models.DateTimeField(verbose_name="زمان")
    notes = models.TextField(blank=True, verbose_name="یادداشت")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name="ثبت‌کننده")

    class Meta:
        verbose_name = "پیگیری ارسال"
        verbose_name_plural = "پیگیری‌های ارسال"
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.shipment.shipment_number} - {self.status} @ {self.timestamp}"
