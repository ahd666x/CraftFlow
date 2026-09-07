from django.db import models
from django.contrib.auth.models import User
from django.db.models import Sum, Case, When, Value, DecimalField, F


class Supplier(models.Model):
    name = models.CharField(max_length=150, verbose_name="نام تامین‌کننده")
    phone = models.CharField(max_length=20, blank=True, verbose_name="تلفن")
    address = models.TextField(blank=True, verbose_name="آدرس")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ثبت")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "تامین‌کننده"
        verbose_name_plural = "تامین‌کنندگان"
        ordering = ['name']


class RawMaterialCategory(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="نام دسته")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "دسته مواد اولیه"
        verbose_name_plural = "دسته‌های مواد اولیه"
        ordering = ['name']


class RawMaterial(models.Model):
    UNIT_CHOICES = [
        ('kg', 'کیلوگرم'),
        ('lit', 'لیتر'),
        ('pcs', 'عدد'),
        ('m', 'متر'),
    ]

    category = models.ForeignKey(RawMaterialCategory, on_delete=models.PROTECT, related_name='materials', verbose_name="دسته")
    name = models.CharField(max_length=150, verbose_name="نام ماده اولیه")
    code = models.CharField(max_length=50, blank=True, verbose_name="کد")
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, verbose_name="واحد")
    min_stock_alert = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="حداقل موجودی هشدار")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ثبت")

    @property
    def current_stock(self):
        agg = self.movements.aggregate(
            total=Sum(
                Case(
                    When(movement_type='consumption', then=-F('quantity')),
                    default=F('quantity'),
                    output_field=DecimalField()
                )
            )
        )
        return agg['total'] or 0

    @property
    def stock_status(self):
        stock = self.current_stock
        if stock <= 0:
            return 'danger'
        elif stock <= self.min_stock_alert:
            return 'warning'
        return 'success'

    def __str__(self):
        return f"{self.name} ({self.get_unit_display()})"

    class Meta:
        verbose_name = "ماده اولیه"
        verbose_name_plural = "مواد اولیه"
        ordering = ['category', 'name']
        unique_together = ['category', 'name']


class StockMovement(models.Model):
    MOVEMENT_TYPES = [
        ('purchase', 'خرید/ورود'),
        ('consumption', 'مصرف'),
        ('adjustment', 'اصلاحیه'),
        ('return', 'مرجوعی'),
    ]

    raw_material = models.ForeignKey(RawMaterial, on_delete=models.PROTECT, related_name='movements', verbose_name="ماده اولیه")
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES, verbose_name="نوع حرکت")
    quantity = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="مقدار")
    unit_price = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True, verbose_name="قیمت واحد (ریال)")
    supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="تامین‌کننده")
    reference_task = models.ForeignKey('product.ProductionTask', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="وظیفه تولید مرتبط")
    note = models.CharField(max_length=255, blank=True, verbose_name="یادداشت")
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, verbose_name="ثبت‌کننده")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ثبت")

    def __str__(self):
        return f"{self.get_movement_type_display()} - {self.raw_material.name} ({self.quantity})"

    class Meta:
        verbose_name = "حرکت انبار"
        verbose_name_plural = "حرکات انبار"
        ordering = ['-created_at']


class PurchaseOrder(models.Model):
    STATUS_CHOICES = [
        ('draft', 'پیش‌نویس'),
        ('ordered', 'سفارش‌شده'),
        ('received', 'دریافت‌شده'),
    ]

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, verbose_name="تامین‌کننده")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name="وضعیت")
    note = models.TextField(blank=True, verbose_name="یادداشت")
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, verbose_name="ثبت‌کننده")

    def __str__(self):
        return f"PO-{self.id}: {self.supplier.name} ({self.get_status_display()})"

    class Meta:
        verbose_name = "سفارش خرید"
        verbose_name_plural = "سفارشات خرید"
        ordering = ['-created_at']


