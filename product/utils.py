# product/utils.py
import re
import json
import logging
from datetime import timedelta
from functools import lru_cache

import jdatetime
from django.db import transaction
from django.db.models import Exists, OuterRef, Prefetch, Q, Max
from django.contrib.auth.models import User
from django.utils import timezone

# ===================================================================
#   ایمپورت مدل‌ها
# ===================================================================
from .models import (
    ProductionTask,
    OrderItem,
    ProductionLog,
    PaintingProcess,
    WorkerProfile,
    Material,
    create_paint_tasks,
)

logger = logging.getLogger(__name__)

# ===================================================================
#   کش‌های سراسری (برای کاهش Query)
#   نکته: این کش‌ها به‌صورت خودکار invalidate نمی‌شن. اگر جایی در
#   models.py سیگنال post_save/post_delete برای PaintingProcess یا
#   WorkerProfile دارید، از invalidate_paint_caches() در آنجا صدا بزنید.
#   علاوه بر این، PaintingScheduler در ابتدای هر اجرا کش کارگران را
#   به‌صورت اجباری تازه می‌کند تا زمان‌بندی همیشه روی داده‌ی زنده کار کند.
# ===================================================================
_PAINT_PROCESS_CACHE = {}
_PAINT_WORKER_CACHE = None


def invalidate_paint_caches():
    """پاک کردن کش‌های سراسری فرآیند نقاشی و کارگران."""
    global _PAINT_PROCESS_CACHE, _PAINT_WORKER_CACHE
    _PAINT_PROCESS_CACHE = {}
    _PAINT_WORKER_CACHE = None


def _get_process_cache(force_refresh=False):
    """برگرداندن کش فرآیندهای نقاشی (بارگذاری یک‌باره، قابل رفرش)."""
    global _PAINT_PROCESS_CACHE
    if force_refresh or not _PAINT_PROCESS_CACHE:
        fresh = {}
        for p in PaintingProcess.objects.filter(is_active=True).prefetch_related('stages'):
            for code in (p.color_codes or []):
                fresh[str(code)] = p
        _PAINT_PROCESS_CACHE = fresh
    return _PAINT_PROCESS_CACHE


def _get_worker_cache(force_refresh=False):
    """برگرداندن کش کارگران نقاشی (بارگذاری یک‌باره، قابل رفرش)."""
    global _PAINT_WORKER_CACHE
    if force_refresh or _PAINT_WORKER_CACHE is None:
        _PAINT_WORKER_CACHE = list(
            WorkerProfile.objects.filter(stage='paint')
            .select_related('user')
            .values('user_id', 'skills', 'user__username')
        )
    return _PAINT_WORKER_CACHE


# ===================================================================
#   جایگزین امن برای eval
# ===================================================================
def _safe_eval(expr, allowed_names):
    """
    ارزیابی امن عبارت ریاضی با استفاده از simpleeval (در صورت وجود) یا fallback دستی.
    """
    try:
        from simpleeval import simple_eval
        return simple_eval(expr, names=allowed_names)
    except ImportError:
        import ast
        import operator

        ops = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.USub: operator.neg,
        }

        def _eval_node(node):
            if isinstance(node, ast.Constant):
                return node.value
            if isinstance(node, ast.Name):
                if node.id not in allowed_names:
                    raise ValueError(f"متغیر غیرمجاز: {node.id}")
                return allowed_names[node.id]
            if isinstance(node, ast.BinOp):
                return ops[type(node.op)](_eval_node(node.left), _eval_node(node.right))
            if isinstance(node, ast.UnaryOp):
                return ops[type(node.op)](_eval_node(node.operand))
            raise ValueError(f"عبارت غیرمجاز")

        tree = ast.parse(expr, mode='eval')
        return _eval_node(tree.body)


# ===================================================================
#   توابع کمکی عمومی
# ===================================================================

