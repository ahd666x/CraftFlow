# product/management/commands/diagnose_unscheduled_paint.py
"""
اسکریپت تشخیص علت عدم زمان‌بندی تسک‌های نقاشی

اجرا:
    python manage.py diagnose_unscheduled_paint [--item-id ITEM_ID] [--order-id ORDER_ID] [--json]
"""

from django.core.management.base import BaseCommand
from django.db.models import Q, Count, Prefetch
import jdatetime
from datetime import timedelta
import json
from collections import defaultdict

from product.models import (
    ProductionTask, OrderItem, PaintingStage, PaintingAssignmentRule,
    WorkerProfile, Order, Color
)
from product.utils import _get_worker_cache, _get_active_assignment_rules, _task_matches_rule


class Command(BaseCommand):
    help = 'تشخیص علت عدم زمان‌بندی تسک‌های نقاشی'

    def add_arguments(self, parser):
        parser.add_argument('--item-id', type=int, help='شناسه آیتم خاص')
        parser.add_argument('--order-id', type=int, help='شناسه سفارش')
        parser.add_argument('--json', action='store_true', help='خروجی JSON')

    def handle(self, *args, **options):
        self.json_output = options.get('json', False)
        item_id = options.get('item_id')
        order_id = options.get('order_id')

        # کپشن کارگران
        self.stdout.write("در حال بارگذاری داده‌ها...")
        workers_data = _get_worker_cache()
        workers_by_id = {w['user_id']: w for w in workers_data}

        profiles = list(
            WorkerProfile.objects.filter(stage='paint', is_available=True)
            .prefetch_related('excluded_products', 'excluded_items')
        )
        profiles_by_id = {p.user_id: p for p in profiles}

        # قوانین فعال
        rules = _get_active_assignment_rules()
        rules_by_worker = defaultdict(list)
        for r in rules:
            rules_by_worker[r.worker.user_id].append(r)

        # تسک‌های بدون زمان‌بندی
        qs = ProductionTask.objects.filter(
            station_name='paint',
            status__in=['pending', 'waiting'],
            scheduled_start__isnull=True,
        ).select_related(
            'order_item__product__category',
            'order_item__order',
            'painting_stage',
            'order_item__product',
        )

        if item_id:
            qs = qs.filter(order_item_id=item_id)
        elif order_id:
            qs = qs.filter(order_id=order_id)

        tasks = list(qs.order_by('order_item_id', 'step_order'))

        # سابقه کارگران روی هر order_item + color_part
        item_existing_workers = defaultdict(set)
        history_qs = ProductionTask.objects.filter(
            station_name='paint',
            order_item_id__in=[t.order_item_id for t in tasks if t.order_item_id],
            assigned_worker__isnull=False,
        ).values_list('order_item_id', 'color_part', 'assigned_worker_id')
        for item_id, color_part, wid in history_qs:
            key = (item_id, color_part or '')
            item_existing_workers[key].add(wid)

        results = []
        for task in tasks:
            result = self._diagnose_task(
                task, workers_data, profiles_by_id, rules, rules_by_worker,
                item_existing_workers, workers_by_id
            )
            results.append(result)

        if self.json_output:
            self.stdout.write(json.dumps(results, ensure_ascii=False, indent=2, default=str))
        else:
            self._print_human_readable(results, tasks)

    def _diagnose_task(self, task, workers_data, profiles_by_id, rules, rules_by_worker,
                       item_existing_workers, workers_by_id):
        result = {
            'task_id': task.id,
            'order_item': f"سفارش {task.order_id} / آیتم {task.order_item_id} - {task.order_item.product.name if task.order_item and task.order_item.product else '-'}",
            'stage': task.painting_stage.name if task.painting_stage else '-',
            'required_skill': task.painting_stage.required_skill if task.painting_stage else 'painter',
            'color_part': task.color_part,
            'duration_minutes': task.painting_stage.duration_minutes if task.painting_stage else None,
            'eligible_workers_by_skill': [],
            'excluded_due_to_product': [],
            'excluded_due_to_item': [],
            'blocked_by_exclusion_rule': [],
            'restricted_by_exclusive_rule': False,
            'sticky_worker_constraint': {
                'count_existing_workers': 0,
                'workers': [],
                'any_has_required_skill': False,
            },
            'root_cause_guess': '',
        }

        skill = task.painting_stage.required_skill if task.painting_stage else 'painter'
        product_id = task.order_item.product.id if task.order_item and task.order_item.product else None
        item_id = task.order_item_id

        # 1) کارگران با مهارت مناسب
        eligible_by_skill = []
        for w in workers_data:
            wid = w.get('user_id')
            if skill in (w.get('skills') or []):
                eligible_by_skill.append({
                    'worker_id': wid,
                    'name': w.get('full_name', str(wid)),
                    'skills': w.get('skills', []),
                })
        result['eligible_workers_by_skill'] = eligible_by_skill

        # 2) ممنوعیت‌های محصول و آیتم
        excluded_product = []
        excluded_item = []
        for wid, profile in profiles_by_id.items():
            if product_id and product_id in {p.id for p in profile.excluded_products.all()}:
                excluded_product.append({
                    'worker_id': wid,
                    'name': profile.user.get_full_name() or profile.user.username,
                })
            if item_id and item_id in {i.id for i in profile.excluded_items.all()}:
                excluded_item.append({
                    'worker_id': wid,
                    'name': profile.user.get_full_name() or profile.user.username,
                })
        result['excluded_due_to_product'] = excluded_product
        result['excluded_due_to_item'] = excluded_item

        # 3) قوانین exclusion
        blocked_by_exclusion = []
        restricted_by_exclusive = False
        for rule in rules:
            if not rule.is_active:
                continue
            if _task_matches_rule(task, rule):
                if rule.rule_type == 'exclusion':
                    blocked_by_exclusion.append({
                        'rule_id': rule.id,
                        'worker_id': rule.worker.user_id,
                        'worker_name': rule.worker.user.get_full_name() or rule.worker.user.username,
                        'priority': rule.priority,
                        'stage': str(rule.painting_stage) if rule.painting_stage else '-',
                        'color_codes': rule.color_codes,
                    })
                elif rule.rule_type == 'exclusive':
                    restricted_by_exclusive = True
        result['blocked_by_exclusion_rule'] = blocked_by_exclusion
        result['restricted_by_exclusive_rule'] = restricted_by_exclusive

        # 4) قید کارگر چسبنده (sticky worker)
        item_key = (item_id, task.color_part or '')
        existing_workers = list(item_existing_workers.get(item_key, set()))
        any_has_skill = any(
            skill in (workers_by_id.get(wid, {}).get('skills') or [])
            for wid in existing_workers
        )
        result['sticky_worker_constraint'] = {
            'count_existing_workers': len(existing_workers),
            'workers': [
                {'worker_id': wid, 'name': workers_by_id.get(wid, {}).get('full_name', str(wid))}
                for wid in existing_workers
            ],
            'any_has_required_skill': any_has_skill,
        }

        # 5) تخمین علت ریشه‌ای
        root_causes = []

        # بررسی آیا هیچ کارگر با مهارت وجود ندارد
        if not eligible_by_skill:
            root_causes.append('هیچ کارگر فعال با مهارت موردنیاز وجود ندارد')

        # بررسی sticky worker constraint
        if len(existing_workers) >= 2 and not any_has_skill:
            root_causes.append(
                f'قید کارگر چسبنده ({len(existing_workers)} کارگر قبلی) اما هیچ‌کدام مهارت «{skill}» را ندارند'
            )
        elif len(existing_workers) >= 2:
            root_causes.append(
                f'قید کارگر چسبنده فعال ({len(existing_workers)} کارگر قبلی)'
            )

        # بررسی exclusion rules
        if blocked_by_exclusion:
            excluded_worker_names = ', '.join(b['worker_name'] for b in blocked_by_exclusion)
            root_causes.append(f'قوانین منع‌کننده کارگران: {excluded_worker_names}')

        # بررسی اگر eligible_by_skill بعد از ممنوعیت‌ها خالی شده
        eligible_after_exclusions = [
            e for e in eligible_by_skill
            if e['worker_id'] not in {p['worker_id'] for p in excluded_product}
            and e['worker_id'] not in {p['worker_id'] for p in excluded_item}
        ]
        if eligible_by_skill and not eligible_after_exclusions:
            root_causes.append('همه کارگران با مهارت مناسب به دلیل ممنوعیت محصول/آیتم حذف شده‌اند')

        # بررسی قوانین exclusive که همه را محدود می‌کنند
        if restricted_by_exclusive and not eligible_after_exclusions:
            root_causes.append('قوانین محدودکننده (exclusive) باعث حذف تمام کارگران مجاز شده‌اند')

        result['root_cause_guess'] = '؛ '.join(root_causes) if root_causes else 'علت نامشخص - احتمالاً کمبود ظرفیت در روزهای کاری'

        return result

    def _print_human_readable(self, results, tasks):
        if not results:
            self.stdout.write(self.style.SUCCESS('هیچ تسک بدون زمان‌بندی یافت نشد.'))
            return

        self.stdout.write(f"\n{'=' * 80}")
        self.stdout.write(f"🔍 {len(results)} تسک بدون زمان‌بندی پیدا شد")
        self.stdout.write(f"{'=' * 80}\n")

        for i, r in enumerate(results, 1):
            task = next((t for t in tasks if t.id == r['task_id']), None)
            self.stdout.write(f"{i}. تسک #{r['task_id']}")
            self.stdout.write(f"   آیتم: {r['order_item']}")
            self.stdout.write(f"   مرحله: {r['stage']} (مهارت: {r['required_skill']})")
            self.stdout.write(f"   بخش رنگی: {r['color_part']}")
            if r['duration_minutes']:
                self.stdout.write(f"   مدت زمان: {r['duration_minutes']} دقیقه")
            self.stdout.write(f"   کارگران واجد مهارت: {len(r['eligible_workers_by_skill'])} نفر")
            if r['eligible_workers_by_skill']:
                names = ', '.join(e['name'] for e in r['eligible_workers_by_skill'][:5])
                self.stdout.write(f"     ({names})")
            if r['excluded_due_to_product']:
                names = ', '.join(e['name'] for e in r['excluded_due_to_product'][:5])
                self.stdout.write(f"   ❌ ممنوع به دلیل محصول: {names}")
            if r['excluded_due_to_item']:
                names = ', '.join(e['name'] for e in r['excluded_due_to_item'][:5])
                self.stdout.write(f"   ❌ ممنوع به دلیل آیتم: {names}")
            if r['blocked_by_exclusion_rule']:
                names = ', '.join(b['worker_name'] for b in r['blocked_by_exclusion_rule'][:5])
                self.stdout.write(f"   🚫 منع توسط قانون: {names}")
            sticky = r['sticky_worker_constraint']
            if sticky['count_existing_workers'] > 0:
                names = ', '.join(w['name'] for w in sticky['workers'][:5])
                self.stdout.write(f"   🔒 کارگر چسبنده ({sticky['count_existing_workers']} نفر قبلی): {names}")
                self.stdout.write(f"      هرکدام مهارت موردنیاز را دارند: {'بله' if sticky['any_has_required_skill'] else 'خیر'}")
            self.stdout.write(f"   💡 علت احتمالی: {r['root_cause_guess']}")
            self.stdout.write("")

        # آمار کلی
        root_cause_counts = defaultdict(int)
        for r in results:
            for cause in r['root_cause_guess'].split('؛ '):
                if cause:
                    root_cause_counts[cause] += 1

        self.stdout.write(f"\n{'=' * 80}")
        self.stdout.write("📊 آمار علل عدم زمان‌بندی")
        self.stdout.write(f"{'=' * 80}\n")
        for cause, count in sorted(root_cause_counts.items(), key=lambda x: -x[1]):
            self.stdout.write(f"  {count}x {cause}")
