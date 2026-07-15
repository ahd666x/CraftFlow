from django.db import models, transaction
from django.contrib.auth.models import User
from django.urls import reverse
import jdatetime
from .fields import PersianDateField
from io import BytesIO
from django.core.files.base import ContentFile
from django.conf import settings
from django.urls import reverse
import qrcode
from decimal import Decimal



class Customer(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customers',
        verbose_name="نماینده"
    )
    name = models.CharField(max_length=100, verbose_name="نام مشتری")
    phone = models.CharField(max_length=20, blank=True, verbose_name="تلفن")
    address = models.TextField(blank=True, verbose_name="آدرس")

    def __str__(self):
        return f"{self.name}"

    class Meta:
        verbose_name = "مشتری"
        verbose_name_plural = "مشتریان"


class ProductCategory(models.Model):
    name = models.CharField(max_length=100, verbose_name="نام دسته")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "دسته بندی"
        verbose_name_plural = "دسته بندی‌ها"


class Material(models.Model):
    name = models.CharField(max_length=100, verbose_name="نام ورق")
    thickness = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        verbose_name="ضخامت (میلی‌متر)",
        help_text="مثال: 16.0"
    )

    def __str__(self):
        return f"{self.name} ({self.thickness}mm)"

    class Meta:
        verbose_name = "متریال"
        verbose_name_plural = "متریال‌ها"



class Order(models.Model):
    ORDER_STATUS = (
        ('draft', 'پیش‌نویس'),
        ('planned', 'برنامه‌ریزی شده'),
        ('producing', 'در حال تولید'),
        ('completed', 'تکمیل شده'),
    )

    user = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, verbose_name="نماینده")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, verbose_name="مشتری")
    number = models.CharField(max_length=10, blank=True, verbose_name="شماره سفارش")
    created_at = PersianDateField(default=jdatetime.date.today, verbose_name="تاریخ سفارش")
    status = models.CharField(
        max_length=20,
        choices=ORDER_STATUS,
        default='draft',
        verbose_name="وضعیت سفارش"
    )

    def __str__(self):
        return f"سفارش {self.id} - {self.customer}"

    class Meta:
        verbose_name = "سفارش"
        verbose_name_plural = "سفارش‌ها"
    @property
    def total_price(self):
        return sum(item.line_total for item in self.items.all())
    

    @property
    def packaging_summary(self):
        total_units = 0
        packed_units = 0
        shipped_units = 0
        for item in self.items.all():
            item_total = item.packaging_units.count()
            total_units += item_total
            packed_units += item.packaging_units.filter(is_packed=True).count()
            shipped_units += item.packaging_units.filter(is_shipped=True).count()
        return {
            'total': total_units,
            'packed': packed_units,
            'shipped': shipped_units,
        }



    def generate_tasks(self):
        from .utils import get_material_for_color, parse_size_string, apply_size_adjustment, update_barcode_size

        if self.tasks.exists():
            return False

        tasks_to_create = []
        with transaction.atomic():
            for item in self.items.all():
                item_colors = {c.part: c.code for c in item.ordercolor.all()}
                print(item_colors)
                order_item_id = item.id   # شناسه آیتم سفارش

                product_default_size = parse_size_string(item.product.default_size or "")
                ordered_size = parse_size_string(item.size or "")
                size_diff = {}
                if product_default_size.get('length') and ordered_size.get('length'):
                    diff_cm = ordered_size['length'] - product_default_size['length']
                    size_diff['length_diff'] = diff_cm * 10
                if product_default_size.get('width') and ordered_size.get('width'):
                    diff_cm = ordered_size['width'] - product_default_size['width']
                    size_diff['width_diff'] = diff_cm * 10

                for bom_entry in item.product.bom.all():
                    part = bom_entry.part
                    total_qty = bom_entry.quantity * item.quantity

                    # تعیین متریال
                    material = part.material
                    if bom_entry.allow_material_override and bom_entry.color_part:
                        color_code = item_colors.get(bom_entry.color_part)
                        if color_code:
                            print(bom_entry.color_material_map)
                            new_material = get_material_for_color(color_code, bom_entry.color_material_map)
                            if new_material:
                                material = new_material

                    # تعیین ابعاد
                    length = part.length
                    width = part.width
                    if bom_entry.size_affected and bom_entry.size_adjustment_rule and size_diff:
                        length, width = apply_size_adjustment(
                            part.length, part.width, size_diff, bom_entry.size_adjustment_rule
                        )

                    # تولید بارکد جدید با شناسه آیتم
                    new_f3 = update_barcode_size(part.f3, length, width, order_item_id)

                    # ایجاد قطعه داینامیک
                    dynamic_part, created = Part.objects.get_or_create(
                        base_part=part,
                        material=material,
                        length=length,
                        width=width,
                        defaults={
                            'name': part.name,
                            'grain': part.grain,
                            'pname' : part.pname,
                            'turn':part.turn,
                            'f26': part.f26,
                            'f18': part.f18,
                            'f4': part.f4,
                            'f5': part.f5,
                            'f3': new_f3,
                            'f2': part.f2,
                            'routing_code': part.routing_code,
                        }
                    )

                    # اگر قطعه از قبل وجود داشت ولی بارکد قدیمی بود، آن را به‌روز کنیم
                    if not created and dynamic_part.f3 != new_f3:
                        dynamic_part.f3 = new_f3
                        dynamic_part.save(update_fields=['f3'])

                    # ایجاد تسک‌ها
                    stations = [s.strip() for s in dynamic_part.routing_code.split('.') if s.strip()]
                    stations.insert(0, "cut")
                    for idx, station_name in enumerate(stations):
                        tasks_to_create.append(
                            ProductionTask(
                                order=self,
                                part=dynamic_part,
                                station_name=station_name.lower(),
                                step_order=idx + 1,
                                quantity=total_qty,
                                status='pending' if idx == 0 else 'waiting'
                            )
                        )

            if tasks_to_create:
                ProductionTask.objects.bulk_create(tasks_to_create)
                self.status = 'planned'
                self.save()
                return True
        return False