def get_material_for_color(color_code, mapping=None):
    default_map = {
        '1': 'kham', '2': 'kham', '3': 'kham', '4': 'kham', '5': 'kham',
        '6': 'kham', '7': 'kham', '8': 'balot', '9': 'gerdo', '10': 'gerdo',
        'بتنی': 'botoni', 'جناغی': 'kham', '11': 'balot',
    }
    if not isinstance(mapping, dict):
        mapping = None
    name = mapping.get(color_code) if mapping else default_map.get(color_code)
    if name:
        material, _ = Material.objects.get_or_create(name=name, thickness=16)
        return material
    return None


def parse_size_string(size_str):
    if not size_str:
        return {}
    nums = re.findall(r'\d+', size_str)
    if len(nums) == 1:
        return {'length': int(nums[0]), 'width': None}
    if len(nums) >= 2:
        return {'length': int(nums[0]), 'width': int(nums[1])}
    return {}


def apply_size_adjustment(original_length, original_width, diff_dict, rule):
    if not rule or not diff_dict:
        return float(original_length), float(original_width)
    rule = rule.replace('length_diff', str(diff_dict.get('length_diff', 0)))
    rule = rule.replace('width_diff', str(diff_dict.get('width_diff', 0)))
    allowed = {
        "length": float(original_length),
        "width": float(original_width),
        "length_diff": float(diff_dict.get('length_diff', 0)),
        "width_diff": float(diff_dict.get('width_diff', 0)),
    }
    try:
        new_length = _safe_eval(rule, allowed)
        return float(new_length), float(original_width)
    except Exception as e:
        logger.error(f"خطا در اعمال قانون اندازه '{rule}': {e}")
        return float(original_length), float(original_width)


def update_barcode_size(original_barcode, new_length, new_width, order_item_id=None):
    if not original_barcode:
        return original_barcode
    new_size = f"{int(new_length)}x{int(new_width)}"
    pattern = r'\d+x\d+'
    if re.search(pattern, original_barcode):
        barcode = re.sub(pattern, new_size, original_barcode)
    else:
        barcode = f"{original_barcode}.{new_size}"
    if order_item_id:
        barcode = f"{barcode}.item{order_item_id}"
    return barcode


def get_unique_color_codes_for_item(item):
    codes = set()
    for c in item.ordercolor.all():
        if c.code and c.code != 'nan':
            codes.add(str(c.code))
    if not codes:
        default = item.product.default_colors or {}
        if isinstance(default, str):
            try:
                default = json.loads(default) or {}
            except (json.JSONDecodeError, TypeError):
                default = {}
        for code in default.values():
            if code and code != 'nan':
                codes.add(str(code))
    return list(codes)


def get_item_color_assignments(item):
    assignments = []
    seen = set()
    order_colors = item.ordercolor.all()
    if order_colors.exists():
        for c in order_colors:
            if c.code and c.code != 'nan':
                key = (c.part, str(c.code))
                if key not in seen:
                    seen.add(key)
                    assignments.append(key)
    else:
        default = item.product.default_colors or {}
        if isinstance(default, str):
            try:
                default = json.loads(default) or {}
            except (json.JSONDecodeError, TypeError):
                default = {}
        for part, code in default.items():
            if code and code != 'nan':
                key = (part, str(code))
                if key not in seen:
                    seen.add(key)
                    assignments.append(key)
    return assignments


def get_painting_process_for_color(color_code):
    if not color_code:
        return None
    cache = _get_process_cache()
    return cache.get(str(color_code).strip())


def parse_jalali_date(date_str):
    if not date_str:
        return jdatetime.date.today()
    try:
        y, m, d = map(int, date_str.split('-'))
        return jdatetime.date(y, m, d)
    except (ValueError, TypeError):
        raise ValueError('تاریخ نامعتبر')


# ===================================================================
#   توابع مربوط به کوئری‌های آماده نقاشی
# ===================================================================

