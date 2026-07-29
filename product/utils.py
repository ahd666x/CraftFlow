# product/utils.py - اضافه کردن تابع assign_task_to_worker برای درگ‌اند‌دراپ

import re
import json
import logging
import traceback
from datetime import datetime, time, timedelta
from collections import defaultdict

import jdatetime
from django.db import transaction
from django.db.models import Exists, OuterRef, Prefetch, Q, Max
from django.contrib.auth.models import User
from django.utils import timezone

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
#   کش‌های سراسری
# ===================================================================
_PAINT_PROCESS_CACHE = None
_PAINT_WORKER_CACHE = None


def invalidate_caches():
    global _PAINT_PROCESS_CACHE, _PAINT_WORKER_CACHE
    _PAINT_PROCESS_CACHE = None
    _PAINT_WORKER_CACHE = None
    logger.info("کش‌های نقاشی پاک شدند.")


def _get_process_cache():
    global _PAINT_PROCESS_CACHE
    if _PAINT_PROCESS_CACHE is None:
        _PAINT_PROCESS_CACHE = {}
        for p in PaintingProcess.objects.filter(is_active=True).prefetch_related('stages'):
            for code in (p.color_codes or []):
                _PAINT_PROCESS_CACHE[str(code)] = p
    return _PAINT_PROCESS_CACHE


def _get_worker_cache():
    global _PAINT_WORKER_CACHE
    if _PAINT_WORKER_CACHE is None:
        try:
            _PAINT_WORKER_CACHE = []
            workers_qs = WorkerProfile.objects.filter(
                stage='paint',
                is_available=True
            ).select_related('user')
            for w in workers_qs:
                user = w.user
                _PAINT_WORKER_CACHE.append({
                    'user_id': user.id,
                    'skills': list(w.skills) if isinstance(w.skills, list) else [],
                    'full_name': f"{user.first_name} {user.last_name}".strip() or user.username,
                })
            logger.debug(f"کش کارگران: {len(_PAINT_WORKER_CACHE)} کارگر بارگذاری شد.")
        except Exception as e:
            logger.error(f"خطا در بارگذاری کش کارگران: {e}\n{traceback.format_exc()}")
            _PAINT_WORKER_CACHE = []
    return _PAINT_WORKER_CACHE if isinstance(_PAINT_WORKER_CACHE, list) else []


# ===================================================================
#   جایگزین امن برای eval
# ===================================================================
def _safe_eval(expr, allowed_names):
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
    name = mapping.get(color_code) if mapping else default_map.get(str(color_code))
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
    except (ValueError, TypeError) as e:
        raise ValueError(f"تاریخ نامعتبر: {date_str}") from e


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
            Q(order__number__icontains=search) |
            Q(order__user__username__icontains=search) |
            Q(order__user__first_name__icontains=search) |
            Q(order__user__last_name__icontains=search)
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
    """مرزهای یک روز کاری (۸:۰۰ تا ۱۶:۳۰ با استراحت ۱۲:۳۰–۱۳:۳۰)"""
    return {
        'start': timezone.make_aware(datetime.combine(gregorian_date, time(8, 0))),
        'end': timezone.make_aware(datetime.combine(gregorian_date, time(16, 30))),
        'break_start': timezone.make_aware(datetime.combine(gregorian_date, time(12, 30))),
        'break_end': timezone.make_aware(datetime.combine(gregorian_date, time(13, 30))),
    }