class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items', verbose_name="سفارش خرید")
    raw_material = models.ForeignKey(RawMaterial, on_delete=models.PROTECT, verbose_name="ماده اولیه")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="مقدار")
    unit_price = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="قیمت واحد (ریال)")
    received_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="مقدار دریافت‌شده")

    @property
    def line_total(self):
        return self.quantity * self.unit_price

    def __str__(self):
        return f"{self.raw_material.name} x {self.quantity}"

    class Meta:
        verbose_name = "آیتم سفارش خرید"
        verbose_name_plural = "آیتم‌های سفارش خرید"
        ordering = ['purchase_order', 'id']


# ===================== V2 Inventory Models =====================

class UOM(models.Model):
    UOM_TYPES = [
        ('weight', 'وزن'),
        ('volume', 'حجم'),
        ('length', 'طول'),
        ('area', 'مساحت'),
        ('count', 'تعداد'),
        ('time', 'زمان'),
    ]

    code = models.CharField(max_length=20, unique=True, verbose_name="کد")
    name = models.CharField(max_length=50, verbose_name="نام")
    uom_type = models.CharField(max_length=20, choices=UOM_TYPES, verbose_name="نوع")
    decimal_places = models.PositiveSmallIntegerField(default=2, verbose_name="تعداد اعشار")
    is_base = models.BooleanField(default=False, verbose_name="واحد پایه")
    description = models.CharField(max_length=255, blank=True, verbose_name="توضیحات")

    class Meta:
        verbose_name = "واحد اندازه‌گیری"
        verbose_name_plural = "واحدهای اندازه‌گیری"
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class UOMConversion(models.Model):
    from_uom = models.ForeignKey(UOM, on_delete=models.CASCADE, related_name='conversions_from', verbose_name="از واحد")
    to_uom = models.ForeignKey(UOM, on_delete=models.CASCADE, related_name='conversions_to', verbose_name="به واحد")
    factor = models.DecimalField(max_digits=12, decimal_places=6, verbose_name="ضریب تبدیل")
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    class Meta:
        verbose_name = "تبدیل واحد"
        verbose_name_plural = "تبدیلات واحد"
        unique_together = ['from_uom', 'to_uom']
        ordering = ['from_uom', 'to_uom']

    def __str__(self):
        return f"1 {self.from_uom.code} = {self.factor} {self.to_uom.code}"


class ItemCategory(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="نام دسته")
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='children', verbose_name="دسته والد")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    class Meta:
        verbose_name = "دسته کالا"
        verbose_name_plural = "دسته‌های کالا"
        ordering = ['name']

    def __str__(self):
        return self.name


class Item(models.Model):
    ITEM_TYPES = [
        ('material', 'ماده اولیه'),
        ('component', 'قطعه'),
        ('packaging', 'بسته‌بندی'),
        ('consumable', 'مصرفی'),
        ('finished', 'کالای آماده'),
    ]

    category = models.ForeignKey(ItemCategory, on_delete=models.PROTECT, related_name='items', verbose_name="دسته")
    code = models.CharField(max_length=50, unique=True, verbose_name="کد کالا")
    name = models.CharField(max_length=200, verbose_name="نام کالا")
    item_type = models.CharField(max_length=20, choices=ITEM_TYPES, default='material', verbose_name="نوع کالا")
    uom = models.ForeignKey(UOM, on_delete=models.PROTECT, verbose_name="واحد اندازه‌گیری")
    barcode = models.CharField(max_length=100, unique=True, blank=True, verbose_name="بارکد")
    qr_code_data = models.CharField(max_length=255, blank=True, verbose_name="داده QR")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    min_stock = models.DecimalField(max_digits=12, decimal_places=3, default=0, verbose_name="حداقل موجودی")
    max_stock = models.DecimalField(max_digits=12, decimal_places=3, default=0, verbose_name="حداکثر موجودی")
    reorder_point = models.DecimalField(max_digits=12, decimal_places=3, default=0, verbose_name="نقطه سفارش مجدد")
    lead_time_days = models.PositiveIntegerField(default=0, verbose_name="زمان تحویل (روز)")
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="هزینه واحد")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    is_serialized = models.BooleanField(default=False, verbose_name="شماره سریال دارد")
    requires_lot_tracking = models.BooleanField(default=False, verbose_name="ردیابی لات نیاز است")
    shelf_life_days = models.PositiveIntegerField(null=True, blank=True, verbose_name="طول عمر قفسه (روز)")
    weight_kg = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True, verbose_name="وزن (کیلوگرم)")
    volume_m3 = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True, verbose_name="حجم (متر مکعب)")
    image = models.ImageField(upload_to='items/', blank=True, null=True, verbose_name="تصویر")

    class Meta:
        verbose_name = "کالا (Item)"
        verbose_name_plural = "کالاها (Items)"
        ordering = ['code', 'name']

    def __str__(self):
        return f"{self.code} - {self.name}"


