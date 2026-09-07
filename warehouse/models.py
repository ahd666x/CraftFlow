from django.conf import settings
from django.db import models
from inventory.models import Item, StockLocation, StockReservation
from sales.models import CustomerOrder, CustomerOrderItem


class MaterialRequirement(models.Model):
    REQ_STATUS = [
        ('draft', 'پیش‌نویس'),
        ('planned', 'برنامه‌ریزی شده'),
        ('requested', 'درخواست شده'),
        ('issued', 'صادر شده'),
        ('consumed', 'مصرف شده'),
        ('returned', 'مرجوع شده'),
        ('cancelled', 'لغو شده'),
    ]

    customer_order_item = models.ForeignKey(CustomerOrderItem, on_delete=models.CASCADE, related_name='material_requirements', verbose_name="آیتم سفارش")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='material_requirements', verbose_name="کالا")
    required_quantity = models.DecimalField(max_digits=12, decimal_places=3, verbose_name="مقدار مورد نیاز")
    reserved_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0, verbose_name="مقدار رزرو شده")
    issued_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0, verbose_name="مقدار صادر شده")
    consumed_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0, verbose_name="مقدار مصرف شده")
    returned_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0, verbose_name="مقدار مرجوع شده")
    wasted_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0, verbose_name="مقدار ضایعات")
    status = models.CharField(max_length=20, choices=REQ_STATUS, default='draft', verbose_name="وضعیت")
    needed_by_date = models.DateField(null=True, blank=True, verbose_name="نیاز به تاریخ")
    notes = models.TextField(blank=True, verbose_name="یادداشت")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاریخ به‌روزرسانی")

    class Meta:
        verbose_name = "نیاز مواد اولیه"
        verbose_name_plural = "نیازهای مواد اولیه"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.item.code} برای {self.customer_order_item}"


class MaterialRequest(models.Model):
    REQ_STATUS = [
        ('draft', 'پیش‌نویس'),
        ('submitted', 'ثبت شده'),
        ('approved', 'تایید شده'),
        ('rejected', 'رد شده'),
        ('processed', 'پردازش شده'),
        ('cancelled', 'لغو شده'),
    ]

    request_number = models.CharField(max_length=50, unique=True, verbose_name="شماره درخواست")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='material_requests', verbose_name="درخواست‌دهنده")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_material_requests', verbose_name="تاییدکننده")
    status = models.CharField(max_length=20, choices=REQ_STATUS, default='draft', verbose_name="وضعیت")
    request_date = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ درخواست")
    needed_date = models.DateField(null=True, blank=True, verbose_name="تاریخ نیاز")
    notes = models.TextField(blank=True, verbose_name="یادداشت‌ها")
    is_urgent = models.BooleanField(default=False, verbose_name="فوری")
    customer_order = models.ForeignKey(CustomerOrder, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="سفارش مرتبط")

    class Meta:
        verbose_name = "درخواست مواد"
        verbose_name_plural = "درخواست‌های مواد"
        ordering = ['-request_date']

    def __str__(self):
        return f"MR-{self.request_number}"


class MaterialRequestItem(models.Model):
    material_request = models.ForeignKey(MaterialRequest, on_delete=models.CASCADE, related_name='items', verbose_name="درخواست مواد")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, verbose_name="کالا")
    source_location = models.ForeignKey(StockLocation, on_delete=models.PROTECT, related_name='request_items_from', verbose_name="مکان مبدأ")
    target_location = models.ForeignKey(StockLocation, on_delete=models.PROTECT, related_name='request_items_to', verbose_name="مکان مقصد")
    requested_quantity = models.DecimalField(max_digits=12, decimal_places=3, verbose_name="مقدار درخواستی")
    approved_quantity = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True, verbose_name="مقدار تایید شده")
    issued_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0, verbose_name="مقدار صادر شده")
    notes = models.CharField(max_length=255, blank=True, verbose_name="یادداشت")
    material_requirement = models.ForeignKey(MaterialRequirement, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="نیاز مرتبط")

    class Meta:
        verbose_name = "آیتم درخواست مواد"
        verbose_name_plural = "آیتم‌های درخواست مواد"
        ordering = ['material_request', 'id']

    def __str__(self):
        return f"{self.material_request.request_number} - {self.item.code}"


class MaterialIssue(models.Model):
    ISSUE_STATUS = [
        ('draft', 'پیش‌نویس'),
        ('issued', 'صادر شده'),
        ('cancelled', 'لغو شده'),
    ]

    issue_number = models.CharField(max_length=50, unique=True, verbose_name="شماره صدور")
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='material_issues', verbose_name="صادرکننده")
    issued_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان صدور")
    status = models.CharField(max_length=20, choices=ISSUE_STATUS, default='draft', verbose_name="وضعیت")
    notes = models.TextField(blank=True, verbose_name="یادداشت‌ها")
    customer_order = models.ForeignKey(CustomerOrder, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="سفارش مرتبط")

    class Meta:
        verbose_name = "صدور مواد"
        verbose_name_plural = "صدورهای مواد"
        ordering = ['-issued_at']

    def __str__(self):
        return f"MI-{self.issue_number}"