class PaintingScheduler:
    def __init__(self, task_ids, target_date, initial_item_cursors=None):
        self.task_ids = list(task_ids) if task_ids else []
        self.target_date = target_date if isinstance(target_date, jdatetime.date) else jdatetime.date.today()
        self.tasks = []
        self.workers = []
        self.worker_schedule = {}
        self.worker_load = {}
        self._loaded = False
        self._all_day_tasks = []
        self.initial_item_cursors = initial_item_cursors or {}

        # تاریخچهٔ کارگر-به-ازای-سفارش
        self._order_worker_history = defaultdict(set)

        # کش استثناهای محصولات (کارگرهای ممنوع)
        self._exclusion_map = {}

        # کش آیتم‌های ممنوعه برای هر کارگر
        self._excluded_items_map = {}

        # ردیابی کارگران تخصیص‌یافته به هر آیتم
        self._item_workers = defaultdict(set)

    def _load(self):
        try:
            logger.debug(f"_load شروع شد برای {self.target_date}")
            gregorian = self.target_date.togregorian()
            bounds = _worker_day_bounds(gregorian)

            self._all_day_tasks = list(
                ProductionTask.objects.filter(
                    station_name='paint',
                    scheduled_start__date=gregorian,
                    scheduled_start__isnull=False,
                )
            )
            logger.debug(f"{len(self._all_day_tasks)} تسک موجود در این روز پیدا شد.")

            if self.task_ids:
                self.tasks = list(
                    ProductionTask.objects.filter(
                        id__in=self.task_ids,
                        station_name='paint',
                        status__in=['pending', 'waiting'],
                        scheduled_start__isnull=True,
                    ).select_related('painting_stage', 'order_item')
                    .order_by('order_item_id', 'step_order')
                )
            else:
                self.tasks = []
            logger.debug(f"{len(self.tasks)} تسک جدید برای زمان‌بندی بارگذاری شد.")

            workers_data = _get_worker_cache()
            if not isinstance(workers_data, list):
                logger.error(f"_get_worker_cache لیست برنگرداند: {type(workers_data)}")
                workers_data = []
            self.workers = [w for w in workers_data if isinstance(w, dict) and 'user_id' in w]
            logger.debug(f"{len(self.workers)} کارگر بارگذاری شدند.")

            self.worker_schedule = {}
            self.worker_load = {}
            for w in self.workers:
                wid = w.get('user_id')
                if wid is not None:
                    self.worker_schedule[wid] = []
                    self.worker_load[wid] = 0

            # افزودن بلوک ناهار
            for wid in self.worker_schedule:
                self.worker_schedule[wid].append(
                    (bounds['break_start'], bounds['break_end'], None)
                )

            # پر کردن برنامه از تسک‌های موجود
            for task in self._all_day_tasks:
                wid = task.assigned_worker_id
                if wid in self.worker_schedule:
                    self.worker_schedule[wid].append((task.scheduled_start, task.scheduled_end, task))
                    duration = int((task.scheduled_end - task.scheduled_start).total_seconds() / 60)
                    self.worker_load[wid] = self.worker_load.get(wid, 0) + duration

            for wid in self.worker_schedule:
                self.worker_schedule[wid].sort(key=lambda x: x[0])

            # تاریخچهٔ کارگر-به-ازای-سفارش
            order_ids = {t.order_id for t in self.tasks if t.order_id is not None}
            if order_ids:
                history_qs = (
                    ProductionTask.objects
                    .filter(
                        order_id__in=order_ids,
                        station_name='paint',
                        assigned_worker__isnull=False,
                    )
                    .values_list('order_id', 'assigned_worker_id')
                    .distinct()
                )
                for order_id, worker_id in history_qs:
                    self._order_worker_history[order_id].add(worker_id)

            # پیش‌بارگذاری استثناهای محصولات
            worker_ids = [w['user_id'] for w in self.workers if w.get('user_id')]
            if worker_ids:
                profiles = WorkerProfile.objects.filter(
                    user_id__in=worker_ids
                ).prefetch_related('excluded_products')
                for profile in profiles:
                    excluded_ids = set(profile.excluded_products.values_list('id', flat=True))
                    self._exclusion_map[profile.user_id] = excluded_ids

            # پر کردن _excluded_items_map
            for w_id in worker_ids:
                profile = WorkerProfile.objects.filter(user_id=w_id).first()
                if profile:
                    self._excluded_items_map[w_id] = set(
                        profile.excluded_items.values_list('id', flat=True)
                    )
                else:
                    self._excluded_items_map[w_id] = set()

            # NEW: پر کردن _item_workers از تسک‌های موجود در دیتابیس
            # تسک‌های نقاشی که قبلاً worker دارند (فارغ از روز)
            existing_item_workers = (
                ProductionTask.objects
                .filter(
                    order_item__isnull=False,
                    station_name='paint',
                    assigned_worker__isnull=False,
                )
                .values_list('order_item_id', 'assigned_worker_id')
            )
            for item_id, wid in existing_item_workers:
                if item_id and wid:
                    self._item_workers[item_id].add(wid)

            self._loaded = True
            logger.info(f"بارگذاری کامل شد: {len(self.tasks)} تسک جدید، {len(self._all_day_tasks)} تسک موجود")

        except Exception as e:
            logger.error(f"خطا در _load: {e}\n{traceback.format_exc()}")
            raise

    def _is_task_excluded_for_worker(self, worker_id, product_id, order_item_id):
        """بررسی ممنوعیت کارگر برای محصول یا آیتم خاص"""
        if product_id and product_id in self._exclusion_map.get(worker_id, set()):
            return True
        if order_item_id and order_item_id in self._excluded_items_map.get(worker_id, set()):
            return True
        return False

    def _find_gap(self, worker_id, duration, bounds, item_ready=None, prefer_early=False):
        if worker_id not in self.worker_schedule:
            return None

        intervals = sorted(self.worker_schedule[worker_id], key=lambda x: x[0])
        candidate = bounds['start']
        if item_ready and item_ready > candidate:
            candidate = item_ready

        best_start = None
        best_gap = timedelta.max

        for start, end, _ in intervals:
            if end <= candidate:
                continue
            if start > candidate:
                gap = start - candidate
                if gap >= timedelta(minutes=duration):
                    if prefer_early:
                        return candidate
                    if gap < best_gap:
                        best_gap = gap
                        best_start = candidate
                    if gap == timedelta(minutes=duration):
                        return candidate
            if end > candidate:
                candidate = end

        if bounds['end'] - candidate >= timedelta(minutes=duration):
            if prefer_early or best_start is None:
                return candidate
            if bounds['end'] - candidate < best_gap:
                best_start = candidate
            return best_start

        return best_start

    def _get_gap_size(self, worker_id, start, bounds):
        if worker_id not in self.worker_schedule:
            return None
        intervals = sorted(self.worker_schedule[worker_id], key=lambda x: x[0])
        for s, e, _ in intervals:
            if s > start:
                return int((s - start).total_seconds() / 60)
        return int((bounds['end'] - start).total_seconds() / 60)

    def _get_worker_load(self, worker_id):
        if worker_id not in self.worker_load:
            total = 0
            for start, end, task in self.worker_schedule.get(worker_id, []):
                if task is not None and start and end:
                    total += int((end - start).total_seconds() / 60)
            self.worker_load[worker_id] = total
        return self.worker_load.get(worker_id, 0)

    def _select_worker(self, task, bounds, item_ready, preferred_worker_id=None):
        try:
            skill = task.painting_stage.required_skill if task.painting_stage else 'painter'
            duration = task.painting_stage.duration_minutes if task.painting_stage else 60
            is_short_task = duration <= 30

            # FIX: تعریف product_id در ابتدا
            product = task.order_item.product if task.order_item and task.order_item.product else None
            product_id = product.id if product else None

            candidates = []

            if preferred_worker_id is not None:
                for w in self.workers:
                    if w.get('user_id') == preferred_worker_id:
                        if skill in (w.get('skills') or []):
                            if allowed_workers and preferred_worker_id not in allowed_workers:
                                break
                            if not self._is_task_excluded_for_worker(preferred_worker_id, product_id, task.order_item_id):
                                slot = self._find_gap(preferred_worker_id, duration, bounds, item_ready, prefer_early=is_short_task)
                                if slot is not None:
                                    return preferred_worker_id, slot
                        break

            for w in self.workers:
                wid = w.get('user_id')
                if wid is None:
                    continue
                if skill not in (w.get('skills') or []):
                    continue

                if self._is_task_excluded_for_worker(wid, product_id, task.order_item_id):
                    continue

                slot = self._find_gap(wid, duration, bounds, item_ready, prefer_early=is_short_task)
                if slot is None:
                    continue

                load = self._get_worker_load(wid)
                score = (slot - bounds['start']).total_seconds() / 60 + load * 5

                existing_worker_ids = self._order_worker_history.get(task.order_id, set())
                if wid in existing_worker_ids:
                    score -= 200

                if is_short_task:
                    gap_size = self._get_gap_size(wid, slot, bounds)
                    if gap_size and gap_size <= duration * 2:
                        score -= 40

                candidates.append((score, wid, slot))

            if not candidates:
                return None, None

            candidates.sort(key=lambda x: x[0])
            return candidates[0][1], candidates[0][2]

        except Exception as e:
            logger.error(f"خطا در _select_worker: {e}\n{traceback.format_exc()}")
            raise

    def _assign_task(self, task, worker_id, start, bounds):
        try:
            duration = task.painting_stage.duration_minutes if task.painting_stage else 60
            drying = task.painting_stage.drying_time_minutes if task.painting_stage else 0
            end = start + timedelta(minutes=duration)

            if worker_id not in self.worker_schedule:
                self.worker_schedule[worker_id] = []
            self.worker_schedule[worker_id].append((start, end, task))
            self.worker_schedule[worker_id].sort(key=lambda x: x[0])
            if task is not None:
                self.worker_load[worker_id] = self.worker_load.get(worker_id, 0) + duration

            task._assigned_worker_id = worker_id
            task._scheduled_start = start
            task._scheduled_end = end

            if task.order_id is not None:
                self._order_worker_history[task.order_id].add(worker_id)

            # NEW: بروزرسانی _item_workers در حافظه
            if task.order_item_id:
                self._item_workers[task.order_item_id].add(worker_id)

            return end + timedelta(minutes=drying)

        except Exception as e:
            logger.error(f"خطا در _assign_task برای task {task.id}: {e}\n{traceback.format_exc()}")
            raise

    def build(self):
        try:
            if not self._loaded:
                self._load()

            if not self.tasks or not self.workers:
                return 0

            gregorian = self.target_date.togregorian()
            bounds = _worker_day_bounds(gregorian)

            self.tasks.sort(key=lambda t: (t.order_item_id, t.step_order))

            scheduled = 0
            item_cursors = dict(self.initial_item_cursors)

            for task in self.tasks:
                duration = task.painting_stage.duration_minutes if task.painting_stage else 60
                drying = task.painting_stage.drying_time_minutes if task.painting_stage else 0

                cursor_key = (task.order_item_id, task.color_part)
                item_ready = item_cursors.get(cursor_key)

                wid, start = self._select_worker(task, bounds, item_ready, preferred_worker_id=None)
                if wid is None:
                    continue

                next_ready = self._assign_task(task, wid, start, bounds)
                item_cursors[cursor_key] = next_ready
                scheduled += 1

            self._remaining_item_cursors = item_cursors

            logger.info(f"{scheduled} تسک از {len(self.tasks)} زمان‌بندی شد.")
            return scheduled

        except Exception as e:
            logger.error(f"خطا در build: {e}\n{traceback.format_exc()}")
            raise

    def apply(self):
        try:
            tasks_to_update = [t for t in self.tasks if hasattr(t, '_assigned_worker_id')]
            if not tasks_to_update:
                return 0

            for task in tasks_to_update:
                task.assigned_worker_id = getattr(task, '_assigned_worker_id', None)
                task.scheduled_start = getattr(task, '_scheduled_start', None)
                task.scheduled_end = getattr(task, '_scheduled_end', None)

            ProductionTask.objects.bulk_update(
                tasks_to_update,
                ['assigned_worker_id', 'scheduled_start', 'scheduled_end']
            )

            logger.info(f"{len(tasks_to_update)} تسک در دیتابیس به‌روزرسانی شد.")
            return len(tasks_to_update)

        except Exception as e:
            logger.error(f"خطا در apply: {e}\n{traceback.format_exc()}")
            raise

    def schedule(self):
        try:
            logger.info(f"شروع schedule برای {self.target_date} با {len(self.task_ids)} تسک")
            self._load()
            count = self.build()
            self.apply()
            logger.info(f"زمان‌بندی کامل شد: {count} تسک")
            return count, getattr(self, '_remaining_item_cursors', {})
        except Exception as e:
            logger.error(f"خطا در schedule: {e}\n{traceback.format_exc()}")
            raise


