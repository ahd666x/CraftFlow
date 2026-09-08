from decimal import Decimal
from django.db import transaction
from django.contrib.auth import get_user_model
import jdatetime
from .models import ProductionTask, ProductionEvent
from .utils import log_production_event, consume_material_for_task

User = get_user_model()


class LegacyProductionService:
    @staticmethod
    def complete_task(task, completed_quantity=None, actor=None):
        """
        تکمیل یک ProductionTask با Behavior کاملاً مطابق legacy ProductionTask.save().

        این متد:
        - completed_quantity را به‌روز می‌کند
        - در صورت رسیدن به مقدار سفارش، status را به 'done' تغییر می‌دهد
        - completed_at جلالی را تنظیم می‌کند
        - ProductionEvent ثبت می‌کند
        - مصرف خودکار مواد را triggering می‌کند (idempotent)
        - مرحله بعدی را فعال می‌کند
        - وضعیت Order را به‌روز می‌کند

        transactionomic است و در صورت خطای مصرف ماده، rollback کامل دارد.

        توجه: این متد برای backward compatibility است. در Phase بعدی،
        ProductionOperation V2 جایگزین خواهد شد.
        """
        with transaction.atomic():
            old_status = task.status

            # Update completed_quantity if provided
            if completed_quantity is not None:
                task.completed_quantity = completed_quantity

            # Clamp completed_quantity to task.quantity
            if task.completed_quantity > task.quantity:
                task.completed_quantity = task.quantity

            # Auto-transition to done if quantity met
            if task.completed_quantity >= task.quantity:
                task.status = 'done'

            # Set scanned_by whenever actor is provided
            if actor is not None:
                task.scanned_by = actor

            # Only execute completion side effects when transitioning to done
            if task.status == 'done' and old_status != 'done':
                if not task.completed_at:
                    task.completed_at = jdatetime.date.today()
                if task.completed_quantity < task.quantity:
                    task.completed_quantity = task.quantity

                # Save model without triggering legacy side effects in save()
                task._bypass_completion_effects = True
                try:
                    task.save(update_fields=['status', 'completed_at', 'completed_quantity', 'scanned_by'])
                finally:
                    if hasattr(task, '_bypass_completion_effects'):
                        delattr(task, '_bypass_completion_effects')

                # Explicit side effects (legacy behavior)
                # Note: exceptions here will rollback the transaction
                log_production_event(
                    task=task,
                    event_type='done',
                    user=actor,
                    old_status=old_status or '',
                    new_status='done',
                    quantity=task.completed_quantity or task.quantity,
                )

                consume_material_for_task(task)

                # Legacy next-step activation
                if task.station_name == 'paint' and task.order_item_id:
                    next_step = ProductionTask.objects.filter(
                        order=task.order,
                        station_name='paint',
                        order_item=task.order_item,
                        color_part=task.color_part,
                        step_order=task.step_order + 1,
                    ).first()
                else:
                    next_step = ProductionTask.objects.filter(
                        order=task.order,
                        part=task.part,
                        step_order=task.step_order + 1,
                    ).first()

                if next_step and next_step.status == 'waiting':
                    next_step.status = 'pending'
                    next_step._bypass_completion_effects = True
                    try:
                        next_step.save(update_fields=['status'])
                    finally:
                        if hasattr(next_step, '_bypass_completion_effects'):
                            delattr(next_step, '_bypass_completion_effects')

                # Update Order status
                task.update_order_status()
            else:
                # Not transitioning to done, just save
                task.save()
