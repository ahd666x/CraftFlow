from django.conf import settings
from django.db import models
from sales.models import CustomerOrderItem
from production.models import ProductionOrderItem, WIPUnit


class Package(models.Model):
    PACKAGE_STATUS = [
        ('draft', 'پیش‌نویس'),
        ('packed', 'بسته‌بندی شده'),
        ('shipped', 'ارسال شده'),
        ('delivered', 'تحویل داده شده'),
        ('returned', 'مرجوع شده'),
    ]

    customer_order_item = models.ForeignKey(CustomerOrderItem, on_delete=models.CASCADE, related_name='packages', verbose_name="آیتم سفارش مشتری")
    production_order_item = models.ForeignKey(ProductionOrderItem, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="آیتم سفارش تولید")
    wip_unit = models.ForeignKey(WIPUnit, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="واحد WIP")
    package_number = models.CharField(max_length=50, verbose_name="شماره بسته")
    status = models.CharField(max_length=20, choices=PACKAGE_STATUS, default='draft', verbose_name="وضعیت")
    packed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان بسته‌بندی")
    packed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='packed_packages', verbose_name="بسته‌بندی‌کننده")
    qr_code = models.ImageField(upload_to='qr/packaging/', blank=True, null=True, verbose_name="QR کد")
    weight_kg = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="وزن (کیلوگرم)")
    dimensions = models.CharField(max_length=100, blank=True, verbose_name="ابعاد")
    notes = models.TextField(blank=True, verbose_name="یادداشت‌ها")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    class Meta:
        verbose_name = "بسته"
        verbose_name_plural = "بسته‌ها"
        ordering = ['-created_at']
        unique_together = ['customer_order_item', 'package_number']

    def __str__(self):
        return f"PKG-{self.package_number}"


class PackageItem(models.Model):
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name='items', verbose_name="بسته")
    item = models.ForeignKey('inventory.Item', on_delete=models.PROTECT, verbose_name="کالا")
    quantity = models.PositiveIntegerField(verbose_name="تعداد")
    serial_numbers = models.JSONField(default=list, blank=True, verbose_name="شماره سریال‌ها")
    notes = models.CharField(max_length=255, blank=True, verbose_name="یادداشت")

    class Meta:
        verbose_name = "آیتم بسته"
        verbose_name_plural = "آیتم‌های بسته"
        ordering = ['package', 'id']

    def __str__(self):
        return f"{self.package.package_number} - {self.item.code}"


class PackagingSpecification(models.Model):
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, related_name='packaging_specs', verbose_name="محصول")
    package_type = models.CharField(max_length=50, verbose_name="نوع بسته‌بندی")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    items_per_package = models.PositiveIntegerField(verbose_name="تعداد در هر بسته")
    package_weight_kg = models.DecimalField(max_digits=8, decimal_places=2, default=0, verbose_name="وزن بسته (کیلوگرم)")
    package_dimensions = models.CharField(max_length=100, blank=True, verbose_name="ابعاد بسته")
    requires_pallet = models.BooleanField(default=False, verbose_name="نیاز به پالت دارد")
    stacking_limit = models.PositiveIntegerField(default=1, verbose_name="حداکثر انباشت")
    image = models.ImageField(upload_to='packaging/specs/', blank=True, null=True, verbose_name="تصویر نمونه")
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    class Meta:
        verbose_name = "مشخصه بسته‌بندی"
        verbose_name_plural = "مشخصه‌های بسته‌بندی"
        ordering = ['product', 'package_type']
        unique_together = ['product', 'package_type']

    def __str__(self):
        return f"{self.product.name} - {self.package_type}"