# ===================================================================
#   توابع عمومی زمان‌بندی
# ===================================================================

def _get_initial_item_cursors(item_ids):
    cursors = {}

    parts = (
        ProductionTask.objects
        .filter(order_item_id__in=item_ids, station_name='paint')
        .values_list('order_item_id', 'color_part')
        .distinct()
    )

    for item_id, color_part in parts:
        last_task = ProductionTask.objects.filter(
            order_item_id=item_id,
            color_part=color_part,
            station_name='paint',
            scheduled_end__isnull=False,
        ).order_by('-scheduled_end').first()

        if last_task:
            drying = last_task.painting_stage.drying_time_minutes if last_task.painting_stage else 0
            cursors[(item_id, color_part)] = last_task.scheduled_end + timedelta(minutes=drying)
        else:
            cursors[(item_id, color_part)] = None

    return cursors


def schedule_paint_tasks_for_items(item_ids, target_date, initial_item_cursors=None):
    if not item_ids:
        return 0, {}
    task_ids = list(
        ProductionTask.objects.filter(
            order_item_id__in=item_ids,
            station_name='paint',
            status__in=['pending', 'waiting'],
            scheduled_start__isnull=True,
        ).values_list('id', flat=True)
    )
    if not task_ids:
        return 0, {}

    sched = PaintingScheduler(task_ids, target_date, initial_item_cursors)
    if not isinstance(sched, PaintingScheduler):
        logger.error(f"خطا: sched از نوع {type(sched)} است، انتظار PaintingScheduler داشتیم.")
        raise TypeError(f"sched باید از نوع PaintingScheduler باشد، اما {type(sched)} دریافت شد.")

    return sched.schedule()


