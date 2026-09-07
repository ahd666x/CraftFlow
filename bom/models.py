from django.conf import settings
from django.db import models
from products.models import Product, ProductPart


class BOM(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='boms', verbose_name="محصول")
    revision = models.CharField(max_length=20, default='A', verbose_name="Revision")
    effective_date = models.DateField(verbose_name="تاریخ اجرا")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name="ایجادکننده")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    class Meta:
        verbose_name = "فرمول ساخت (BOM)"
        verbose_name_plural = "فرمول‌های ساخت (BOM)"
        ordering = ['product', '-effective_date']
        unique_together = ['product', 'revision']

    def __str__(self):
        return f"BOM {self.product.name} - {self.revision}"


class BOMItem(models.Model):
    bom = models.ForeignKey(BOM, on_delete=models.CASCADE, related_name='items', verbose_name="BOM")
    part = models.ForeignKey(ProductPart, on_delete=models.PROTECT, related_name='bom_items', verbose_name="قطعه")
    quantity = models.PositiveIntegerField(default=1, verbose_name="تعداد در هر محصول")
    scrap_factor = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="ضریب دورریز")
    notes = models.CharField(max_length=255, blank=True, verbose_name="یادداشت")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="ترتیب")

    class Meta:
        verbose_name = "آیتم BOM"
        verbose_name_plural = "آیتم‌های BOM"
        ordering = ['bom', 'sort_order']

    def __str__(self):
        return f"{self.bom} - {self.part.name} x{self.quantity}"


class BOMItemMaterialRule(models.Model):
    RULE_TYPE_CHOICES = [
        ('standard', 'استاندارد'),
        ('color_override', 'جایگزینی بر اساس رنگ'),
        ('size_adjustment', 'تنظیم بر اساس اندازه'),
        ('alternative', 'جایگزین'),
    ]

    bom_item = models.ForeignKey(BOMItem, on_delete=models.CASCADE, related_name='material_rules', verbose_name="آیتم BOM")
    rule_type = models.CharField(max_length=30, choices=RULE_TYPE_CHOICES, default='standard', verbose_name="نوع قانون")
    condition = models.CharField(max_length=100, blank=True, verbose_name="شرط")
    material_item = models.ForeignKey('inventory.Item', on_delete=models.PROTECT, verbose_name="ماده اولیه")
    quantity = models.DecimalField(max_digits=10, decimal_places=3, verbose_name="مقدار")
    is_primary = models.BooleanField(default=True, verbose_name="اولیه")
    priority = models.PositiveIntegerField(default=0, verbose_name="اولویت")
    notes = models.CharField(max_length=255, blank=True, verbose_name="یادداشت")

    class Meta:
        verbose_name = "قانون ماده BOM"
        verbose_name_plural = "قوانین ماده BOM"
        ordering = ['bom_item', '-is_primary', 'priority']

    def __str__(self):
        return f"{self.bom_item} - {self.material_item.name} ({self.get_rule_type_display()})"
