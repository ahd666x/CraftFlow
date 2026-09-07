from django.conf import settings
from django.db import models
from products.models import Product, ProductPart


class WorkCenter(models.Model):
    code = models.CharField(max_length=50, unique=True, verbose_name="کد")
    name = models.CharField(max_length=100, verbose_name="نام")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    capacity_per_hour = models.DecimalField(max_digits=8, decimal_places=2, default=0, verbose_name="ظرفیت در ساعت")
    efficiency_factor = models.DecimalField(max_digits=4, decimal_places=2, default=1.0, verbose_name="ضریب بازده")
    setup_time_minutes = models.PositiveIntegerField(default=0, verbose_name="زمان آماده‌سازی (دقیقه)")
    cost_per_hour = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="هزینه هر ساعت")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="مدیر")

    class Meta:
        verbose_name = "مرکز کار"
        verbose_name_plural = "مراکز کار"
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class Resource(models.Model):
    RESOURCE_TYPES = [
        ('machine', 'ماشین'),
        ('tool', 'ابزار'),
        ('fixture', 'گیج و مهار'),
        ('measurement', 'دستگاه اندازه‌گیری'),
    ]

    work_center = models.ForeignKey(WorkCenter, on_delete=models.CASCADE, related_name='resources', verbose_name="مرکز کار")
    code = models.CharField(max_length=50, verbose_name="کد")
    name = models.CharField(max_length=100, verbose_name="نام")
    resource_type = models.CharField(max_length=20, choices=RESOURCE_TYPES, default='machine', verbose_name="نوع")
    model = models.CharField(max_length=100, blank=True, verbose_name="مدل")
    serial_number = models.CharField(max_length=100, blank=True, verbose_name="شماره سریال")
    capacity = models.DecimalField(max_digits=8, decimal_places=2, default=1, verbose_name="ظرفیت")
    unit = models.CharField(max_length=20, blank=True, verbose_name="واحد")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    purchase_date = models.DateField(null=True, blank=True, verbose_name="تاریخ خرید")
    last_maintenance = models.DateField(null=True, blank=True, verbose_name="آخرین تعمیر")
    next_maintenance = models.DateField(null=True, blank=True, verbose_name="تعمیر بعدی")
    notes = models.TextField(blank=True, verbose_name="یادداشت")

    class Meta:
        verbose_name = "منبع"
        verbose_name_plural = "منابع"
        ordering = ['work_center', 'code']
        unique_together = ['work_center', 'code']

    def __str__(self):
        return f"{self.work_center.code} - {self.code}"


class Skill(models.Model):
    code = models.CharField(max_length=50, unique=True, verbose_name="کد")
    name = models.CharField(max_length=100, verbose_name="نام مهارت")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    level = models.PositiveSmallIntegerField(default=1, verbose_name="سطح")
    is_certified = models.BooleanField(default=False, verbose_name="نیاز به گواهینامه")

    class Meta:
        verbose_name = "مهارت"
        verbose_name_plural = "مهارت‌ها"
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class Routing(models.Model):
    ROUTING_STATUS = [
        ('draft', 'پیش‌نویس'),
        ('active', 'فعال'),
        ('obsolete', 'منسوخ شده'),
    ]

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='routings', verbose_name="محصول")
    revision = models.CharField(max_length=20, default='A', verbose_name="Revision")
    name = models.CharField(max_length=100, verbose_name="نام مسیر")
    effective_date = models.DateField(verbose_name="تاریخ اجرا")
    status = models.CharField(max_length=20, choices=ROUTING_STATUS, default='draft', verbose_name="وضعیت")
    total_time_minutes = models.PositiveIntegerField(default=0, verbose_name="زمان کل (دقیقه)")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name="ایجادکننده")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    class Meta:
        verbose_name = "مسیر تولید"
        verbose_name_plural = "مسیرهای تولید"
        ordering = ['product', '-effective_date']
        unique_together = ['product', 'revision']

    def __str__(self):
        return f"RT-{self.product.name} - {self.revision}"