def get_painting_ready_items_queryset(search=None, process_id=None):
    has_mon = ProductionLog.objects.filter(order_item=OuterRef('pk'), stage='mon')
    has_paint = ProductionLog.objects.filter(order_item=OuterRef('pk'), stage='paint')
    has_pack = ProductionLog.objects.filter(order_item=OuterRef('pk'), stage='packaging')
    has_unfinished = ProductionTask.objects.filter(
        order_item=OuterRef('pk'), station_name='paint', status__in=['pending', 'waiting']
    )
    has_any = ProductionTask.objects.filter(order_item=OuterRef('pk'), station_name='paint')

    qs = OrderItem.objects.annotate(
        has_mon=Exists(has_mon),
        has_paint=Exists(has_paint),
        has_pack=Exists(has_pack),
        has_unfinished=Exists(has_unfinished),
        has_any=Exists(has_any),
    ).filter(
        has_mon=True,
        has_paint=False,
        has_pack=False,
    ).filter(
        Q(has_unfinished=True) | Q(has_any=False)
    ).distinct().select_related('order', 'product', 'order__customer')

    if search:
        qs = qs.filter(
            Q(order__id__icontains=search) |
            Q(product__name__icontains=search) |
            Q(order__customer__name__icontains=search) |
            Q(order__number__icontains=search)
        )
    if process_id:
        qs = qs.filter(paint_tasks__painting_stage__process_id=process_id).distinct()
    return qs


def get_unscheduled_ready_items(search=None, process_id=None):
    ready = get_painting_ready_items_queryset(search, process_id)
    has_scheduled = ProductionTask.objects.filter(
        order_item=OuterRef('pk'),
        station_name='paint',
        scheduled_start__isnull=False
    )
    return ready.annotate(_has_scheduled=Exists(has_scheduled)).filter(_has_scheduled=False)


def get_item_paint_preview(item):
    assignments = get_item_color_assignments(item)
    result = {
        'item_id': item.id,
        'color_codes': [f"{p}:{c}" for p, c in assignments],
        'processes': [],
        'unmatched_codes': [],
        'already_has_tasks': item.paint_tasks.filter(station_name='paint').exists(),
        'total_minutes': 0,
        'ok': True,
        'reason': None,
    }
    if not assignments:
        result['ok'] = False
        result['reason'] = 'no_color'
        return result

    for part_name, code in assignments:
        process = get_painting_process_for_color(code)
        if not process:
            result['unmatched_codes'].append(f"{part_name}:{code}")
            continue
        stages = process.stages.all()
        total = sum(s.duration_minutes for s in stages)
        result['processes'].append({
            'part': part_name,
            'color_code': code,
            'process_name': process.name,
            'stage_count': stages.count(),
            'total_minutes': total,
        })
        result['total_minutes'] += total

    if not result['processes']:
        result['ok'] = False
        result['reason'] = 'no_process_match'
    return result


def painting_nav_context():
    return {
        'today': jdatetime.date.today().strftime('%Y/%m/%d'),
        'unscheduled_ready_count': get_unscheduled_ready_items().count(),
    }


# ===================================================================
#   موتور زمان‌بندی نقاشی (Scheduler)
# ===================================================================

def _worker_day_bounds(gregorian_date):
    from datetime import datetime, time
    return {
        'start': timezone.make_aware(datetime.combine(gregorian_date, time(8, 0))),
        'end': timezone.make_aware(datetime.combine(gregorian_date, time(16, 30))),
        'break_start': timezone.make_aware(datetime.combine(gregorian_date, time(12, 30))),
        'break_end': timezone.make_aware(datetime.combine(gregorian_date, time(13, 30))),
    }


