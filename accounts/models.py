from django.contrib.auth.models import User
from django.db import models
import datetime


def _default_work_start():
    return datetime.time(8, 0)


def _default_work_end():
    return datetime.time(16, 30)


def _default_break_start():
    return datetime.time(12, 30)


def _default_break_end():
    return datetime.time(13, 30)


class Worker(models.Model):
    STATION_CHOICES = [
        ('cut', 'برش'),
        ('cnc', 'CNC'),
        ('dr', 'سوراخکاری'),
        ('pvc', 'نوارکاری'),
        ('prs', 'پرس'),
        ('mon', 'مونتاژ اول'),
        ('vacum', 'وکیوم'),
        ('paint', 'نقاشی'),
        ('assembly2', 'مونتاژ نهایی'),
        ('packaging', 'بسته‌بندی'),
        ('shipping', 'ارسال'),
        ('quality', 'کنترل کیفیت'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='worker_profile', verbose_name="کاربر")
    employee_id = models.CharField(max_length=50, unique=True, verbose_name="کد کارمندی", blank=True)
    station = models.CharField(max_length=50, choices=STATION_CHOICES, verbose_name="ایستگاه کاری")
    skills = models.JSONField(default=list, blank=True, verbose_name="مهارت‌ها")
    skill_priority = models.JSONField(default=dict, blank=True, verbose_name="اولویت مهارت‌ها")
    is_available = models.BooleanField(default=True, verbose_name="در دسترس")
    work_start = models.TimeField(default=_default_work_start, verbose_name="شروع کار")
    work_end = models.TimeField(default=_default_work_end, verbose_name="پایان کار")
    break_start = models.TimeField(default=_default_break_start, verbose_name="شروع استراحت")
    break_end = models.TimeField(default=_default_break_end, verbose_name="پایان استراحت")
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=0, default=0, verbose_name="حقوق ساعتی")
    excluded_products = models.ManyToManyField('products.Product', blank=True, verbose_name="محصولات ممنوعه")
    excluded_items = models.ManyToManyField('sales.CustomerOrderItem', blank=True, verbose_name="آیتم‌های ممنوعه")

    class Meta:
        verbose_name = "کارگر"
        verbose_name_plural = "کارگران"
        ordering = ['user__last_name', 'user__first_name']

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - {self.get_station_display()}"


class WorkerSchedule(models.Model):
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name='schedules', verbose_name="کارگر")
    date = models.DateField(verbose_name="تاریخ")
    is_working = models.BooleanField(default=True, verbose_name="روز کاری")
    overtime_hours = models.DecimalField(max_digits=4, decimal_places=2, default=0, verbose_name="ساعت اضافه کار")
    notes = models.CharField(max_length=255, blank=True, verbose_name="یادداشت")

    class Meta:
        verbose_name = "برنامه کاری کارگر"
        verbose_name_plural = "برنامه‌های کاری کارگران"
        unique_together = ['worker', 'date']
        ordering = ['date', 'worker']

    def __str__(self):
        return f"{self.worker} - {self.date}"


class Holiday(models.Model):
    date = models.DateField(unique=True, verbose_name="تاریخ")
    description = models.CharField(max_length=200, blank=True, verbose_name="مناسبت")
    is_recurring = models.BooleanField(default=False, verbose_name="تکرار سالانه")

    class Meta:
        verbose_name = "تعطیلی"
        verbose_name_plural = "تعطیلات"
        ordering = ['date']

    def __str__(self):
        return f"{self.date} - {self.description}" if self.description else str(self.date)
