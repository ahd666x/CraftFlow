from django.conf import settings
from django.db import models
from sales.models import CustomerOrder, CustomerOrderItem
from planning.models import Routing, ProductionPart


class ProductionOrder(models.Model):
    PO_STATUS = [
        ('draft', 'پیش‌نویس'),
        ('planned', 'برنامه‌ریزی شده'),
        ('released', 'آغاز شده'),
        ('in_progress', 'در حال انجام'),
        ('paused', 'متوقف موقت'),
        ('completed', 'تکمیل شده'),
        ('cancelled', 'لغو شده'),
    ]

    order = models.ForeignKey(CustomerOrder, on_delete=models.PROTECT, related_name='production_orders', verbose_name="سفارش مشتری")
    order_number = models.CharField(max_length=50, unique=True, verbose_name="شماره سفارش تولید")
    routing = models.ForeignKey(Routing, on_delete=models.PROTECT, related_name='production_orders', verbose_name="مسیر تولید")
    bom_revision = models.CharField(max_length=20, verbose_name="Revision BOM")
    status = models.CharField(max_length=20, choices=PO_STATUS, default='draft', verbose_name="وضعیت")
    planned_start = models.DateField(null=True, blank=True, verbose_name="شروع برنامه‌ریزی شده")
    planned_end = models.DateField(null=True, blank=True, verbose_name="پایان برنامه‌ریزی شده")
    actual_start = models.DateTimeField(null=True, blank=True, verbose_name="شروع واقعی")
    actual_end = models.DateTimeField(null=True, blank=True, verbose_name="پایان واقعی")
    priority = models.PositiveSmallIntegerField(default=3, verbose_name="اولویت")
    notes = models.TextField(blank=True, verbose_name="یادداشت‌ها")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name="ایجادکننده")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاریخ به‌روزرسانی")

    class Meta:
        verbose_name = "سفارش تولید"
        verbose_name_plural = "سفارش‌های تولید"
        ordering = ['-created_at']

    def __str__(self):
        return f"PO-{self.order_number}"


class ProductionOrderItem(models.Model):
    production_order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name='items', verbose_name="سفارش تولید")
    customer_order_item = models.ForeignKey(CustomerOrderItem, on_delete=models.PROTECT, related_name='production_order_items', verbose_name="آیتم سفارش مشتری")
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT, verbose_name="محصول")
    quantity = models.PositiveIntegerField(verbose_name="تعداد")
    completed_quantity = models.PositiveIntegerField(default=0, verbose_name="تعداد تکمیل شده")
    scrapped_quantity = models.PositiveIntegerField(default=0, verbose_name="تعداد دورریز")
    bom = models.ForeignKey('bom.BOM', on_delete=models.PROTECT, verbose_name="BOM")
    routing = models.ForeignKey(Routing, on_delete=models.PROTECT, verbose_name="مسیر تولید")
    notes = models.TextField(blank=True, verbose_name="یادداشت‌ها")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    class Meta:
        verbose_name = "آیتم سفارش تولید"
        verbose_name_plural = "آیتم‌های سفارش تولید"
        ordering = ['production_order', 'id']

    def __str__(self):
        return f"{self.production_order.order_number} - {self.product.name}"


class ProductionBatch(models.Model):
    BATCH_STATUS = [
        ('planned', 'برنامه‌ریزی شده'),
        ('started', 'شروع شده'),
        ('in_progress', 'در حال انجام'),
        ('completed', 'تکمیل شده'),
        ('cancelled', 'لغو شده'),
    ]

    production_order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name='batches', verbose_name="سفارش تولید")
    batch_number = models.CharField(max_length=50, verbose_name="شماره بچ")
    status = models.CharField(max_length=20, choices=BATCH_STATUS, default='planned', verbose_name="وضعیت")
    planned_quantity = models.PositiveIntegerField(verbose_name="تعداد برنامه‌ریزی شده")
    actual_quantity = models.PositiveIntegerField(default=0, verbose_name="تعداد واقعی")
    scrapped_quantity = models.PositiveIntegerField(default=0, verbose_name="تعداد دورریز")
    planned_start = models.DateTimeField(null=True, blank=True, verbose_name="شروع برنامه‌ریزی شده")
    planned_end = models.DateTimeField(null=True, blank=True, verbose_name="پایان برنامه‌ریزی شده")
    actual_start = models.DateTimeField(null=True, blank=True, verbose_name="شروع واقعی")
    actual_end = models.DateTimeField(null=True, blank=True, verbose_name="پایان واقعی")
    notes = models.TextField(blank=True, verbose_name="یادداشت‌ها")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    class Meta:
        verbose_name = "بچ تولید"
        verbose_name_plural = "بچ‌های تولید"
        ordering = ['production_order', 'batch_number']
        unique_together = ['production_order', 'batch_number']

    def __str__(self):
        return f"BATCH-{self.batch_number}"