class PaintingScheduler:
    """
    موتور زمان‌بندی نقاشی با قابلیت:
    - بارگذاری یک‌باره تسک‌ها و کارگران (با رفرش اجباری کش کارگران)
    - زمان‌بندی در حافظه با پر کردن شکاف‌ها، با بررسی مجدد تداخل بعد از
      عبور از ساعت استراحت (رفع باگ double-booking)
    - قفل ردیف‌ها (select_for_update) هم روی تسک‌های در حال زمان‌بندی و
      هم روی تسک‌های از قبل زمان‌بندی‌شده‌ی همان روز، همه در یک تراکنش
      atomic واحد، تا دو اجرای همزمان روی یک روز واقعاً سریالایز بشن
      (نه فقط لحظه‌ی ذخیره، بلکه از لحظه‌ی خواندن)
    - ذخیره‌سازی یکجا با bulk_update روی یک لیست صریح (نه queryset)
    - رعایت استراحت و پایان روز
    - پشتیبانی از مهارت کارگر
    """

    MAX_GAP_ITERATIONS = 200

    def __init__(self, task_ids, target_date):
        self.task_ids = task_ids
        self.target_date = target_date if isinstance(target_date, jdatetime.date) else jdatetime.date.today()
        self.tasks = []
        self.workers = []
        self.schedule = {}  # worker_id -> list of (start, end, task_or_None)
        self._loaded = False

    def _load(self, lock=False):
        task_qs = ProductionTask.objects.filter(
            id__in=self.task_ids,
            station_name='paint',
            status__in=['pending', 'waiting'],
            scheduled_start__isnull=True,
        ).select_related('painting_stage', 'order_item').order_by('order_item_id', 'step_order')

        gregorian = self.target_date.togregorian()
        existing_qs = ProductionTask.objects.filter(
            station_name='paint',
            scheduled_start__date=gregorian,
            scheduled_start__isnull=False,
        )

        if lock:
            # قفل کردن هر دو دسته‌ی تسک، تا اجرای همزمان دیگری برای همین
            # روز مجبور بشه منتظر بمونه تا این تراکنش کامل بشه.
            task_qs = task_qs.select_for_update()
            existing_qs = existing_qs.select_for_update()

        self.tasks = list(task_qs)
        self.workers = _get_worker_cache(force_refresh=True)
        for w in self.workers:
            self.schedule[w['user_id']] = []

        existing = existing_qs.values('assigned_worker_id', 'scheduled_start', 'scheduled_end')
        for e in existing:
            wid = e['assigned_worker_id']
            if wid in self.schedule:
                self.schedule[wid].append((e['scheduled_start'], e['scheduled_end'], None))

        for wid in self.schedule:
            self.schedule[wid].sort(key=lambda x: x[0])

        self._loaded = True
        logger.info(f"بارگذاری {len(self.tasks)} تسک و {len(self.workers)} کارگر برای {self.target_date}")

    def _find_gap(self, worker_id, duration, bounds, item_ready=None):
        """
        پیدا کردن اولین شکاف خالی در برنامه‌ی کارگر که:
        - داخل ساعت کاری باشه
        - از ساعت استراحت عبور نکنه
        - با هیچ بازه‌ی موجودی (حتی بعد از عبور از استراحت) تداخل نداشته باشه
        """
        if worker_id not in self.schedule:
            return None

        intervals = self.schedule[worker_id]
        candidate = bounds['start']
        if item_ready and item_ready > candidate:
            candidate = item_ready

        for _ in range(self.MAX_GAP_ITERATIONS):
            if candidate < bounds['start']:
                candidate = bounds['start']
            if candidate >= bounds['end']:
                return None

            # عبور از ساعت استراحت
            if bounds['break_start'] <= candidate < bounds['break_end']:
                candidate = bounds['break_end']
                continue

            proposed_end = candidate + timedelta(minutes=duration)

            # اگر تسک از وسط استراحت رد می‌شه، شروع رو به بعد از استراحت منتقل کن
            if candidate < bounds['break_start'] and proposed_end > bounds['break_start']:
                candidate = bounds['break_end']
                continue

            if proposed_end > bounds['end']:
                return None

            # حالا که candidate نهایی شد، با تمام بازه‌های موجود چک کن
            conflict_end = None
            for start, end, _ in intervals:
                if proposed_end <= start or candidate >= end:
                    continue
                conflict_end = end
                break

            if conflict_end is None:
                return candidate

            # تداخل پیدا شد؛ برو بعد از بازه‌ی مزاحم و دوباره تلاش کن
            candidate = conflict_end

        logger.warning(f"عدم همگرایی جستجوی شکاف برای کارگر {worker_id}")
        return None

    def _select_worker(self, task, bounds, item_ready):
        """انتخاب بهترین کارگر برای تسک (با رعایت مهارت و کمترین زمان شروع)"""
        skill = task.painting_stage.required_skill if task.painting_stage else 'painter'
        duration = task.painting_stage.duration_minutes if task.painting_stage else 60

        candidates = []
        for w in self.workers:
            if skill not in (w.get('skills') or []) and skill != 'painter':
                continue
            slot = self._find_gap(w['user_id'], duration, bounds, item_ready)
            if slot is not None:
                candidates.append((w['user_id'], slot))

        if not candidates:
            return None, None

        candidates.sort(key=lambda x: x[1])
        return candidates[0][0], candidates[0][1]

    def build(self):
        """ساخت برنامه زمان‌بندی در حافظه"""
        if not self._loaded:
            self._load()
        if not self.tasks or not self.workers:
            return 0

        gregorian = self.target_date.togregorian()
        bounds = _worker_day_bounds(gregorian)
        item_cursors = {}
        scheduled = 0

        for task in self.tasks:
            duration = task.painting_stage.duration_minutes if task.painting_stage else 60
            drying = task.painting_stage.drying_time_minutes if task.painting_stage else 0
            item_ready = item_cursors.get(task.order_item_id)

            wid, start = self._select_worker(task, bounds, item_ready)
            if wid is None:
                continue

            end = start + timedelta(minutes=duration)

            self.schedule[wid].append((start, end, task))
            self.schedule[wid].sort(key=lambda x: x[0])

            task._assigned_worker_id = wid
            task._scheduled_start = start
            task._scheduled_end = end

            item_cursors[task.order_item_id] = end + timedelta(minutes=drying)
            scheduled += 1

        logger.info(f"{scheduled} تسک از {len(self.tasks)} زمان‌بندی شد.")
        return scheduled

    def apply(self):
        """
        اعمال تغییرات در دیتابیس. اگر تسک‌های self.tasks از قبل با
        select_for_update قفل شده باشن (یعنی از طریق run() صدا زده شده)،
        همون آبجکت‌های قفل‌شده مستقیماً آپدیت می‌شن؛ در غیر این صورت
        یک قفل مستقل و مقطعی فقط روی همین تسک‌ها گرفته می‌شه (سازگاری
        با کدهای قدیمی که مستقیماً apply() را صدا می‌زنند).
        """
        if not self._loaded:
            self._load()

        tasks_to_update = [t for t in self.tasks if hasattr(t, '_assigned_worker_id')]
        if not tasks_to_update:
            return 0

        def _write(objs):
            for task in objs:
                task.assigned_worker_id = getattr(task, '_assigned_worker_id', None)
                task.scheduled_start = getattr(task, '_scheduled_start', None)
                task.scheduled_end = getattr(task, '_scheduled_end', None)
            ProductionTask.objects.bulk_update(
                objs, ['assigned_worker_id', 'scheduled_start', 'scheduled_end']
            )

        if transaction.get_connection().in_atomic_block:
            # از قبل داخل تراکنش (معمولاً از طریق run())؛ آبجکت‌های فعلی
            # همان‌هایی هستن که قفل شدن، دوباره کوئری نمی‌گیریم.
            _write(tasks_to_update)
        else:
            with transaction.atomic():
                ids = [t.id for t in tasks_to_update]
                locked = list(ProductionTask.objects.select_for_update().filter(id__in=ids))
                locked_by_id = {t.id: t for t in locked}
                for t in tasks_to_update:
                    locked_obj = locked_by_id[t.id]
                    locked_obj._assigned_worker_id = t._assigned_worker_id
                    locked_obj._scheduled_start = t._scheduled_start
                    locked_obj._scheduled_end = t._scheduled_end
                _write(locked)

        logger.info(f"{len(tasks_to_update)} تسک در دیتابیس به‌روزرسانی شد.")
        return len(tasks_to_update)

    def run(self):
        """
        نقطه‌ی ورود توصیه‌شده: بارگذاری + ساخت برنامه + ذخیره، همه داخل
        یک تراکنش atomic واحد با قفل روی تسک‌های مرتبط، تا اجرای همزمان
        این کلاس برای یک روز/کارگر مشترک واقعاً سریالایز بشه.
        """
        with transaction.atomic():
            self._load(lock=True)
            scheduled = self.build()
            applied = self.apply()
        return scheduled, applied


