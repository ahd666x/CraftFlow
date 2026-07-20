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


def get_unique_color_codes_for_item(item):
    """
    استخراج لیست کدهای رنگی منحصربه‌فرد برای یک آیتم سفارش.
    اولویت: رنگ‌های ثبت‌شده در سفارش > رنگ‌های پیش‌فرض محصول
    """
    color_codes = set()

    order_colors = item.ordercolor.all()
    if order_colors.exists():
        for color in order_colors:
            if color.code and color.code != 'nan':
                color_codes.add(str(color.code))
    else:
        default_colors = item.product.default_colors or {}
        if isinstance(default_colors, str):
            try:
                import json
                default_colors = json.loads(default_colors) or {}
            except (ValueError, TypeError):
                default_colors = {}
        for code in default_colors.values():
            if code and code != 'nan':
                color_codes.add(str(code))

    return list(color_codes)


def get_painting_process_for_color(color_code):
    """
    بازگرداندن اولین روند فعال که color_code در لیست آن وجود دارد.
    تطابق با تبدیل هر دو به رشته انجام می‌شود تا نوع داده (عدد/رشته)干预 نکند.
    """
    from .models import PaintingProcess

    if not color_code:
        return None

    color_code = str(color_code).strip()

    processes = PaintingProcess.objects.filter(is_active=True)

    for process in processes:
        codes = process.color_codes or []
        str_codes = [str(c) for c in codes]
        if color_code in str_codes:
            return process

    return None