class Product(models.Model):
    category = models.ForeignKey(ProductCategory,on_delete=models.PROTECT,related_name='products',verbose_name="دسته")
    name = models.CharField(max_length=200, verbose_name="نام محصول")
    color = models.CharField(max_length=100, blank=True, verbose_name="رنگ")
    parts_list_key = models.CharField(max_length=255, blank=True, verbose_name="مسیر فایل")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    default_size = models.CharField(max_length=100, blank=True, verbose_name="سایز پیش‌فرض")
    default_colors = models.JSONField(default=dict,blank=True,verbose_name="رنگ‌های پیش‌فرض")   ####default="{}"
    base_price = models.DecimalField(max_digits=12, decimal_places=0, default=0,verbose_name="قیمت")
    price_increment_per_cm = models.DecimalField(max_digits=5,decimal_places=2,default=0,verbose_name="درصد افزایش قیمت به ازای هر سانتی‌متر",)


    def __str__(self):
        return f"{self.category} - {self.name}"

    class Meta:
        verbose_name = "محصول"
        verbose_name_plural = "محصولات"



class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items', verbose_name="سفارش")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name="محصول")
    notes = models.CharField(max_length=200, blank=True, verbose_name="توضیحات")
    quantity = models.PositiveIntegerField(default=1, verbose_name="تعداد")
    size = models.CharField(max_length=100, blank=True, verbose_name="اندازه")
    qr_code = models.ImageField(upload_to='qr/', blank=True, null=True)
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=0, default=0,verbose_name="قیمت")
    class Meta:
        verbose_name = "لیست سفارش"
        verbose_name_plural = "لیست سفارش‌ها"

    def get_absolute_url(self):
        return reverse('scan_qr', args=[self.id])

    def __str__(self):
        return f"{self.product.name} (سفارش {self.order.id})"

    @property
    def color_summary(self):
        colors = self.ordercolor.all()
        parts = []
        for c in colors:
            if c.code and c.code != 'nan':
                parts.append(f"{c.part}:{c.code}")
        return "-".join(parts) if parts else "بدون رنگ"

    @property
    def packaging_progress(self):
        total = self.packaging_units.count()
        packed = self.packaging_units.filter(is_packed=True).count()
        return packed, total

    @property
    def shipping_progress(self):
        total = self.packaging_units.count()
        shipped = self.packaging_units.filter(is_shipped=True).count()
        return shipped, total

    @property
    def is_fully_packed(self):
        packed, total = self.packaging_progress
        return total > 0 and packed == total

    @property
    def is_fully_shipped(self):
        shipped, total = self.shipping_progress
        return total > 0 and shipped == total
    
    @property
    def line_total(self):
        return self.unit_price * self.quantity


    def sync_packaging_units(self):
        """تعداد واحدهای بسته‌بندی را با مقدار quantity هماهنگ می‌کند."""
        current_count = self.packaging_units.count()
        target_count = self.quantity

        if target_count > current_count:
            # ایجاد واحدهای جدید
            base_url = getattr(settings, 'SCAN_BASE_URL', 'http://192.168.1.123:8000')
            for i in range(current_count + 1, target_count + 1):
                unit = PackagingUnit.objects.create(
                    order_item=self,
                    unit_number=i
                )
                # تولید QR برای واحد جدید
                scan_url = reverse('scan_packaging_unit', args=[unit.id])
                full_url = f"{base_url.rstrip('/')}{scan_url}?next={reverse('item_detail', args=[self.id])}"
                qr = qrcode.make(full_url, box_size=10, border=4)
                buffer = BytesIO()
                qr.save(buffer, format='PNG')
                filename = f"pack_qr_order_{self.order.id}_item_{self.id}_unit_{i}.png"
                unit.qr_code.save(filename, ContentFile(buffer.getvalue()), save=True)

        elif target_count < current_count:
            # حذف واحدهای اضافی (آخرین‌ها)
            extra_units = self.packaging_units.order_by('-unit_number')[:current_count - target_count]
            extra_units.delete()



    def calculate_price(self):
        """محاسبه قیمت بر اساس طول سفارش"""
        if not self.product:
            return 0
            
        order_size_str = self.size or self.product.default_size
        default_size_str = self.product.default_size
        
        if not order_size_str or not default_size_str:
            return int(self.product.base_price or 0)
            
        import re
        order_numbers = re.findall(r'\d+', order_size_str)
        default_numbers = re.findall(r'\d+', default_size_str)
        
        if not order_numbers or not default_numbers:
            return int(self.product.base_price or 0)
            
        order_length = int(order_numbers[0])
        default_length = int(default_numbers[0])
        
        if default_length == 0:
            return int(self.product.base_price or 0)
            
        base_price_int = int(self.product.base_price or 0)
        increment_percent_float = float(self.product.price_increment_per_cm or 0)
        
        # diff_percent = ((order_length - default_length) / default_length) * 100
        # price_increase = (base_price_int * diff_percent * increment_percent_float) / 100
        # final_price = base_price_int + price_increase

        diff_percent = ((order_length - default_length) * increment_percent_float )/100
        price_increase = (base_price_int * diff_percent ) 
        final_price = base_price_int + price_increase
        
        if final_price < 0:
            return 0
        return int(round(final_price))
    
    def save(self, *args, **kwargs):
        """ذخیره آیتم با محاسبه خودکار قیمت"""
        # محاسبه قیمت قبل از ذخیره
        if self.product:
            try:
                self.unit_price = self.calculate_price()
            except Exception as e:
                # اگر خطایی رخ داد، از قیمت پایه استفاده کن
                if self.product and self.product.base_price is not None:
                    self.unit_price = int(self.product.base_price)
                else:
                    self.unit_price = 0
        
        super().save(*args, **kwargs)
        