# ===================================================================
#   توابع عمومی زمان‌بندی (با استفاده از Scheduler)
# ===================================================================

def schedule_paint_tasks_for_items(item_ids, target_date):
    task_ids = list(
        ProductionTask.objects.filter(
            order_item_id__in=item_ids,
            station_name='paint',
            status__in=['pending', 'waiting'],
            scheduled_start__isnull=True,
        ).values_list('id', flat=True)
    )
    if not task_ids:
        return 0
    sched = PaintingScheduler(task_ids, target_date)
    cnt, _ = sched.run()
    return cnt


def schedule_paint_items_auto(item_ids, start_date=None):
    if start_date is None:
        start_date = jdatetime.date.today()

    remaining = list(
        ProductionTask.objects.filter(
            order_item_id__in=item_ids,
            station_name='paint',
            status__in=['pending', 'waiting'],
            scheduled_start__isnull=True,
        ).values_list('id', flat=True)
    )

    if not remaining:
        return 0, None

    total = 0
    cur_date = start_date
    safety = 0
    while remaining and safety < 30:
        sched = PaintingScheduler(remaining, cur_date)
        cnt, _ = sched.run()
        total += cnt

        remaining = list(
            ProductionTask.objects.filter(
                id__in=remaining,
                station_name='paint',
                status__in=['pending', 'waiting'],
                scheduled_start__isnull=True,
            ).values_list('id', flat=True)
        )
        cur_date += jdatetime.timedelta(days=1)
        safety += 1

    return total, cur_date - jdatetime.timedelta(days=1)


