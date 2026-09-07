from django.conf import settings
from django.db import models
from accounts.models import Worker


class PaintingProcess(models.Model):
    name = models.CharField(max_length=100, verbose_name="نام روند")
    code = models.CharField(max_length=20, unique=True, verbose_name="کد روند")
    color_codes = models.JSONField(default=list, verbose_name="لیست کدهای رنگی مرتبط")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    estimated_time_minutes = models.PositiveIntegerField(default=0, verbose_name="زمان تخمینی (دقیقه)")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاریخ به‌روزرسانی")

    class Meta:
        verbose_name = "روند نقاشی"
        verbose_name_plural = "روندهای نقاشی"
        ordering = ['code']

    def __str__(self):
        return self.name


class PaintingProcessStage(models.Model):
    SKILL_CHOICES = [
        ('painter', 'نقاش'),
        ('general', 'زیرکار'),
        ('helper', 'کمک'),
    ]

    process = models.ForeignKey(PaintingProcess, on_delete=models.CASCADE, related_name='stages', verbose_name="روند")
    sequence = models.PositiveSmallIntegerField(verbose_name="ترتیب")
    name = models.CharField(max_length=100, verbose_name="نام مرحله")
    duration_minutes = models.PositiveIntegerField(verbose_name="زمان انجام (دقیقه)")
    drying_time_minutes = models.PositiveIntegerField(default=0, verbose_name="زمان خشک‌شدن (دقیقه)")
    required_skill = models.CharField(max_length=50, choices=SKILL_CHOICES, default='painter', verbose_name="مهارت مورد نیاز")
    temperature_min = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, verbose_name="حداقل دما (سانتی‌گراد)")
    temperature_max = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, verbose_name="حداکثر دما (سانتی‌گراد)")
    humidity_max = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, verbose_name="حداکثر رطوبت (%)")
    is_mandatory = models.BooleanField(default=True, verbose_name="اجباری")
    notes = models.TextField(blank=True, verbose_name="یادداشت")

    class Meta:
        verbose_name = "مرحله نقاشی"
        verbose_name_plural = "مراحل نقاشی"
        ordering = ['process', 'sequence']
        unique_together = ['process', 'sequence']

    def __str__(self):
        return f"{self.process.name} - مرحله {self.sequence}: {self.name}"


class PaintingAssignmentRule(models.Model):
    RULE_TYPE_CHOICES = [
        ('priority', 'اولویت‌دهی'),
        ('exclusive', 'محدودکننده'),
        ('exclusion', 'منع‌کننده'),
    ]

    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name='painting_assignment_rules', verbose_name="کارگر")
    painting_stage = models.ForeignKey(PaintingProcessStage, on_delete=models.CASCADE, null=True, blank=True, verbose_name="مرحله نقاشی")
    color_codes = models.JSONField(null=True, blank=True, verbose_name="کدهای رنگ")
    process = models.ForeignKey(PaintingProcess, on_delete=models.CASCADE, null=True, blank=True, verbose_name="روند نقاشی")
    rule_type = models.CharField(max_length=20, choices=RULE_TYPE_CHOICES, default='priority', verbose_name="نوع قانون")
    priority = models.IntegerField(default=100, verbose_name="اولویت")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    class Meta:
        verbose_name = "قانون تخصیص نقاشی"
        verbose_name_plural = "قوانین تخصیص نقاشی"
        ordering = ['-priority', 'worker']

    def __str__(self):
        return f"{self.worker} [{self.get_rule_type_display()}]"


class PaintingSchedule(models.Model):
    SCHEDULE_STATUS = [
        ('draft', 'پیش‌نویس'),
        ('published', 'منتشر شده'),
        ('in_progress', 'در حال اجرا'),
        ('completed', 'تکمیل شده'),
        ('cancelled', 'لغو شده'),
    ]

    date = models.DateField(verbose_name="تاریخ")
    status = models.CharField(max_length=20, choices=SCHEDULE_STATUS, default='draft', verbose_name="وضعیت")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name="ایجادکننده")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    published_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان انتشار")
    notes = models.TextField(blank=True, verbose_name="یادداشت‌ها")

    class Meta:
        verbose_name = "برنامه نقاشی"
        verbose_name_plural = "برنامه‌های نقاشی"
        ordering = ['-date']
        unique_together = ['date']

    def __str__(self):
        return f"برنامه نقاشی {self.date}"


class PaintingScheduleItem(models.Model):
    schedule = models.ForeignKey(PaintingSchedule, on_delete=models.CASCADE, related_name='items', verbose_name="برنامه")
    production_operation = models.ForeignKey('production.ProductionOperation', on_delete=models.CASCADE, verbose_name="عملیات تولید")
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, verbose_name="کارگر")
    painting_stage = models.ForeignKey(PaintingProcessStage, on_delete=models.CASCADE, verbose_name="مرحله نقاشی")
    scheduled_start = models.DateTimeField(verbose_name="شروع برنامه‌ریزی شده")
    scheduled_end = models.DateTimeField(verbose_name="پایان برنامه‌ریزی شده")
    actual_start = models.DateTimeField(null=True, blank=True, verbose_name="شروع واقعی")
    actual_end = models.DateTimeField(null=True, blank=True, verbose_name="پایان واقعی")
    status = models.CharField(max_length=20, default='scheduled', verbose_name="وضعیت")
    notes = models.CharField(max_length=255, blank=True, verbose_name="یادداشت")
    is_cascade_moved = models.BooleanField(default=False, verbose_name="جابه‌جایی زنجیره‌ای")

    class Meta:
        verbose_name = "آیتم برنامه نقاشی"
        verbose_name_plural = "آیتم‌های برنامه نقاشی"
        ordering = ['schedule', 'scheduled_start']

    def __str__(self):
        return f"{self.schedule.date} - {self.worker} - {self.painting_stage.name}"