class Color(models.Model):
    PART_CHOICES = [
        ('بدنه', 'بدنه'),
        ('درب', 'درب'),
        ('دستگیره', 'دستگیره'),
        ('پایه', 'پایه'),
        ('صفحه', 'صفحه'),
        ('رینگ', 'رینگ'),
    ]
    CODE_CHOICES = [(str(i), str(i)) for i in range(1, 11)]
    CODE_CHOICES.append(('جناغی' , 'جناغی'))
    CODE_CHOICES.append(('بتنی' , 'بتنی'))

    part = models.CharField(max_length=20, choices=PART_CHOICES, verbose_name="قطعه")
    code = models.CharField(max_length=20, choices=CODE_CHOICES, verbose_name="کد رنگ")
    orderitem = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name='ordercolor', verbose_name="آیتم سفارش")

    def __str__(self):
        return f"{self.part}:{self.code}"

    class Meta:
        verbose_name = "رنگ"
        verbose_name_plural = "رنگ‌ها"




class Part(models.Model):
    material = models.ForeignKey(
        Material,
        on_delete=models.PROTECT,
        related_name='parts',
        verbose_name="نوع ورق"
    )
    name = models.CharField(max_length=100, verbose_name="نام قطعه")
    length = models.DecimalField(max_digits=7, decimal_places=1, verbose_name="طول (X)")
    width = models.DecimalField(max_digits=7, decimal_places=1, verbose_name="عرض (Y)")
    grain = models.CharField(max_length=100, blank=True , verbose_name="دسته")
    pname = models.CharField(max_length=100, verbose_name="نام محصول")
    turn = models.BooleanField(default=False, blank=True , verbose_name="turn")

    # نوار لبه
    f26 = models.CharField(max_length=100, blank=True, verbose_name="نوار لبه F26")
    f18 = models.CharField(max_length=100, blank=True, verbose_name="نوار لبه F18")
    f4 = models.CharField(max_length=100, blank=True, verbose_name="نوار لبه F4")
    f5 = models.CharField(max_length=100, blank=True, verbose_name="نوار لبه F5")

    # بارکد و نام فنی
    f3 = models.CharField(max_length=100, blank=True, verbose_name="بارکد F3")
    f2 = models.CharField(max_length=100, blank=True, verbose_name="نام قطعه F2")

    # مسیر تولید
    routing_code = models.CharField(max_length=255, verbose_name="تحویل به مرحله")

    # فیلدهای تغییر اندازه
    base_part = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='variations',
        verbose_name="قطعه پایه"
    )

    class Meta:
        verbose_name = "قطعه"
        verbose_name_plural = "قطعات"

    def __str__(self):
        return f"{self.f2 or self.name} ({self.length}x{self.width})"


