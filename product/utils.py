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


def auto_assign_paint_tasks(target_date=None):
    """تخصیص خودکار کارگران به تسک‌های نقاشی (بر اساس OrderItem)"""
    import logging
    from datetime import timedelta
    from django.utils import timezone
    logger = logging.getLogger(__name__)

    from .models import ProductionTask, WorkerProfile
    from django.db.models import Count, Q

    tasks_qs = ProductionTask.objects.filter(
        station_name='paint',
        assigned_worker__isnull=True,
        status__in=['pending', 'waiting'],
    )
    if target_date:
        gregorian = target_date.togregorian()
        tasks_qs = tasks_qs.filter(scheduled_start__date=gregorian)

    tasks = list(
        tasks_qs.select_related('painting_stage', 'order_item').order_by('scheduled_start', 'step_order')
    )

    if not tasks:
        return

    worker_load = {}
    for wp in WorkerProfile.objects.annotate(
        active_tasks=Count(
            'user__assigned_tasks',
            filter=Q(user__assigned_tasks__station_name='paint', user__assigned_tasks__status__in=['pending', 'waiting'])
        )
    ):
        worker_load[wp.user_id] = (wp, wp.active_tasks)

    assigned_task_ids = set()
    for task in tasks:
        skill = task.painting_stage.required_skill if task.painting_stage else 'painter'

        candidates = [
            wp for wp in WorkerProfile.objects.all()
            if skill in (wp.skills or [])
        ]

        fresh = [wp for wp in candidates if wp.user_id not in assigned_task_ids]
        pool = fresh if fresh else candidates

        if pool:
            selected_worker = min(pool, key=lambda wp: worker_load.get(wp.user_id, (None, 0))[1])
            task.assigned_worker = selected_worker.user
            if not task.scheduled_start:
                task.scheduled_start = timezone.now()
            if task.painting_stage and not task.scheduled_end:
                task.scheduled_end = task.scheduled_start + timedelta(minutes=task.painting_stage.duration_minutes)
            task.save()
            _, load = worker_load.get(selected_worker.user_id, (None, 0))
            worker_load[selected_worker.user_id] = (selected_worker, load + 1)
            assigned_task_ids.add(selected_worker.user_id)
            item_label = task.order_item.id if task.order_item else '-'
            logger.info("تسک %s (آیتم %s) به %s اختصاص یافت.", task.id, item_label, selected_worker.user.username)
        else:
            logger.warning("هیچ کارگری با مهارت %s برای تسک %s یافت نشد.", skill, task.id)


# ---------------------------------------------------------------------------
# مدیریت نقاشی — کوئری و برنامه‌ریزی
# ---------------------------------------------------------------------------

def parse_jalali_date(date_str):
    """تبدیل رشته Y-m-d جلالی به jdatetime.date"""
    import jdatetime
    if not date_str:
        return jdatetime.date.today()
    try:
        y, m, d = map(int, date_str.split('-'))
        return jdatetime.date(y, m, d)
    except (ValueError, TypeError) as exc:
        raise ValueError('تاریخ نامعتبر است') from exc


def get_painting_ready_items_queryset(search=None, process_id=None):
    """
    بازگرداندن Queryset از آیتم‌های سفارش که لاگ مونتاژ اول (mon) در ProductionLog دارند.
    (بدون در نظر گرفتن وضعیت تسک نقاشی)
    """
    from django.db.models import Exists, OuterRef, Prefetch, Q

    from .models import OrderItem, ProductionLog

    has_mon_log = ProductionLog.objects.filter(
        order_item=OuterRef('pk'),
        stage='mon',
    )

    qs = OrderItem.objects.annotate(
        has_mon=Exists(has_mon_log),
    ).filter(
        has_mon=True,
    ).distinct().select_related(
        'order', 'product', 'order__customer',
    ).prefetch_related(
        'ordercolor',
        'paint_tasks__painting_stage',
        Prefetch('logs', queryset=ProductionLog.objects.filter(stage='mon')),
    )

    if search:
        qs = qs.filter(
            Q(order__id__icontains=search) |
            Q(product__name__icontains=search) |
            Q(order__customer__name__icontains=search) |
            Q(order__number__icontains=search)
        )

    if process_id:
        qs = qs.filter(
            paint_tasks__painting_stage__process_id=process_id,
        ).distinct()

    return qs


def get_unscheduled_ready_items(search=None, process_id=None):
    """آیتم‌های آماده که هنوز در برنامه قرار نگرفته‌اند"""
    from .models import ProductionTask

    ready = get_painting_ready_items_queryset(search=search, process_id=process_id)
    unscheduled_ids = ProductionTask.objects.filter(
        station_name='paint',
        status__in=['pending', 'waiting'],
        scheduled_start__isnull=True,
        order_item__isnull=False,
    ).values_list('order_item_id', flat=True).distinct()

    return ready.filter(pk__in=unscheduled_ids)


def schedule_paint_items_for_date(item_ids, target_jdate):
    """قرار دادن تسک‌های نقاشی آیتم‌های انتخاب‌شده در برنامه یک روز"""
    from datetime import datetime, time, timedelta

    from django.db.models import Max
    from django.utils import timezone

    from .models import ProductionTask

    ready_ids = set(
        get_painting_ready_items_queryset().filter(pk__in=item_ids).values_list('pk', flat=True)
    )
    if not ready_ids:
        return 0

    gregorian = target_jdate.togregorian()
    day_start = timezone.make_aware(datetime.combine(gregorian, time(8, 0)))

    last_end = ProductionTask.objects.filter(
        station_name='paint',
        scheduled_end__date=gregorian,
    ).aggregate(max_end=Max('scheduled_end'))['max_end']

    current_start = max(last_end, day_start) if last_end else day_start
    scheduled_count = 0

    for item_id in ready_ids:
        tasks = list(
            ProductionTask.objects.filter(
                order_item_id=item_id,
                station_name='paint',
                status__in=['pending', 'waiting'],
                scheduled_start__isnull=True,
            ).select_related('painting_stage').order_by('step_order')
        )
        for task in tasks:
            task.scheduled_start = current_start
            duration = task.painting_stage.duration_minutes if task.painting_stage else 60
            drying = task.painting_stage.drying_time_minutes if task.painting_stage else 0
            task.scheduled_end = current_start + timedelta(minutes=duration)
            task.save(update_fields=['scheduled_start', 'scheduled_end'])
            current_start = task.scheduled_end + timedelta(minutes=drying)
            scheduled_count += 1

    return scheduled_count


def painting_nav_context():
    """متغیرهای مشترک ناوبری پنل نقاشی"""
    import jdatetime

    return {
        'today': jdatetime.date.today().strftime('%Y/%m/%d'),
        'unscheduled_ready_count': get_unscheduled_ready_items().count(),
    }