def schedule_paint_items_auto(item_ids, start_date=None, max_days=100, initial_item_cursors=None):
    if not item_ids:
        return 0, None, {}
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
        return 0, None, {}

    if initial_item_cursors is None:
        initial_item_cursors = _get_initial_item_cursors(item_ids)

    total = 0
    cur_date = start_date
    safety = 0
    item_cursors = dict(initial_item_cursors)

    while remaining and safety < max_days:
        sched = PaintingScheduler(remaining, cur_date, item_cursors)
        cnt, new_cursors = sched.schedule()
        total += cnt
        item_cursors.update(new_cursors)

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

    if remaining:
        logger.warning(f"{len(remaining)} تسک پس از {max_days} روز همچنان زمان‌بندی نشده‌اند.")

    return total, cur_date - jdatetime.timedelta(days=1), item_cursors


def auto_assign_paint_tasks(target_date=None):
    if target_date is None:
        target_date = jdatetime.date.today()

    tasks_qs = ProductionTask.objects.filter(
        station_name='paint',
        assigned_worker__isnull=True,
        status__in=['pending', 'waiting'],
        order_item__isnull=False,
        painting_stage__isnull=False,
    )
    if target_date:
        gregorian = target_date.togregorian()
        tasks_qs = tasks_qs.filter(
            Q(scheduled_start__isnull=True) | Q(scheduled_start__date=gregorian)
        )

    task_ids = list(tasks_qs.values_list('id', flat=True))
    if not task_ids:
        return 0

    item_ids = list(tasks_qs.values_list('order_item_id', flat=True).distinct())
    initial_cursors = _get_initial_item_cursors(item_ids)

    sched = PaintingScheduler(task_ids, target_date, initial_cursors)
    cnt, _ = sched.schedule()
    return cnt


