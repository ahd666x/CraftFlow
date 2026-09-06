# product/management/commands/backfill_order_item_on_tasks.py
"""
بک‌فیلد فیلد order_item روی ProductionTask‌هایی که خالی است ولی part دارند.
از روی part.f3 با regex \.item(\d+) عدد order_item_id را استخراج می‌کند.
"""
from django.core.management.base import BaseCommand
from django.db.models import Q
import re

from product.models import ProductionTask, OrderItem


class Command(BaseCommand):
    help = 'بک‌فیلد فیلد order_item روی تسک‌هایی که part دارند ولی order_item خالی است'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='فقط گزارش می‌دهد بدون ذخیره در دیتابیس'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        tasks = ProductionTask.objects.filter(
            Q(order_item__isnull=True) & Q(part__isnull=False)
        ).select_related('order', 'part')

        total = tasks.count()
        self.stdout.write(f"تعداد تسک‌های قابل بررسی: {total}")

        updated = 0
        skipped = 0
        for task in tasks:
            match = re.search(r'\.item(\d+)$', task.part.f3 or '')
            if not match:
                skipped += 1
                continue

            order_item_id = int(match.group(1))
            try:
                order_item = OrderItem.objects.get(pk=order_item_id, order=task.order)
            except OrderItem.DoesNotExist:
                skipped += 1
                continue

            if dry_run:
                self.stdout.write(
                    f"Task {task.id}: order_item_id={order_item_id} -> order={order_item.order_id} item={order_item.id}"
                )
            else:
                task.order_item = order_item
                task.save(update_fields=['order_item'])

            updated += 1

        mode = '--dry-run' if dry_run else ''
        self.stdout.write(
            self.style.SUCCESS(
                f"تعداد {updated} رکورد اصلاح شد. {skipped} رکورد قابل‌پارس نبود (در {mode} {'حالت آزمایشی' if dry_run else 'حالت اجرایی'})."
            )
        )