def auto_assign_paint_tasks(target_date=None):
    """تخصیص خودکار کارگران به تسک‌های نقاشی (بر اساس OrderItem)"""
    import logging
    from datetime import datetime, time, timedelta
    from django.utils import timezone
    logger = logging.getLogger(__name__)

    from .models import ProductionTask, WorkerProfile
    from django.db.models import Count, Q

    reference_date = target_date.togregorian() if target_date else timezone.localdate()

    tasks_qs = ProductionTask.objects.filter(
        station_name='paint',
        assigned_worker__isnull=True,
        status__in=['pending', 'waiting'],
    )
    if target_date:
        tasks_qs = tasks_qs.filter(scheduled_start__date=reference_date)

    tasks = list(
        tasks_qs.select_related('painting_stage', 'order_item').order_by('scheduled_start', 'step_order')
    )

    if not tasks:
        return 0

    day_start = timezone.make_aware(datetime.combine(reference_date, time(8, 0)))
    day_end = timezone.make_aware(datetime.combine(reference_date, time(16, 30)))
    break_start = timezone.make_aware(datetime.combine(reference_date, time(12, 30)))
    break_end = timezone.make_aware(datetime.combine(reference_date, time(13, 30)))

    def next_available_start(start):
        if start < day_start:
            return day_start
        if break_start <= start < break_end:
            return break_end
        if start >= day_end:
            next_day = reference_date + timedelta(days=1)
            return timezone.make_aware(datetime.combine(next_day, time(8, 0)))
        return start

    paint_workers_qs = WorkerProfile.objects.filter(stage='paint').annotate(
        active_tasks=Count(
            'user__assigned_tasks',
            filter=Q(user__assigned_tasks__station_name='paint', user__assigned_tasks__status__in=['pending', 'waiting'])
        )
    )

    worker_load = {}
    for wp in paint_workers_qs:
        worker_load[wp.user_id] = (wp, wp.active_tasks)

    all_paint_workers = list(paint_workers_qs)

    assigned_task_ids = set()
    for task in tasks:
        skill = task.painting_stage.required_skill if task.painting_stage else 'painter'

        candidates = [
            wp for wp in all_paint_workers
            if skill in (wp.skills or [])
        ]

        fresh = [wp for wp in candidates if wp.user_id not in assigned_task_ids]
        pool = fresh if fresh else candidates

        if pool:
            selected_worker = min(pool, key=lambda wp: worker_load.get(wp.user_id, (None, 0))[1])
            task.assigned_worker = selected_worker.user
            if not task.scheduled_start:
                task.scheduled_start = next_available_start(timezone.now())
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
    آیتم‌های آماده نقاشی:
    - لاگ مونتاژ اول (mon) داشته باشند
    - لاگ نقاشی (paint) نداشته باشند
    - لاگ بسته‌بندی (packaging) نداشته باشند
    - حداقل یک تسک نقاشی pending/waiting داشته باشند یا اصلاً تسک نقاشی نداشته باشند
    """
    from django.db.models import Exists, OuterRef, Prefetch, Q

    from .models import OrderItem, ProductionLog, ProductionTask

    has_mon_log = ProductionLog.objects.filter(
        order_item=OuterRef('pk'),
        stage='mon',
    )
    has_paint_log = ProductionLog.objects.filter(
        order_item=OuterRef('pk'),
        stage='paint',
    )
    has_packaging_log = ProductionLog.objects.filter(
        order_item=OuterRef('pk'),
        stage='packaging',
    )
    has_unfinished_paint_task = ProductionTask.objects.filter(
        order_item=OuterRef('pk'),
        station_name='paint',
        status__in=['pending', 'waiting'],
    )
    has_any_paint_task = ProductionTask.objects.filter(
        order_item=OuterRef('pk'),
        station_name='paint',
    )

    qs = OrderItem.objects.annotate(
        has_mon=Exists(has_mon_log),
        has_paint_log=Exists(has_paint_log),
        has_packaging_log=Exists(has_packaging_log),
        has_unfinished_paint=Exists(has_unfinished_paint_task),
        has_any_paint=Exists(has_any_paint_task),
    ).filter(
        has_mon=True,
        has_paint_log=False,
        has_packaging_log=False,
    ).filter(
        Q(has_unfinished_paint=True) | Q(has_any_paint=False)
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
    """آیتم‌های آماده که هیچ تسک زمان‌بندی‌شده‌ای ندارند (همه تسک‌ها بدون زمان هستند)"""
    from django.db.models import Exists, OuterRef

    from .models import ProductionTask

    ready = get_painting_ready_items_queryset(search=search, process_id=process_id)

    has_scheduled_task = ProductionTask.objects.filter(
        order_item=OuterRef('pk'),
        station_name='paint',
        scheduled_start__isnull=False,
    )
    return ready.annotate(_has_scheduled=Exists(has_scheduled_task)).filter(_has_scheduled=False)


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
    day_end = timezone.make_aware(datetime.combine(gregorian, time(16, 30)))
    break_start = timezone.make_aware(datetime.combine(gregorian, time(12, 30)))
    break_end = timezone.make_aware(datetime.combine(gregorian, time(13, 30)))

    def next_available_start(start):
        if start < day_start:
            return day_start
        if break_start <= start < break_end:
            return break_end
        if start >= day_end:
            next_day = (target_jdate + timedelta(days=1)).togregorian()
            return timezone.make_aware(datetime.combine(next_day, time(8, 0)))
        return start

    last_end = ProductionTask.objects.filter(
        station_name='paint',
        scheduled_end__date=gregorian,
    ).aggregate(max_end=Max('scheduled_end'))['max_end']

    current_start = next_available_start(last_end) if last_end else day_start
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
            current_start = next_available_start(current_start)
            duration = task.painting_stage.duration_minutes if task.painting_stage else 60
            drying = task.painting_stage.drying_time_minutes if task.painting_stage else 0
            task.scheduled_start = current_start
            task.scheduled_end = current_start + timedelta(minutes=duration)
            task.save(update_fields=['scheduled_start', 'scheduled_end'])
            current_start = task.scheduled_end + timedelta(minutes=drying)
            scheduled_count += 1

    return scheduled_count


def get_item_paint_preview(item):
    """
    پیش‌نمایش وضعیت نقاشی یک آیتم: رنگ‌ها، روند(های) تشخیص‌داده‌شده،
    تعداد مراحل و زمان تخمینی. برای نمایش در جدول «آماده نقاشی» بدون نیاز به ساخت تسک.
    """
    color_codes = get_unique_color_codes_for_item(item)
    result = {
        'item_id': item.id,
        'color_codes': color_codes,
        'processes': [],
        'unmatched_codes': [],
        'already_has_tasks': item.paint_tasks.filter(station_name='paint').exists(),
        'total_minutes': 0,
        'ok': True,
        'reason': None,
    }
    if not color_codes:
        result['ok'] = False
        result['reason'] = 'no_color'
        return result

    for code in color_codes:
        process = get_painting_process_for_color(code)
        if not process:
            result['unmatched_codes'].append(code)
            continue
        stage_count = process.stages.count()
        total_minutes = sum(s.duration_minutes for s in process.stages.all())
        result['processes'].append({
            'color_code': code,
            'process_name': process.name,
            'stage_count': stage_count,
            'total_minutes': total_minutes,
        })
        result['total_minutes'] += total_minutes

    if not result['processes']:
        result['ok'] = False
        result['reason'] = 'no_process_match'

    return result


def create_and_schedule_items_for_date(item_ids, target_jdate=None):
    """
    برای هر آیتم انتخاب‌شده:
      ۱. اگر تسک نقاشی ندارد، بر اساس کدهای رنگ تسک‌ها را می‌سازد (بدون BOM/Part)
      ۲. سپس همه‌ی تسک‌های بدون‌زمانِ این آیتم‌ها را زمان‌بندی می‌کند
      - اگر target_jdate داده شود: در همان روز زمان‌بندی می‌کند
      - اگر None باشد: اولین روز با ظرفیت کافی (از امروز) پیدا و زمان‌بندی می‌شود
    """
    from .models import OrderItem, ProductionTask, create_paint_tasks

    items = OrderItem.objects.filter(pk__in=item_ids).prefetch_related('ordercolor', 'paint_tasks')

    created_items = []
    skipped = []
    new_tasks = []

    for item in items:
        has_existing_tasks = item.paint_tasks.filter(station_name='paint').exists()
        if has_existing_tasks:
            continue

        color_codes = get_unique_color_codes_for_item(item)
        item_colors = {c.part: c.code for c in item.ordercolor.all()}
        if not color_codes:
            skipped.append({'item_id': item.id, 'reason': 'no_color'})
            continue

        base_step = 0
        item_created_any = False
        for color_code in color_codes:
            process = get_painting_process_for_color(color_code)
            if not process:
                continue
            color_part_name = next(
                (part for part, code in item_colors.items() if code == color_code),
                f"رنگ {color_code}"
            )
            create_paint_tasks(
                tasks_list=new_tasks,
                order=item.order,
                quantity=item.quantity,
                process=process,
                base_step=base_step,
                order_item=item,
                color_part=color_part_name,
            )
            base_step += process.stages.count()
            item_created_any = True

        if item_created_any:
            created_items.append(item.id)
        else:
            skipped.append({'item_id': item.id, 'reason': 'no_process_match'})

    if new_tasks:
        ProductionTask.objects.bulk_create(new_tasks)

    if target_jdate:
        scheduled_date = target_jdate
        scheduled_count = schedule_paint_tasks_for_items(item_ids, target_jdate)
    else:
        scheduled_count, scheduled_date = schedule_paint_items_auto(item_ids)

    return {
        'scheduled_count': scheduled_count,
        'scheduled_date': scheduled_date,
        'created_items': created_items,
        'skipped': skipped,
    }


def schedule_paint_items_auto(item_ids, start_jdate=None):
    """
    زمان‌بندی تسک‌های نقاشی آیتم‌های انتخاب‌شده از اولین روز (start_jdate یا امروز)
    به بعد. رعایت ساعت کاری ۸:۰۰–۱۶:۳۰ و وقفه ناهار ۱۲:۳۰–۱۳:۳۰.
    اگر تسک‌ها در یک روز جا نشوند، باقی‌مانده به روزهای بعد منتقل می‌شود.
    بازگشت: (scheduled_count, first_scheduled_jdate)
    """
    import jdatetime

    from .models import ProductionTask

    if start_jdate is None:
        start_jdate = jdatetime.date.today()

    remaining_ids = list(
        ProductionTask.objects.filter(
            order_item_id__in=item_ids,
            station_name='paint',
            status__in=['pending', 'waiting'],
            scheduled_start__isnull=True,
        ).values_list('id', flat=True)
    )
    if not remaining_ids:
        return 0, None

    scheduled_count = 0
    target_jdate = start_jdate

    # هر روز تا جایی که ظرفیت دارد تسک زمان‌بندی می‌شود؛ باقی‌مانده روز بعد.
    safety = 0
    while remaining_ids and safety < 400:
        scheduled_now, target_jdate = _schedule_day_slice(remaining_ids, target_jdate)
        scheduled_count += scheduled_now
        remaining_ids = list(
            ProductionTask.objects.filter(
                id__in=remaining_ids,
                station_name='paint',
                status__in=['pending', 'waiting'],
                scheduled_start__isnull=True,
            ).values_list('id', flat=True)
        )
        target_jdate = target_jdate + jdatetime.timedelta(days=1)
        safety += 1

    return scheduled_count, target_jdate - jdatetime.timedelta(days=1)


def _schedule_day_slice(task_ids, target_jdate):
    """زمان‌بندی تا جایی که ظرفیت روز اجازه دهد؛ بازگشت (تعداد، تاریخ هدف)"""
    from datetime import datetime, time, timedelta

    from django.db.models import Max
    from django.utils import timezone

    from .models import ProductionTask

    gregorian = target_jdate.togregorian()
    day_start = timezone.make_aware(datetime.combine(gregorian, time(8, 0)))
    day_end = timezone.make_aware(datetime.combine(gregorian, time(16, 30)))
    break_start = timezone.make_aware(datetime.combine(gregorian, time(12, 30)))
    break_end = timezone.make_aware(datetime.combine(gregorian, time(13, 30)))

    def next_available_start(start):
        if start is None:
            return None
        if start < day_start:
            return day_start
        if break_start <= start < break_end:
            return break_end
        if start >= day_end:
            return None
        return start

    last_end = ProductionTask.objects.filter(
        station_name='paint',
        scheduled_end__date=gregorian,
    ).aggregate(max_end=Max('scheduled_end'))['max_end']

    current_start = next_available_start(last_end) if last_end else day_start
    scheduled_count = 0

    tasks = list(
        ProductionTask.objects.filter(
            id__in=task_ids,
            station_name='paint',
            status__in=['pending', 'waiting'],
            scheduled_start__isnull=True,
        ).select_related('painting_stage').order_by('step_order')
    )

    for task in tasks:
        current_start = next_available_start(current_start)
        if current_start is None:
            break
        duration = task.painting_stage.duration_minutes if task.painting_stage else 60
        drying = task.painting_stage.drying_time_minutes if task.painting_stage else 0
        if duration <= 0:
            duration = 1
        end = current_start + timedelta(minutes=duration)
        # اگر انتهای تسک از پایان روز یا شروع ناهار بگذرد، به روز بعد موکول شود
        if end > day_end or (break_start <= current_start < break_end):
            break
        task.scheduled_start = current_start
        task.scheduled_end = end
        task.save(update_fields=['scheduled_start', 'scheduled_end'])
        current_start = end + timedelta(minutes=drying)
        scheduled_count += 1

    return scheduled_count, target_jdate


def schedule_paint_tasks_for_items(item_ids, target_jdate):
    """زمان‌بندی تسک‌های نقاشی آیتم‌های انتخاب‌شده در یک روز"""
    from datetime import datetime, time, timedelta

    from django.db.models import Max
    from django.utils import timezone

    from .models import ProductionTask

    tasks = list(
        ProductionTask.objects.filter(
            order_item_id__in=item_ids,
            station_name='paint',
            status__in=['pending', 'waiting'],
            scheduled_start__isnull=True,
        ).select_related('painting_stage').order_by('step_order')
    )
    if not tasks:
        return 0

    gregorian = target_jdate.togregorian()
    day_start = timezone.make_aware(datetime.combine(gregorian, time(8, 0)))
    day_end = timezone.make_aware(datetime.combine(gregorian, time(16, 30)))
    break_start = timezone.make_aware(datetime.combine(gregorian, time(12, 30)))
    break_end = timezone.make_aware(datetime.combine(gregorian, time(13, 30)))

    def next_available_start(start):
        if start < day_start:
            return day_start
        if break_start <= start < break_end:
            return break_end
        if start >= day_end:
            next_day = (target_jdate + timedelta(days=1)).togregorian()
            return timezone.make_aware(datetime.combine(next_day, time(8, 0)))
        return start

    last_end = ProductionTask.objects.filter(
        station_name='paint',
        scheduled_end__date=gregorian,
        order_item_id__in=item_ids,
    ).aggregate(max_end=Max('scheduled_end'))['max_end']

    current_start = next_available_start(last_end) if last_end else day_start
    scheduled_count = 0

    for task in tasks:
        current_start = next_available_start(current_start)
        duration = task.painting_stage.duration_minutes if task.painting_stage else 60
        drying = task.painting_stage.drying_time_minutes if task.painting_stage else 0
        task.scheduled_start = current_start
        task.scheduled_end = current_start + timedelta(minutes=duration)
        task.save(update_fields=['scheduled_start', 'scheduled_end'])
        current_start = task.scheduled_end + timedelta(minutes=drying)
        scheduled_count += 1

    return scheduled_count


def repaint_item_ids_for_date(item_ids, target_jdate):
    """
    بازنشانی و زمان‌بندی مجدد تسک‌های نقاشی آیتم‌های انتخاب‌شده.
    این تابع برای رفع مشکلات برنامه‌ریزی اشتباه استفاده می‌شود:
    - همه‌ی تسک‌های نقاشی این آیتم‌ها در تاریخ موردنظر حذف می‌شوند
    - مجدداً طبق منطق درست ایجاد و زمان‌بندی می‌شوند
    """
    from .models import OrderItem, ProductionTask

    items = OrderItem.objects.filter(pk__in=item_ids)
    task_ids = []
    for item in items:
        task_ids.extend(
            ProductionTask.objects.filter(
                order_item=item,
                station_name='paint',
                scheduled_start__date=target_jdate.togregorian(),
            ).values_list('pk', flat=True)
        )

    if task_ids:
        done_count = ProductionTask.objects.filter(pk__in=task_ids, status='done').count()
        if done_count:
            raise ValueError(f'{done_count} تسک قبلاً انجام شده و نمی‌تواند بازنشانی شود.')
        ProductionTask.objects.filter(pk__in=task_ids).delete()

    return create_and_schedule_items_for_date(item_ids, target_jdate)


def painting_nav_context():
    """متغیرهای مشترک ناوبری پنل نقاشی"""
    import jdatetime

    return {
        'today': jdatetime.date.today().strftime('%Y/%m/%d'),
        'unscheduled_ready_count': get_unscheduled_ready_items().count(),
    }
