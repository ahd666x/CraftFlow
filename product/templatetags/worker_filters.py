# product/templatetags/worker_filters.py

from django import template

register = template.Library()

@register.filter
def format_costs(costs):
    """تبدیل دیکشنری هزینه‌ها به رشته قابل خواندن"""
    if not costs:
        return ''
    return ', '.join([f"{k}:{v}" for k, v in costs.items() if v > 0])