class ProductionBatchItem(models.Model):
    batch = models.ForeignKey(ProductionBatch, on_delete=models.CASCADE, related_name='items', verbose_name="بچ")
    production_order_item = models.ForeignKey(ProductionOrderItem, on_delete=models.CASCADE, related_name='batch_items', verbose_name="آیتم سفارش تولید")
    quantity = models.PositiveIntegerField(verbose_name="تعداد")
    serial_numbers = models.JSONField(default=list, blank=True, verbose_name="شماره سریال‌ها")

    class Meta:
        verbose_name = "آیتم بچ تولید"
        verbose_name_plural = "آیتم‌های بچ تولید"
        ordering = ['batch', 'id']

    def __str__(self):
        return f"{self.batch.batch_number} - {self.production_order_item.product.name}"


class ProductionOperation(models.Model):
    OPERATION_STATUS = [
        ('waiting', 'در انتظار'),
        ('ready', 'آماده'),
        ('in_progress', 'در حال انجام'),
        ('paused', 'متوقف موقت'),
        ('completed', 'تکمیل شده'),
        ('skipped', 'رد شده'),
        ('failed', 'ناموفق'),
    ]

    production_order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name='operations', verbose_name="سفارش تولید")
    production_order_item = models.ForeignKey(ProductionOrderItem, on_delete=models.CASCADE, related_name='operations', verbose_name="آیتم سفارش تولید")
    operation_name = models.CharField(max_length=100, verbose_name="نام عملیات")
    operation_code = models.CharField(max_length=50, verbose_name="کد عملیات")
    work_center = models.ForeignKey('planning.WorkCenter', on_delete=models.PROTECT, verbose_name="مرکز کار")
    sequence = models.PositiveIntegerField(verbose_name="ترتیب")
    status = models.CharField(max_length=20, choices=OPERATION_STATUS, default='waiting', verbose_name="وضعیت")
    planned_start = models.DateTimeField(null=True, blank=True, verbose_name="شروع برنامه‌ریزی شده")
    planned_end = models.DateTimeField(null=True, blank=True, verbose_name="پایان برنامه‌ریزی شده")
    actual_start = models.DateTimeField(null=True, blank=True, verbose_name="شروع واقعی")
    actual_end = models.DateTimeField(null=True, blank=True, verbose_name="پایان واقعی")
    setup_time_minutes = models.PositiveIntegerField(default=0, verbose_name="زمان آماده‌سازی (دقیقه)")
    run_time_minutes = models.PositiveIntegerField(default=0, verbose_name="زمان اجرا (دقیقه)")
    completed_quantity = models.PositiveIntegerField(default=0, verbose_name="تعداد تکمیل شده")
    scrapped_quantity = models.PositiveIntegerField(default=0, verbose_name="تعداد دورریز")
    notes = models.TextField(blank=True, verbose_name="یادداشت‌ها")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاریخ به‌روزرسانی")

    class Meta:
        verbose_name = "عملیات تولید"
        verbose_name_plural = "عملیات‌های تولید"
        ordering = ['production_order', 'sequence']
        indexes = [
            models.Index(fields=['production_order', 'sequence']),
            models.Index(fields=['status', 'planned_start']),
        ]

    def __str__(self):
        return f"{self.production_order.order_number} - {self.operation_name}"