class ProductBOM(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='bom')
    part = models.ForeignKey(Part, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1, verbose_name="تعداد در هر محصول")

    # نقش رنگی قطعه
    color_part = models.CharField(
        max_length=20,
        choices=Color.PART_CHOICES,
        blank=True,
        null=True,
        verbose_name="بخش رنگی"
    )

    # تغییر متریال با رنگ
    allow_material_override = models.BooleanField(default=False, verbose_name="امکان تغییر متریال با رنگ")
    color_material_map = models.JSONField(default=dict, blank=True, verbose_name="نگاشت رنگ به متریال")

    # تغییر اندازه
    size_affected = models.BooleanField(default=False, verbose_name="تحت تأثیر اندازه")
    size_adjustment_rule = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="قانون تغییر اندازه",
        help_text="مثال: length+length_diff, width/3"
    )

    def __str__(self):
        return f"{self.product.name}: {self.quantity}x {self.part.name}"

    class Meta:
        verbose_name = "فرمول ساخت"
        verbose_name_plural = "فرمول‌های ساخت"


STATION_CHOICES = [
    ('cut', 'برش'),
    ('cnc', 'CNC'),
    ('dr', 'سوراخکاری'),
    ('pvc', 'نوارکاری'),       # ← نوارکاری با نام اختصاری pvc
    ('prs', 'پرس'),             # ← پرس با نام اختصاری prs
    # ('assembly1', 'مونتاژ اول'),
    ('mon', 'مونتاژ اول'),
    ('vacum', 'وکیوم'),

    ('paint', 'نقاشی'),
    ('assembly2', 'مونتاژ نهایی'),
    ('packaging', 'بسته‌بندی'),
    ('shipping', 'ارسال شده'),
]