class RoutingOperation(models.Model):
    routing = models.ForeignKey(Routing, on_delete=models.CASCADE, related_name='operations', verbose_name="مسیر تولید")
    sequence = models.PositiveIntegerField(verbose_name="ترتیب")
    operation_name = models.CharField(max_length=100, verbose_name="نام عملیات")
    operation_code = models.CharField(max_length=50, verbose_name="کد عملیات")
    work_center = models.ForeignKey(WorkCenter, on_delete=models.PROTECT, verbose_name="مرکز کار")
    setup_time_minutes = models.PositiveIntegerField(default=0, verbose_name="زمان آماده‌سازی (دقیقه)")
    run_time_per_unit_minutes = models.DecimalField(max_digits=8, decimal_places=2, default=0, verbose_name="زمان اجرا در واحد (دقیقه)")
    queue_time_minutes = models.PositiveIntegerField(default=0, verbose_name="زمان انتظار (دقیقه)")
    is_inspection = models.BooleanField(default=False, verbose_name="بازرسی است")
    is_mandatory = models.BooleanField(default=True, verbose_name="اجباری")
    notes = models.TextField(blank=True, verbose_name="یادداشت")

    class Meta:
        verbose_name = "عملیات مسیر تولید"
        verbose_name_plural = "عملیات‌های مسیر تولید"
        ordering = ['routing', 'sequence']

    def __str__(self):
        return f"{self.routing} - {self.sequence}. {self.operation_name}"


class RoutingDependency(models.Model):
    DEPENDENCY_TYPES = [
        ('FS', 'پایان تا شروع (Finish to Start)'),
        ('SS', 'شروع تا شروع (Start to Start)'),
        ('FF', 'پایان تا پایان (Finish to Finish)'),
        ('SF', 'شروع تا پایان (Start to Finish)'),
    ]

    routing = models.ForeignKey(Routing, on_delete=models.CASCADE, related_name='dependencies', verbose_name="مسیر تولید")
    predecessor = models.ForeignKey(RoutingOperation, on_delete=models.CASCADE, related_name='successors', verbose_name="عملیات قبل")
    successor = models.ForeignKey(RoutingOperation, on_delete=models.CASCADE, related_name='predecessors', verbose_name="عملیات بعد")
    dependency_type = models.CharField(max_length=5, choices=DEPENDENCY_TYPES, default='FS', verbose_name="نوع وابستگی")
    lag_minutes = models.PositiveIntegerField(default=0, verbose_name="تأخیر (دقیقه)")
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    class Meta:
        verbose_name = "وابستگی مسیر تولید"
        verbose_name_plural = "وابستگی‌های مسیر تولید"
        unique_together = ['routing', 'predecessor', 'successor']

    def __str__(self):
        return f"{self.predecessor} → {self.successor} ({self.get_dependency_type_display()})"


class ProductionPart(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='production_parts', verbose_name="محصول")
    part = models.ForeignKey(ProductPart, on_delete=models.PROTECT, related_name='production_parts', verbose_name="قطعه")
    name = models.CharField(max_length=100, verbose_name="نام قطعه تولید")
    code = models.CharField(max_length=50, blank=True, verbose_name="کد")
    length = models.DecimalField(max_digits=7, decimal_places=1, verbose_name="طول")
    width = models.DecimalField(max_digits=7, decimal_places=1, verbose_name="عرض")
    thickness = models.DecimalField(max_digits=7, decimal_places=1, verbose_name="ضخامت")
    grain = models.CharField(max_length=20, blank=True, verbose_name="جهت رگه")
    f26 = models.CharField(max_length=100, blank=True, verbose_name="نوار لبه F26")
    f18 = models.CharField(max_length=100, blank=True, verbose_name="نوار لبه F18")
    f4 = models.CharField(max_length=100, blank=True, verbose_name="نوار لبه F4")
    f5 = models.CharField(max_length=100, blank=True, verbose_name="نوار لبه F5")
    f3 = models.CharField(max_length=100, blank=True, verbose_name="بارکد F3")
    f2 = models.CharField(max_length=100, blank=True, verbose_name="نام فنی F2")
    pname = models.CharField(max_length=100, blank=True, verbose_name="نام محصول")
    turn = models.BooleanField(default=False, verbose_name="چرخش")
    routing_code = models.CharField(max_length=255, blank=True, verbose_name="کد مسیر")

    class Meta:
        verbose_name = "قطعه تولید"
        verbose_name_plural = "قطعات تولید"
        ordering = ['product', 'code']

    def __str__(self):
        return f"{self.product.name} - {self.name} ({self.length}x{self.width})"
