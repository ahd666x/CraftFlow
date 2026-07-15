# product/templatetags/product_filters.py
from django import template
from django import template
from django.contrib.humanize.templatetags.humanize import intcomma as humanize_intcomma
import jdatetime
from django import template


register = template.Library()


@register.filter(name='format_colors')
def format_colors(value):
    """تبدیل دیکشنری رنگ‌ها به لیستی از (نام, کد) برای حلقه‌ی قالب"""
    if not isinstance(value, dict):
        return []
    return value.items()




@register.filter
def split(value, arg):
    return value.split(arg)






@register.filter
def get_item(dictionary, key):
    """دریافت مقدار از دیکشنری با کلید مشخص"""
    if dictionary is None:
        return ''
    return dictionary.get(key, '')



@register.filter
def zip_lists(a, b):
    """ترکیب دو لیست در قالب"""
    return zip(a, b)

from django import template



@register.filter
def get_item(dictionary, key):
    if dictionary is None:
        return ''
    return dictionary.get(key, '')

@register.filter
def zip_lists(a, b):
    return zip(a, b)











@register.filter
def intcomma(value):
    """نمایش اعداد با جداکننده هزارگان"""
    try:
        return humanize_intcomma(int(value))
    except (ValueError, TypeError):
        return value

@register.filter
def multiply(value, arg):
    """ضرب دو عدد"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0
    









@register.filter
def intcomma(value):
    try:
        return humanize_intcomma(int(value))
    except (ValueError, TypeError):
        return value







@register.filter
def persian_date(value):
    """تبدیل datetime یا date میلادی به رشتهٔ شمسی YYYY/MM/DD"""
    if not value:
        return ''
    try:
        # اگر datetime باشد، قسمت date آن را می‌گیریم
        if hasattr(value, 'date'):
            value = value.date()
        return jdatetime.date.fromgregorian(date=value).strftime('%Y/%m/%d')
    except Exception:
        return str(value)