# product/utils.py
import re

def get_material_for_color(color_code, mapping=None):
    """برگرداندن نمونه Material بر اساس کد رنگ و نگاشت دلخواه"""
    from .models import Material   # ← import محلی برای جلوگیری از circular import

    default_map = {
        '1': 'kham',
        '2': 'kham',
        '3': 'kham',
        '4': 'kham',
        '5': 'kham',
        '6': 'kham',
        '7': 'kham',
        '8': 'balot',
        '9': 'gerdo',
        '10': 'gerdo',
        'بتنی' : 'botoni',
        'جناغی' : 'kham',
        '11': 'balot',

    }

    if not isinstance(mapping , dict):
        mapping=None

    if mapping:
        # print(color_code)
        material_name = mapping.get(color_code)
    else:
        material_name = default_map.get(color_code)

    if material_name:
        material, _ = Material.objects.get_or_create(name=material_name, thickness=16)
        return material
    return None







def parse_size_string(size_str):
    """تبدیل رشته اندازه (مثل '200' یا '120x60') به دیکشنری length, width"""
    if not size_str:
        return {}
    numbers = re.findall(r'\d+', size_str)
    if len(numbers) == 1:
        return {'length': int(numbers[0]), 'width': None}
    elif len(numbers) >= 2:
        return {'length': int(numbers[0]), 'width': int(numbers[1])}
    return {}



def apply_size_adjustment(original_length, original_width, diff_dict, rule):
    if not rule or not diff_dict:
        return float(original_length), float(original_width)
    
    # جایگزینی متغیرها
    rule = rule.replace('length_diff', str(diff_dict.get('length_diff', 0)))
    rule = rule.replace('width_diff', str(diff_dict.get('width_diff', 0)))
    
    allowed_names = {
        "length": float(original_length),
        "width": float(original_width),
        "length_diff": float(diff_dict.get('length_diff', 0)),
        "width_diff": float(diff_dict.get('width_diff', 0)),
    }
    try:
        new_length = eval(rule, {"__builtins__": {}}, allowed_names)
        # عرض را هم اگر قاعده‌ای برایش نوشته شده باشد تغییر دهیم
        # فعلاً فقط طول تغییر می‌کند
        new_width = original_width
    except Exception as e:
        print("Error in size rule:", e)
        new_length = original_length
        new_width = original_width
    return float(new_length), float(new_width)






def update_barcode_size(original_barcode, new_length, new_width, order_item_id=None):
    """
    ابعاد درون بارکد را با ابعاد جدید جایگزین می‌کند و شناسه آیتم سفارش را اضافه می‌نماید.
    """
    if not original_barcode:
        return original_barcode

    # تبدیل اعداد اعشاری به عدد صحیح
    # length_int = int(round(new_length))
    # width_int = int(round(new_width))
    length_int = int((new_length))
    width_int = int((new_width))
    new_size_str = f"{length_int}x{width_int}"

    # جایگزینی ابعاد
    pattern = r'\d+x\d+'
    if re.search(pattern, original_barcode):
        new_barcode = re.sub(pattern, new_size_str, original_barcode)
    else:
        new_barcode = f"{original_barcode}.{new_size_str}"

    # اضافه کردن شناسه آیتم سفارش (در صورت وجود)
    if order_item_id:
        # حذف پسوند احتمالی قبلی (مثلاً .1set) و اضافه کردن .item{id}
        # new_barcode = re.sub(r'\.\d+set$', '', new_barcode)
        new_barcode = f"{new_barcode}.item{order_item_id}"

    return new_barcode