def auto_assign_paint_tasks(target_date=None):
    if target_date is None:
        target_date = jdatetime.date.today()

    task_ids = list(
        ProductionTask.objects.filter(
            station_name='paint',
            part__isnull=True,
            assigned_worker__isnull=True,
            status__in=['pending', 'waiting'],
            scheduled_start__isnull=True,
        ).values_list('id', flat=True)
    )
    if not task_ids:
        return 0
    sched = PaintingScheduler(task_ids, target_date)
    cnt, _ = sched.run()
    return cnt


def create_and_schedule_items_for_date(item_ids, target_date=None):
    items = OrderItem.objects.filter(pk__in=item_ids).prefetch_related('ordercolor', 'paint_tasks')
    created_items = []
    skipped = []
    new_tasks = []

    for item in items:
        if item.paint_tasks.filter(station_name='paint').exists():
            continue
        assignments = get_item_color_assignments(item)
        if not assignments:
            skipped.append({'item_id': item.id, 'reason': 'no_color'})
            continue
        base_step = 0
        any_created = False
        for part_name, color_code in assignments:
            process = get_painting_process_for_color(color_code)
            if not process:
                continue
            create_paint_tasks(
                tasks_list=new_tasks,
                order=item.order,
                quantity=item.quantity,
                process=process,
                base_step=base_step,
                order_item=item,
                color_part=part_name,
            )
            base_step += process.stages.count()
            any_created = True
        if any_created:
            created_items.append(item.id)
        else:
            skipped.append({'item_id': item.id, 'reason': 'no_process_match'})

    if new_tasks:
        ProductionTask.objects.bulk_create(new_tasks)

    if target_date:
        cnt = schedule_paint_tasks_for_items(item_ids, target_date)
        return {'scheduled_count': cnt, 'scheduled_date': target_date, 'created_items': created_items, 'skipped': skipped}
    else:
        cnt, date = schedule_paint_items_auto(item_ids)
        return {'scheduled_count': cnt, 'scheduled_date': date, 'created_items': created_items, 'skipped': skipped}


def repaint_item_ids_for_date(item_ids, target_date):
    items = OrderItem.objects.filter(pk__in=item_ids)
    task_ids = []
    for item in items:
        task_ids.extend(
            ProductionTask.objects.filter(
                order_item=item,
                station_name='paint',
                scheduled_start__date=target_date.togregorian(),
            ).values_list('pk', flat=True)
        )
    if task_ids:
        done = ProductionTask.objects.filter(pk__in=task_ids, status='done').count()
        if done:
            raise ValueError(f'{done} تسک قبلاً انجام شده و نمی‌تواند بازنشانی شود.')
        ProductionTask.objects.filter(pk__in=task_ids).delete()
    return create_and_schedule_items_for_date(item_ids, target_date)