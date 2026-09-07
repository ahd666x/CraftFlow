from django.conf import settings
from django.db import models
from production.models import ProductionOrder, ProductionOperation


class QualityInspection(models.Model):
    INSPECTION_TYPES = [
        ('incoming', 'ورودی'),
        ('in_process', 'در فرآیند'),
        ('final', 'نهایی'),
        ('outgoing', 'خروجی'),
    ]

    INSPECTION_RESULTS = [
        ('pass', 'قبول'),
        ('fail', 'رد'),
        ('conditional', 'مشروط'),
        ('rework', 'بازسازی'),
    ]

    inspection_number = models.CharField(max_length=50, unique=True, verbose_name="شماره بازرسی")
    inspection_type = models.CharField(max_length=20, choices=INSPECTION_TYPES, verbose_name="نوع بازرسی")
    production_order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name='quality_inspections', verbose_name="سفارش تولید")
    production_operation = models.ForeignKey(ProductionOperation, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="عملیات تولید")
    result = models.CharField(max_length=20, choices=INSPECTION_RESULTS, verbose_name="نتیجه")
    inspected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name="بازرس")
    inspected_at = models.DateTimeField(verbose_name="زمان بازرسی")
    notes = models.TextField(blank=True, verbose_name="یادداشت‌ها")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    class Meta:
        verbose_name = "بازرسی کیفیت"
        verbose_name_plural = "بازرسی‌های کیفیت"
        ordering = ['-inspected_at']

    def __str__(self):
        return f"QI-{self.inspection_number}"


class QualityDefect(models.Model):
    DEFECT_SEVERITY = [
        ('minor', 'جزعی'),
        ('major', 'عمده'),
        ('critical', 'بحرانی'),
    ]

    quality_inspection = models.ForeignKey(QualityInspection, on_delete=models.CASCADE, related_name='defects', verbose_name="بازرسی کیفیت")
    code = models.CharField(max_length=50, verbose_name="کد نقص")
    description = models.CharField(max_length=255, verbose_name="توضیحات")
    severity = models.CharField(max_length=20, choices=DEFECT_SEVERITY, default='minor', verbose_name="شدت")
    quantity = models.PositiveIntegerField(default=1, verbose_name="تعداد")
    image = models.ImageField(upload_to='quality/defects/', blank=True, null=True, verbose_name="تصویر")
    is_reworkable = models.BooleanField(default=True, verbose_name="قابل بازسازی است")
    notes = models.TextField(blank=True, verbose_name="یادداشت")

    class Meta:
        verbose_name = "نقص کیفیت"
        verbose_name_plural = "نقص‌های کیفیت"
        ordering = ['-severity', 'code']

    def __str__(self):
        return f"{self.code} - {self.description}"


class ReworkOrder(models.Model):
    REWORK_STATUS = [
        ('draft', 'پیش‌نویس'),
        ('planned', 'برنامه‌ریزی شده'),
        ('in_progress', 'در حال انجام'),
        ('completed', 'تکمیل شده'),
        ('cancelled', 'لغو شده'),
    ]

    rework_number = models.CharField(max_length=50, unique=True, verbose_name="شماره بازسازی")
    production_order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name='rework_orders', verbose_name="سفارش تولید")
    production_operation = models.ForeignKey(ProductionOperation, on_delete=models.CASCADE, verbose_name="عملیات تولید")
    quality_inspection = models.ForeignKey(QualityInspection, on_delete=models.CASCADE, related_name='rework_orders', verbose_name="بازرسی کیفیت")
    status = models.CharField(max_length=20, choices=REWORK_STATUS, default='draft', verbose_name="وضعیت")
    defect_description = models.TextField(verbose_name="توضیحات نقص")
    repair_description = models.TextField(verbose_name="روش تعمیر")
    quantity = models.PositiveIntegerField(verbose_name="تعداد")
    completed_quantity = models.PositiveIntegerField(default=0, verbose_name="تعداد تکمیل شده")
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="هزینه تخمینی")
    actual_cost = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="هزینه واقعی")
    assigned_to = models.ForeignKey('accounts.Worker', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="مسئول")
    planned_start = models.DateField(null=True, blank=True, verbose_name="شروع برنامه‌ریزی شده")
    planned_end = models.DateField(null=True, blank=True, verbose_name="پایان برنامه‌ریزی شده")
    actual_start = models.DateTimeField(null=True, blank=True, verbose_name="شروع واقعی")
    actual_end = models.DateTimeField(null=True, blank=True, verbose_name="پایان واقعی")
    notes = models.TextField(blank=True, verbose_name="یادداشت‌ها")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    class Meta:
        verbose_name = "سفارش بازسازی"
        verbose_name_plural = "سفارش‌های بازسازی"
        ordering = ['-created_at']

    def __str__(self):
        return f"RWO-{self.rework_number}"


class ReworkOrderItem(models.Model):
    rework_order = models.ForeignKey(ReworkOrder, on_delete=models.CASCADE, related_name='items', verbose_name="سفارش بازسازی")
    quality_defect = models.ForeignKey(QualityDefect, on_delete=models.CASCADE, verbose_name="نقص کیفیت")
    quantity = models.PositiveIntegerField(verbose_name="تعداد")
    repair_action = models.CharField(max_length=255, verbose_name="اقدام تعمیر")
    notes = models.CharField(max_length=255, blank=True, verbose_name="یادداشت")

    class Meta:
        verbose_name = "آیتم سفارش بازسازی"
        verbose_name_plural = "آیتم‌های سفارش بازسازی"
        ordering = ['rework_order', 'id']

    def __str__(self):
        return f"{self.rework_order.rework_number} - {self.quality_defect.code}"