class OperationAssignment(models.Model):
    ASSIGNMENT_STATUS = [
        ('assigned', 'تخصیص داده شده'),
        ('accepted', 'پذیرفته شده'),
        ('started', 'شروع شده'),
        ('completed', 'تکمیل شده'),
        ('released', ' آزاد شده'),
    ]

    operation = models.ForeignKey(ProductionOperation, on_delete=models.CASCADE, related_name='assignments', verbose_name="عملیات")
    worker = models.ForeignKey('accounts.Worker', on_delete=models.CASCADE, related_name='assignments', verbose_name="کارگر")
    status = models.CharField(max_length=20, choices=ASSIGNMENT_STATUS, default='assigned', verbose_name="وضعیت")
    assigned_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان تخصیص")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان شروع")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان تکمیل")
    notes = models.TextField(blank=True, verbose_name="یادداشت")

    class Meta:
        verbose_name = "تخصیص عملیات"
        verbose_name_plural = "تخصیص‌های عملیات"
        ordering = ['-assigned_at']
        unique_together = ['operation', 'worker']

    def __str__(self):
        return f"{self.operation} - {self.worker}"


class OperationExecution(models.Model):
    operation = models.ForeignKey(ProductionOperation, on_delete=models.CASCADE, related_name='executions', verbose_name="عملیات")
    worker = models.ForeignKey('accounts.Worker', on_delete=models.CASCADE, verbose_name="کارگر", null=True, blank=True)
    started_at = models.DateTimeField(verbose_name="زمان شروع")
    ended_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان پایان")
    quantity_produced = models.PositiveIntegerField(default=0, verbose_name="تعداد تولید شده")
    quantity_scrapped = models.PositiveIntegerField(default=0, verbose_name="تعداد دورریز")
    setup_time_minutes = models.PositiveIntegerField(default=0, verbose_name="زمان آماده‌سازی")
    run_time_minutes = models.PositiveIntegerField(default=0, verbose_name="زمان اجرا")
    notes = models.TextField(blank=True, verbose_name="یادداشت")
    is_completed = models.BooleanField(default=False, verbose_name="تکمیل شده")

    class Meta:
        verbose_name = "اجرای عملیات"
        verbose_name_plural = "اجراهای عملیات"
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.operation} - {self.worker} @ {self.started_at}"


class WIPUnit(models.Model):
    WIP_STATUS = [
        ('in_progress', 'در حال انجام'),
        ('waiting', 'در انتظار'),
        ('completed', 'تکمیل شده'),
        ('scrapped', 'ضایعات'),
    ]

    production_order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name='wip_units', verbose_name="سفارش تولید")
    production_order_item = models.ForeignKey(ProductionOrderItem, on_delete=models.CASCADE, related_name='wip_units', verbose_name="آیتم سفارش تولید")
    serial_number = models.CharField(max_length=100, unique=True, verbose_name="شماره سریال")
    status = models.CharField(max_length=20, choices=WIP_STATUS, default='in_progress', verbose_name="وضعیت")
    current_operation = models.ForeignKey(ProductionOperation, null=True, blank=True, on_delete=models.SET_NULL, related_name='current_wip_units', verbose_name="عملیات فعلی")
    quantity = models.PositiveIntegerField(default=1, verbose_name="تعداد")
    notes = models.TextField(blank=True, verbose_name="یادداشت")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاریخ تکمیل")

    class Meta:
        verbose_name = "واحد WIP"
        verbose_name_plural = "واحدهای WIP"
        ordering = ['-created_at']

    def __str__(self):
        return f"WIP-{self.serial_number}"


class WIPTransfer(models.Model):
    wip_unit = models.ForeignKey(WIPUnit, on_delete=models.CASCADE, related_name='transfers', verbose_name="واحد WIP")
    from_operation = models.ForeignKey(ProductionOperation, null=True, blank=True, on_delete=models.SET_NULL, related_name='transfers_from', verbose_name="از عملیات")
    to_operation = models.ForeignKey(ProductionOperation, on_delete=models.CASCADE, related_name='transfers_to', verbose_name="به عملیات")
    from_location = models.ForeignKey('inventory.StockLocation', null=True, blank=True, on_delete=models.SET_NULL, related_name='wip_transfers_from', verbose_name="از مکان")
    to_location = models.ForeignKey('inventory.StockLocation', null=True, blank=True, on_delete=models.SET_NULL, related_name='wip_transfers_to', verbose_name="به مکان")
    transferred_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name="انتقال‌دهنده")
    transferred_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان انتقال")
    notes = models.CharField(max_length=255, blank=True, verbose_name="یادداشت")

    class Meta:
        verbose_name = "انتقال WIP"
        verbose_name_plural = "انتقال‌های WIP"
        ordering = ['-transferred_at']

    def __str__(self):
        return f"{self.wip_unit.serial_number}: {self.from_operation} → {self.to_operation}"
