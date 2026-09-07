from django.conf import settings
from django.db import models


class CustomerGroup(models.Model):
    name = models.CharField(max_length=100, verbose_name="نام گروه")
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="درصد تخفیف")
    description = models.TextField(blank=True, verbose_name="توضیحات")

    class Meta:
        verbose_name = "گروه مشتری"
        verbose_name_plural = "گروه‌های مشتری"
        ordering = ['name']

    def __str__(self):
        return self.name


class Customer(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='v2_customers', verbose_name="نماینده")
    group = models.ForeignKey(CustomerGroup, null=True, blank=True, on_delete=models.SET_NULL, related_name='customers', verbose_name="گروه")
    name = models.CharField(max_length=100, verbose_name="نام مشتری")
    phone = models.CharField(max_length=20, blank=True, verbose_name="تلفن")
    mobile = models.CharField(max_length=20, blank=True, verbose_name="موبایل")
    email = models.EmailField(blank=True, verbose_name="ایمیل")
    address = models.TextField(blank=True, verbose_name="آدرس")
    postal_code = models.CharField(max_length=20, blank=True, verbose_name="کد پستی")
    economic_code = models.CharField(max_length=20, blank=True, verbose_name="کد اقتصادی")
    national_id = models.CharField(max_length=20, blank=True, verbose_name="کد ملی")
    is_representative = models.BooleanField(default=False, verbose_name="نماینده است")
    notes = models.TextField(blank=True, verbose_name="یادداشت‌ها")
    balance = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="مانده حساب")
    credit_limit = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="سقف اعتبار")

    class Meta:
        verbose_name = "مشتری"
        verbose_name_plural = "مشتریان"
        ordering = ['name']

    def __str__(self):
        return self.name


class CustomerAddress(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='addresses', verbose_name="مشتری")
    title = models.CharField(max_length=100, verbose_name="عنوان")
    address = models.TextField(verbose_name="آدرس")
    city = models.CharField(max_length=100, verbose_name="شهر")
    postal_code = models.CharField(max_length=20, blank=True, verbose_name="کد پستی")
    receiver_name = models.CharField(max_length=100, verbose_name="نام گیرنده")
    receiver_phone = models.CharField(max_length=20, verbose_name="تلفن گیرنده")
    is_default = models.BooleanField(default=False, verbose_name="آدرس پیش‌فرض")

    class Meta:
        verbose_name = "آدرس مشتری"
        verbose_name_plural = "آدرس‌های مشتری"
        ordering = ['-is_default', 'title']

    def __str__(self):
        return f"{self.customer.name} - {self.title}"