def create_and_schedule_items_for_date(item_ids, target_date=None):
    try:
        if target_date is None:
            target_date = jdatetime.date.today()
            logger.info("target_date None بود، تاریخ امروز جایگزین شد.")

        if not isinstance(target_date, jdatetime.date):
            logger.error(f"target_date از نوع {type(target_date)} است. جایگزین با امروز.")
            target_date = jdatetime.date.today()

        # ایجاد تسک‌های جدید
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

        # زمان‌بندی همه تسک‌ها
        all_item_ids = list(
            ProductionTask.objects.filter(
                order_item_id__in=item_ids,
                station_name='paint',
                status__in=['pending', 'waiting'],
                scheduled_start__isnull=True,
            ).values_list('order_item_id', flat=True).distinct()
        )

        if not all_item_ids:
            return {
                'scheduled_count': 0,
                'scheduled_date': target_date,
                'created_items': created_items,
                'skipped': skipped
            }

        initial_cursors = _get_initial_item_cursors(all_item_ids)

        cnt, last_date, _ = schedule_paint_items_auto(
            all_item_ids, target_date, max_days=100, initial_item_cursors=initial_cursors
        )

        return {
            'scheduled_count': cnt,
            'scheduled_date': last_date or target_date,
            'created_items': created_items,
            'skipped': skipped
        }

    except Exception as e:
        logger.error(f"خطا در create_and_schedule_items_for_date: {e}\n{traceback.format_exc()}")
        raise


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


# ===================================================================
#   تابع اختصاصی برای درگ‌اند‌دراپ (تخصیص دستی کارگر به تسک)
# ===================================================================