class ItemSupplier(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='suppliers', verbose_name="کالا")
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, verbose_name="تامین‌کننده")
    supplier_item_code = models.CharField(max_length=100, blank=True, verbose_name="کد کالا نزد تامین‌کننده")
    lead_time_days = models.PositiveIntegerField(default=0, verbose_name="زمان تحویل (روز)")
    min_order_qty = models.DecimalField(max_digits=12, decimal_places=3, default=0, verbose_name="حداقل مقدار سفارش")
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="قیمت واحد")
    is_preferred = models.BooleanField(default=False, verbose_name="ترجیحی")
    notes = models.TextField(blank=True, verbose_name="یادداشت")

    class Meta:
        verbose_name = "تامین‌کننده کالا"
        verbose_name_plural = "تامین‌کنندگان کالا"
        unique_together = ['item', 'supplier']
        ordering = ['item', '-is_preferred']

    def __str__(self):
        return f"{self.item.code} - {self.supplier.name}"


class StockLocation(models.Model):
    LOCATION_TYPES = [
        ('warehouse', 'انبار اصلی'),
        ('wip', 'در حال تولید'),
        ('paint', 'نقاشی'),
        ('qc', 'کنترل کیفیت'),
        ('shipping', 'ارسال'),
        ('quarantine', 'قرنطینه'),
    ]

    code = models.CharField(max_length=50, unique=True, verbose_name="کد مکان")
    name = models.CharField(max_length=100, verbose_name="نام مکان")
    location_type = models.CharField(max_length=20, choices=LOCATION_TYPES, default='warehouse', verbose_name="نوع مکان")
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='children', verbose_name="مکان والد")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    capacity = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True, verbose_name="ظرفیت")
    manager = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="مدیر")

    class Meta:
        verbose_name = "مکان انبار"
        verbose_name_plural = "مکان‌های انبار"
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class StockLot(models.Model):
    LOT_STATUS = [
        ('available', 'موجود'),
        ('reserved', 'رزرو شده'),
        ('quarantine', 'قرنطینه'),
        ('expired', 'منقضی'),
        ('damaged', 'خراب'),
    ]

    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='lots', verbose_name="کالا")
    location = models.ForeignKey(StockLocation, on_delete=models.PROTECT, related_name='lots', verbose_name="مکان")
    lot_number = models.CharField(max_length=100, verbose_name="شماره لات")
    batch_number = models.CharField(max_length=100, blank=True, verbose_name="شماره بچ")
    quantity = models.DecimalField(max_digits=12, decimal_places=3, verbose_name="مقدار")
    status = models.CharField(max_length=20, choices=LOT_STATUS, default='available', verbose_name="وضعیت")
    manufactured_date = models.DateField(null=True, blank=True, verbose_name="تاریخ تولید")
    expiry_date = models.DateField(null=True, blank=True, verbose_name="تاریخ انقضا")
    received_date = models.DateField(verbose_name="تاریخ دریافت")
    received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="دریافت‌کننده")
    notes = models.TextField(blank=True, verbose_name="یادداشت")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    class Meta:
        verbose_name = "لات انبار"
        verbose_name_plural = "لات‌های انبار"
        ordering = ['-received_date', 'lot_number']
        unique_together = ['item', 'location', 'lot_number']

    def __str__(self):
        return f"{self.item.code} - {self.lot_number} @ {self.location.code}"