class ProductionTask(models.Model):
    STATION_CHOICES = STATION_CHOICES
    TASK_STATUS = (
        ('waiting', 'در انتظار مرحله قبل'),
        ('pending', 'آماده انجام'),
        ('done', 'تکمیل شده'),
    )

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='tasks', verbose_name="سفارش")
    part = models.ForeignKey(Part, on_delete=models.PROTECT, verbose_name="قطعه")
    station_name = models.CharField(max_length=50, choices=STATION_CHOICES, verbose_name="ایستگاه کاری")
    step_order = models.PositiveIntegerField(verbose_name="اولویت مرحله")
    quantity = models.PositiveIntegerField(verbose_name="تعداد قطعه")
    status = models.CharField(max_length=20, choices=TASK_STATUS, default='waiting', verbose_name="وضعیت تسک")
    scanned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="انجام‌دهنده")
    completed_at = PersianDateField(null=True, blank=True, verbose_name="زمان تکمیل")

    class Meta:
        verbose_name = "وظیفه تولید"
        verbose_name_plural = "وظایف تولید"
        ordering = ['order', 'part', 'step_order']

    def __str__(self):
        return f"{self.get_station_name_display()} | {self.part} (سفارش {self.order.id})"

    def save(self, *args, **kwargs):
        old_status = None
        if self.pk:
            old_status = ProductionTask.objects.filter(pk=self.pk).values_list('status', flat=True).first()

        if self.status == 'done' and old_status != 'done':
            if not self.completed_at:
                self.completed_at = jdatetime.date.today()

        super().save(*args, **kwargs)

        if self.status == 'done' and old_status != 'done':
            next_step = ProductionTask.objects.filter(
                order=self.order,
                part=self.part,
                step_order=self.step_order + 1
            ).first()
            if next_step and next_step.status == 'waiting':
                next_step.status = 'pending'
                next_step.save()

            self.update_order_status()

    def update_order_status(self):
        order = self.order
        all_tasks = order.tasks.all()
        total = all_tasks.count()
        done = all_tasks.filter(status='done' ).count() 

        if total == 0:
            return
        if done == total:
            new_status = 'completed'
        elif done > 0:
            new_status = 'producing'
        else:
            new_status = 'planned'

        if order.status != new_status:
            order.status = new_status
            order.save(update_fields=['status'])


class WorkerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    stage = models.CharField(max_length=50, choices=STATION_CHOICES, verbose_name="مرحله کاری")

    def __str__(self):
        return f"{self.user.username} - {self.get_stage_display()}"

    class Meta:
        verbose_name = "پروفایل کارگر"
        verbose_name_plural = "پروفایل کارگران"


class ProductionLog(models.Model):
    STATION_CHOICES = STATION_CHOICES
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name='logs', verbose_name="آیتم سفارش")
    stage = models.CharField(max_length=50, choices=STATION_CHOICES, verbose_name="مرحله")
    user = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, verbose_name="کاربر")
    notes = models.CharField(max_length=200, blank=True, verbose_name="یادداشت")
    created_at = PersianDateField(auto_now_add=True, verbose_name="تاریخ ثبت")

    class Meta:
        verbose_name = "گزارش تولید"
        verbose_name_plural = "گزارش‌های تولید"






class PackagingUnit(models.Model):
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name='packaging_units')
    unit_number = models.PositiveIntegerField(verbose_name="شماره واحد")
    qr_code = models.ImageField(upload_to='qr/packaging/', blank=True, null=True, verbose_name="QR بسته‌بندی")
    
    # وضعیت بسته‌بندی
    is_packed = models.BooleanField(default=False, verbose_name="بسته‌بندی شده")
    packed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان بسته‌بندی")
    packed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='packed_units', verbose_name="بسته‌بندی‌کننده")
    
    # وضعیت ارسال
    is_shipped = models.BooleanField(default=False, verbose_name="ارسال شده")
    shipped_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان ارسال")
    shipped_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='shipped_units', verbose_name="ارسال‌کننده")

    class Meta:
        unique_together = ('order_item', 'unit_number')
        verbose_name = "واحد بسته‌بندی"
        verbose_name_plural = "واحدهای بسته‌بندی و ارسال"

    def __str__(self):
        return f"بسته {self.unit_number} از {self.order_item}"

    def get_absolute_url(self):
        return reverse('scan_packaging_unit', args=[self.id])








class ShipmentLog(models.Model):
    packaging_unit = models.ForeignKey(
        PackagingUnit,
        on_delete=models.CASCADE,
        related_name='shipment_logs',
        verbose_name="بسته‌بندی"
    )
    plate_number = models.CharField(max_length=50, verbose_name="پلاک")
    shipped_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ارسال")
    shipped_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="ارسال‌کننده")

    class Meta:
        verbose_name = "بارگیری"
        verbose_name_plural = "بارگیری"




