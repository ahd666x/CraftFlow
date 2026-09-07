from django.conf import settings
from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey


class BusinessEvent(models.Model):
    EVENT_CATEGORIES = [
        ('sales', 'فروش'),
        ('production', 'تولید'),
        ('inventory', 'انبار'),
        ('warehouse', 'انبار مواد'),
        ('shipping', 'ارسال'),
        ('quality', 'کیفیت'),
        ('painting', 'نقاشی'),
        ('packaging', 'بسته‌بندی'),
        ('system', 'سیستم'),
    ]

    EVENT_TYPES = [
        ('created', 'ایجاد'),
        ('updated', 'به‌روزرسانی'),
        ('deleted', 'حذف'),
        ('status_changed', 'تغییر وضعیت'),
        ('assigned', 'تخصیص'),
        ('started', 'شروع'),
        ('completed', 'تکمیل'),
        ('cancelled', 'لغو'),
        ('issued', 'صدور'),
        ('received', 'دریافت'),
        ('transferred', 'انتقال'),
        ('consumed', 'مصرف'),
        ('returned', 'مرجوعی'),
        ('inspected', 'بازرسی'),
        ('shipped', 'ارسال'),
        ('delivered', 'تحویل'),
        ('scrapped', 'ضایعات'),
        ('reserved', 'رزرو'),
        ('released', 'آزادسازی'),
    ]

    category = models.CharField(max_length=20, choices=EVENT_CATEGORIES, verbose_name="دسته رویداد")
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES, verbose_name="نوع رویداد")
    title = models.CharField(max_length=200, verbose_name="عنوان")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    occurred_at = models.DateTimeField(verbose_name="زمان رخ دادن")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name="ثبت‌کننده")

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True, verbose_name="نوع محتوا")
    object_id = models.PositiveIntegerField(null=True, blank=True, verbose_name="شناسه شی")
    content_object = GenericForeignKey('content_type', 'object_id')

    metadata = models.JSONField(default=dict, blank=True, verbose_name="اطلاعات اضافی")
    is_system = models.BooleanField(default=False, verbose_name="رویداد سیستمی")

    class Meta:
        verbose_name = "رویداد کسب‌وکار"
        verbose_name_plural = "رویدادهای کسب‌وکار"
        ordering = ['-occurred_at']
        indexes = [
            models.Index(fields=['category', 'event_type', 'occurred_at']),
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        return f"{self.get_category_display()} - {self.get_event_type_display()} - {self.title}"


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('create', 'ایجاد'),
        ('update', 'به‌روزرسانی'),
        ('delete', 'حذف'),
        ('view', 'مشاهده'),
        ('export', 'خروجی'),
        ('import', 'ورودی'),
        ('login', 'ورود'),
        ('logout', 'خروج'),
        ('approve', 'تایید'),
        ('reject', 'رد'),
        ('cancel', 'لغو'),
        ('assign', 'تخصیص'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name="کاربر")
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, verbose_name="عملیات")
    model_name = models.CharField(max_length=100, verbose_name="نام مدل")
    object_id = models.CharField(max_length=50, blank=True, verbose_name="شناسه شی")
    object_repr = models.CharField(max_length=200, blank=True, verbose_name="نماینده شی")
    changes = models.JSONField(default=dict, blank=True, verbose_name="تغییرات")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="آدرس IP")
    user_agent = models.TextField(blank=True, verbose_name="مرورگر")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="زمان")

    class Meta:
        verbose_name = "لاگ تغییرات"
        verbose_name_plural = "لاگ‌های تغییرات"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'action', 'timestamp']),
            models.Index(fields=['model_name', 'object_id']),
        ]

    def __str__(self):
        return f"{self.user} - {self.get_action_display()} - {self.model_name} #{self.object_id}"