class StockBalance(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='stock_balances', verbose_name="کالا")
    location = models.ForeignKey(StockLocation, on_delete=models.CASCADE, related_name='stock_balances', verbose_name="مکان")
    quantity_on_hand = models.DecimalField(max_digits=12, decimal_places=3, default=0, verbose_name="موجود فیزیکی")
    quantity_reserved = models.DecimalField(max_digits=12, decimal_places=3, default=0, verbose_name="رزرو شده")
    quantity_available = models.DecimalField(max_digits=12, decimal_places=3, default=0, verbose_name="موجود قابل استفاده")
    last_counted = models.DateTimeField(null=True, blank=True, verbose_name="آخرین شمارش")
    last_movement = models.DateTimeField(null=True, blank=True, verbose_name="آخرین حرکت")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="به‌روزرسانی")

    class Meta:
        verbose_name = "موجودی"
        verbose_name_plural = "موجودی‌ها"
        ordering = ['item', 'location']
        unique_together = ['item', 'location']

    def __str__(self):
        return f"{self.item.code} @ {self.location.code}: {self.quantity_on_hand}"


class StockLedger(models.Model):
    LEDGER_TYPES = [
        ('receipt', 'رسید'),
        ('issue', 'رسیدگی'),
        ('transfer', 'انتقال'),
        ('adjustment', 'اصلاحیه'),
        ('return', 'مرجوعی'),
        ('consumption', 'مصرف'),
        ('waste', 'ضایعات'),
        ('production', 'تولید'),
    ]

    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='ledger_entries', verbose_name="کالا")
    location = models.ForeignKey(StockLocation, on_delete=models.PROTECT, related_name='ledger_entries', verbose_name="مکان")
    lot = models.ForeignKey(StockLot, null=True, blank=True, on_delete=models.SET_NULL, related_name='ledger_entries', verbose_name="لات")
    ledger_type = models.CharField(max_length=20, choices=LEDGER_TYPES, verbose_name="نوع")
    quantity = models.DecimalField(max_digits=12, decimal_places=3, verbose_name="مقدار")
    balance_after = models.DecimalField(max_digits=12, decimal_places=3, verbose_name="موجودی بعد")
    reference_document = models.CharField(max_length=100, blank=True, verbose_name="سند مرجع")
    reference_id = models.CharField(max_length=50, blank=True, verbose_name="شناسه مرجع")
    notes = models.TextField(blank=True, verbose_name="یادداشت")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="ثبت‌کننده")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ثبت")
    is_balanced = models.BooleanField(default=True, verbose_name="موازنه شده")

    class Meta:
        verbose_name = "دفتر روزنامه انبار"
        verbose_name_plural = "دفتر روزنامه انبار"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['item', 'location', 'created_at']),
            models.Index(fields=['reference_document', 'reference_id']),
        ]

    def __str__(self):
        return f"{self.item.code} - {self.get_ledger_type_display()} ({self.quantity})"


class StockReservation(models.Model):
    RESERVATION_STATUS = [
        ('active', 'فعال'),
        ('fulfilled', 'برآورده شده'),
        ('cancelled', 'لغو شده'),
        ('expired', 'منقضی شده'),
    ]

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='reservations', verbose_name="کالا")
    location = models.ForeignKey(StockLocation, on_delete=models.CASCADE, related_name='reservations', verbose_name="مکان")
    quantity = models.DecimalField(max_digits=12, decimal_places=3, verbose_name="مقدار رزرو")
    reserved_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان رزرو")
    reserved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="رزروکننده")
    status = models.CharField(max_length=20, choices=RESERVATION_STATUS, default='active', verbose_name="وضعیت")
    reference_document = models.CharField(max_length=100, verbose_name="سند مرجع")
    reference_id = models.CharField(max_length=50, verbose_name="شناسه مرجع")
    fulfilled_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان برآورده شدن")
    notes = models.TextField(blank=True, verbose_name="یادداشت")
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name="انقضای رزرو")

    class Meta:
        verbose_name = "رزرو موجودی"
        verbose_name_plural = "رزروهای موجودی"
        ordering = ['-reserved_at']
        indexes = [
            models.Index(fields=['item', 'status']),
            models.Index(fields=['reference_document', 'reference_id']),
        ]

    def __str__(self):
        return f"{self.item.code} - {self.quantity} ({self.get_status_display()})"