def assign_task_to_worker(task_id, worker_id):
    """
    تخصیص دستی یک تسک نقاشی به یک کارگر خاص (برای درگ‌اند‌دراپ در کانبان).

    پارامترها:
        task_id: شناسه تسک نقاشی
        worker_id: شناسه کاربر کارگر

    خروجی:
        dict: {'ok': True/False, 'error': str (در صورت خطا)}
              در صورت موفقیت:
              {'ok': True, 'scheduled_start': '08:30', 'scheduled_end': '09:15'}
    """
    try:
        # ۱. دریافت تسک
        task = ProductionTask.objects.select_related(
            'painting_stage', 'order_item', 'order_item__product'
        ).filter(
            pk=task_id,
            station_name='paint'
        ).first()

        if not task:
            return {'ok': False, 'error': 'تسک یافت نشد'}

        if task.status == 'done':
            return {'ok': False, 'error': 'این تسک قبلاً انجام شده است'}

        # ۲. دریافت کارگر مقصد از کش کارگران فعال
        workers = _get_worker_cache()
        worker_data = next((w for w in workers if w['user_id'] == int(worker_id)), None)

        if not worker_data:
            return {'ok': False, 'error': 'کارگر یافت نشد یا غیرفعال است'}

        # ۳. بررسی مهارت
        required_skill = task.painting_stage.required_skill if task.painting_stage else 'painter'
        if required_skill not in (worker_data.get('skills') or []):
            return {
                'ok': False,
                'error': f'کارگر مهارت "{required_skill}" را ندارد. مهارت‌های فعلی: {", ".join(worker_data.get("skills") or [])}'
            }

        # ۴. بررسی استثناهای محصول
        product = task.order_item.product if task.order_item and task.order_item.product else None
        if product:
            worker_profile = WorkerProfile.objects.filter(user_id=worker_id).first()
            if worker_profile and worker_profile.excluded_products.filter(id=product.id).exists():
                return {'ok': False, 'error': f'این کارگر برای محصول "{product.name}" ممنوع است'}

        # ۴-ب. بررسی ممنوعیت آیتم خاص
        if task.order_item_id:
            worker_profile = WorkerProfile.objects.filter(user_id=worker_id).first()
            if worker_profile and worker_profile.excluded_items.filter(id=task.order_item_id).exists():
                return {
                    'ok': False,
                    'error': f'کارگر برای این آیتم (شماره {task.order_item_id}) ممنوع شده است.'
                }

        # ۶. محاسبه زمان با استفاده از منطق Scheduler
        if task.scheduled_start:
            ref_date = task.scheduled_start.date()
        else:
            ref_date = timezone.localdate()

        bounds = _worker_day_bounds(ref_date)

        # ساختن یک Scheduler موقت برای استفاده از _find_gap
        temp_scheduler = PaintingScheduler([], jdatetime.date.fromgregorian(date=ref_date))
        temp_scheduler._loaded = True
        temp_scheduler.workers = workers
        temp_scheduler.worker_schedule = {}

        # پر کردن worker_schedule با تسک‌های موجود این کارگر در آن روز (به‌غیر از خود تسک)
        existing_tasks = ProductionTask.objects.filter(
            assigned_worker_id=worker_id,
            station_name='paint',
            scheduled_start__date=ref_date,
            scheduled_start__isnull=False,
        ).exclude(pk=task_id)

        temp_scheduler.worker_schedule[worker_id] = []
        for et in existing_tasks:
            temp_scheduler.worker_schedule[worker_id].append(
                (et.scheduled_start, et.scheduled_end, et)
            )
        # اضافه کردن بلوک ناهار
        temp_scheduler.worker_schedule[worker_id].append(
            (bounds['break_start'], bounds['break_end'], None)
        )
        temp_scheduler.worker_schedule[worker_id].sort(key=lambda x: x[0])

        duration = task.painting_stage.duration_minutes if task.painting_stage else 60
        start = temp_scheduler._find_gap(worker_id, duration, bounds, item_ready=None, prefer_early=True)

        if start is None:
            return {'ok': False, 'error': 'کارگر در این روز ظرفیت کافی ندارد'}

        end = start + timedelta(minutes=duration)

        # ۷. ذخیره تغییرات
        task.assigned_worker_id = worker_id
        task.scheduled_start = start
        task.scheduled_end = end
        task.save(update_fields=['assigned_worker_id', 'scheduled_start', 'scheduled_end'])

        return {
            'ok': True,
            'scheduled_start': start.strftime('%H:%M'),
            'scheduled_end': end.strftime('%H:%M'),
        }

    except Exception as e:
        logger.error(f"خطا در assign_task_to_worker: {e}\n{traceback.format_exc()}")
        return {'ok': False, 'error': f'خطای داخلی: {str(e)}'}


# ===================================================================
#   سیگنال‌ها
# ===================================================================
from django.db.models.signals import post_save, post_delete


def _invalidate_on_change(sender, **kwargs):
    invalidate_caches()


post_save.connect(_invalidate_on_change, sender=PaintingProcess)
post_delete.connect(_invalidate_on_change, sender=PaintingProcess)
post_save.connect(_invalidate_on_change, sender=WorkerProfile)
post_delete.connect(_invalidate_on_change, sender=WorkerProfile)