class Barcode(models.Model):
    BARCODE_TYPES = [
        ('qr', 'QR Code'),
        ('code128', 'Code 128'),
        ('code39', 'Code 39'),
        ('ean13', 'EAN-13'),
        ('upc', 'UPC'),
    ]

    code = models.CharField(max_length=100, unique=True, verbose_name="کد")
    barcode_type = models.CharField(max_length=20, choices=BARCODE_TYPES, default='qr', verbose_name="نوع بارکد")
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True, verbose_name="نوع محتوا")
    object_id = models.PositiveIntegerField(null=True, blank=True, verbose_name="شناسه شی")
    content_object = GenericForeignKey('content_type', 'object_id')
    data = models.JSONField(default=dict, blank=True, verbose_name="داده‌های بارکد")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    last_scanned_at = models.DateTimeField(null=True, blank=True, verbose_name="آخرین اسکن")
    scan_count = models.PositiveIntegerField(default=0, verbose_name="تعداد اسکن")

    class Meta:
        verbose_name = "بارکد"
        verbose_name_plural = "بارکدها"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.code} ({self.get_barcode_type_display()})"


class MigrationMap(models.Model):
    MIGRATION_TYPES = [
        ('customer', 'مشتری'),
        ('order', 'سفارش'),
        ('order_item', 'آیتم سفارش'),
        ('product', 'محصول'),
        ('part', 'قطعه'),
        ('bom', 'BOM'),
        ('routing', 'مسیر تولید'),
        ('task', 'تسک تولید'),
        ('material', 'ماده اولیه'),
        ('stock_movement', 'حرکت انبار'),
        ('raw_material', 'ماده خام'),
        ('supplier', 'تامین‌کننده'),
        ('purchase_order', 'سفارش خرید'),
        ('worker', 'کارگر'),
        ('painting_process', 'روند نقاشی'),
        ('painting_stage', 'مرحله نقاشی'),
    ]

    migration_type = models.CharField(max_length=30, choices=MIGRATION_TYPES, verbose_name="نوع مهاجرت")
    old_id = models.CharField(max_length=50, verbose_name="شناسه قدیمی")
    new_id = models.CharField(max_length=50, verbose_name="شناسه جدید")
    old_app = models.CharField(max_length=50, blank=True, verbose_name="اپ قدیمی")
    old_model = models.CharField(max_length=100, blank=True, verbose_name="مدل قدیمی")
    new_app = models.CharField(max_length=50, blank=True, verbose_name="اپ جدید")
    new_model = models.CharField(max_length=100, blank=True, verbose_name="مدل جدید")
    is_legacy = models.BooleanField(default=False, verbose_name="قدیمی/میراث")
    legacy_reason = models.CharField(max_length=255, blank=True, verbose_name="دلیل قدیمی بودن")
    migrated_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان مهاجرت")
    migration_run = models.ForeignKey('MigrationRun', on_delete=models.CASCADE, related_name='mappings', null=True, blank=True, verbose_name="اجرای مهاجرت")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="اطلاعات اضافی")

    class Meta:
        verbose_name = "نگاشت مهاجرت"
        verbose_name_plural = "نگاشت‌های مهاجرت"
        ordering = ['migration_type', 'old_id']
        unique_together = ['migration_type', 'old_id', 'old_app']

    def __str__(self):
        return f"{self.migration_type}: {self.old_id} → {self.new_id}"


class MigrationRun(models.Model):
    MIGRATION_STATUS = [
        ('pending', 'در انتظار'),
        ('running', 'در حال اجرا'),
        ('completed', 'تکمیل شده'),
        ('failed', 'ناموفق'),
        ('partial', 'جزئی'),
    ]

    phase = models.CharField(max_length=50, verbose_name="فاز")
    name = models.CharField(max_length=100, verbose_name="نام")
    status = models.CharField(max_length=20, choices=MIGRATION_STATUS, default='pending', verbose_name="وضعیت")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان شروع")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان تکمیل")
    records_processed = models.PositiveIntegerField(default=0, verbose_name="رکوردهای پردازش شده")
    records_failed = models.PositiveIntegerField(default=0, verbose_name="رکوردهای ناموفق")
    records_skipped = models.PositiveIntegerField(default=0, verbose_name="رکوردهای رد شده")
    log = models.TextField(blank=True, verbose_name="لاگ")
    errors = models.JSONField(default=list, blank=True, verbose_name="خطاها")
    warnings = models.JSONField(default=list, blank=True, verbose_name="هشدارها")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name="ایجادکننده")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    class Meta:
        verbose_name = "اجرای مهاجرت"
        verbose_name_plural = "اجرای‌های مهاجرت"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.phase} - {self.name} ({self.get_status_display()})"