class MaterialIssueItem(models.Model):
    material_issue = models.ForeignKey(MaterialIssue, on_delete=models.CASCADE, related_name='items', verbose_name="صدور مواد")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, verbose_name="کالا")
    source_location = models.ForeignKey(StockLocation, on_delete=models.PROTECT, related_name='issue_items_from', verbose_name="مکان مبدأ")
    target_location = models.ForeignKey(StockLocation, on_delete=models.PROTECT, related_name='issue_items_to', verbose_name="مکان مقصد")
    quantity = models.DecimalField(max_digits=12, decimal_places=3, verbose_name="مقدار")
    lot = models.ForeignKey('inventory.StockLot', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="لات")
    notes = models.CharField(max_length=255, blank=True, verbose_name="یادداشت")
    material_request_item = models.ForeignKey(MaterialRequestItem, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="آیتم درخواست مرتبط")

    class Meta:
        verbose_name = "آیتم صدور مواد"
        verbose_name_plural = "آیتم‌های صدور مواد"
        ordering = ['material_issue', 'id']

    def __str__(self):
        return f"{self.material_issue.issue_number} - {self.item.code}"


class MaterialConsumption(models.Model):
    material_issue_item = models.ForeignKey(MaterialIssueItem, on_delete=models.CASCADE, related_name='consumptions', verbose_name="آیتم صدور")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, verbose_name="کالا")
    quantity = models.DecimalField(max_digits=12, decimal_places=3, verbose_name="مقدار مصرف")
    consumption_date = models.DateTimeField(verbose_name="تاریخ مصرف")
    consumed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name="مصرف‌کننده")
    production_order = models.ForeignKey('production.ProductionOrder', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="سفارش تولید")
    production_operation = models.ForeignKey('production.ProductionOperation', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="عملیات تولید")
    notes = models.TextField(blank=True, verbose_name="یادداشت")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ثبت")

    class Meta:
        verbose_name = "مصرف مواد"
        verbose_name_plural = "مصرف مواد"
        ordering = ['-consumption_date']

    def __str__(self):
        return f"مصرف {self.item.code} - {self.quantity}"


class MaterialReturn(models.Model):
    RETURN_STATUS = [
        ('draft', 'پیش‌نویس'),
        ('returned', 'مرجوع شده'),
        ('cancelled', 'لغو شده'),
    ]

    return_number = models.CharField(max_length=50, unique=True, verbose_name="شماره مرجوعی")
    returned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='material_returns', verbose_name="مرجوع‌کننده")
    returned_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان مرجوعی")
    status = models.CharField(max_length=20, choices=RETURN_STATUS, default='draft', verbose_name="وضعیت")
    notes = models.TextField(blank=True, verbose_name="یادداشت‌ها")
    customer_order = models.ForeignKey(CustomerOrder, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="سفارش مرتبط")

    class Meta:
        verbose_name = "مرجوعی مواد"
        verbose_name_plural = "مرجوعی‌های مواد"
        ordering = ['-returned_at']

    def __str__(self):
        return f"MR-{self.return_number}"


class MaterialReturnItem(models.Model):
    material_return = models.ForeignKey(MaterialReturn, on_delete=models.CASCADE, related_name='items', verbose_name="مرجوعی")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, verbose_name="کالا")
    source_location = models.ForeignKey(StockLocation, on_delete=models.PROTECT, related_name='return_items_from', verbose_name="مکان مبدأ")
    target_location = models.ForeignKey(StockLocation, on_delete=models.PROTECT, related_name='return_items_to', verbose_name="مکان مقصد")
    quantity = models.DecimalField(max_digits=12, decimal_places=3, verbose_name="مقدار")
    lot = models.ForeignKey('inventory.StockLot', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="لات")
    reason = models.CharField(max_length=255, blank=True, verbose_name="دلیل مرجوعی")
    notes = models.CharField(max_length=255, blank=True, verbose_name="یادداشت")
    material_issue_item = models.ForeignKey(MaterialIssueItem, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="آیتم صدور مرتبط")

    class Meta:
        verbose_name = "آیتم مرجوعی"
        verbose_name_plural = "آیتم‌های مرجوعی"
        ordering = ['material_return', 'id']

    def __str__(self):
        return f"{self.material_return.return_number} - {self.item.code}"


class MaterialWaste(models.Model):
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='wastes', verbose_name="کالا")
    location = models.ForeignKey(StockLocation, on_delete=models.PROTECT, verbose_name="مکان")
    quantity = models.DecimalField(max_digits=12, decimal_places=3, verbose_name="مقدار ضایعات")
    waste_date = models.DateTimeField(verbose_name="تاریخ ضایعات")
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name="ثبت‌کننده")
    reason = models.CharField(max_length=255, verbose_name="دلیل ضایعات")
    disposal_method = models.CharField(max_length=100, blank=True, verbose_name="روش دفع")
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="هزینه ضایعات")
    notes = models.TextField(blank=True, verbose_name="یادداشت")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ثبت")

    class Meta:
        verbose_name = "ضایعات مواد"
        verbose_name_plural = "ضایعات مواد"
        ordering = ['-waste_date']

    def __str__(self):
        return f"ضایعات {self.item.code} - {self.quantity}"
