from django.conf import settings
from django.db import models
from customers.models import Customer


class ProductCategory(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="نام دسته")
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='children', verbose_name="دسته والد")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="ترتیب نمایش")

    class Meta:
        verbose_name = "دسته بندی محصول"
        verbose_name_plural = "دسته‌بندی‌های محصول"
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class Product(models.Model):
    category = models.ForeignKey(ProductCategory, on_delete=models.PROTECT, related_name='products', verbose_name="دسته")
    name = models.CharField(max_length=200, verbose_name="نام محصول")
    code = models.CharField(max_length=50, unique=True, blank=True, verbose_name="کد محصول")
    color = models.CharField(max_length=100, blank=True, verbose_name="رنگ")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    default_size = models.CharField(max_length=100, blank=True, verbose_name="سایز پیش‌فرض")
    default_colors = models.JSONField(default=dict, blank=True, verbose_name="رنگ‌های پیش‌فرض")
    base_price = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="قیمت پایه")
    price_increment_per_cm = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="درصد افزایش قیمت به ازای هر سانتی‌متر")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    estimated_production_days = models.PositiveIntegerField(default=0, verbose_name="تعداد روز تولید پیش‌بینی")
    weight_kg = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="وزن (کیلوگرم)")
    dimensions = models.CharField(max_length=100, blank=True, verbose_name="ابعاد")

    class Meta:
        verbose_name = "محصول"
        verbose_name_plural = "محصولات"
        ordering = ['category', 'name']

    def __str__(self):
        return f"{self.category} - {self.name}"


class ProductPart(models.Model):
    GRAIN_CHOICES = [
        ('vertical', 'عمودی'),
        ('horizontal', 'افقی'),
        ('none', 'بدون جهت'),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='parts', verbose_name="محصول")
    name = models.CharField(max_length=100, verbose_name="نام قطعه")
    code = models.CharField(max_length=50, blank=True, verbose_name="کد قطعه")
    length = models.DecimalField(max_digits=7, decimal_places=1, verbose_name="طول (X)")
    width = models.DecimalField(max_digits=7, decimal_places=1, verbose_name="عرض (Y)")
    thickness = models.DecimalField(max_digits=7, decimal_places=1, verbose_name="ضخامت (Z)")
    grain = models.CharField(max_length=20, choices=GRAIN_CHOICES, default='none', verbose_name="جهت رگه")
    f26 = models.CharField(max_length=100, blank=True, verbose_name="نوار لبه F26")
    f18 = models.CharField(max_length=100, blank=True, verbose_name="نوار لبه F18")
    f4 = models.CharField(max_length=100, blank=True, verbose_name="نوار لبه F4")
    f5 = models.CharField(max_length=100, blank=True, verbose_name="نوار لبه F5")
    f3 = models.CharField(max_length=100, blank=True, verbose_name="بارکد F3")
    f2 = models.CharField(max_length=100, blank=True, verbose_name="نام فنی F2")
    pname = models.CharField(max_length=100, blank=True, verbose_name="نام محصول")
    turn = models.BooleanField(default=False, verbose_name="چرخش")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="ترتیب")

    class Meta:
        verbose_name = "قطعه محصول"
        verbose_name_plural = "قطعات محصول"
        ordering = ['product', 'sort_order']

    def __str__(self):
        return f"{self.product.name} - {self.name} ({self.length}x{self.width})"


class ProductRevision(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='revisions', verbose_name="محصول")
    revision_number = models.CharField(max_length=20, verbose_name="شمارهRevision")
    effective_date = models.DateField(verbose_name="تاریخ اجرا")
    description = models.TextField(blank=True, verbose_name="تغییرات")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name="ایجادکننده")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    class Meta:
        verbose_name = "Revision محصول"
        verbose_name_plural = "Revisionهای محصول"
        ordering = ['-effective_date']
        unique_together = ['product', 'revision_number']

    def __str__(self):
        return f"{self.product} - {self.revision_number}"
