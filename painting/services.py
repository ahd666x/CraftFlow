from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import PaintingProcess, PaintingProcessStage, PaintingSchedule, PaintingScheduleItem, PaintingAssignmentRule

User = get_user_model()


class PaintingService:
    @staticmethod
    def create_painting_process(name, code, color_codes=None, **kwargs):
        with transaction.atomic():
            process = PaintingProcess.objects.create(
                name=name,
                code=code,
                color_codes=color_codes or [],
                **kwargs
            )
            return process

    @staticmethod
    def add_painting_stage(process, sequence, name, duration_minutes, drying_time_minutes=0, **kwargs):
        with transaction.atomic():
            stage = PaintingProcessStage.objects.create(
                process=process,
                sequence=sequence,
                name=name,
                duration_minutes=duration_minutes,
                drying_time_minutes=drying_time_minutes,
                **kwargs
            )
            return stage

    @staticmethod
    def create_daily_schedule(date, created_by, **kwargs):
        with transaction.atomic():
            schedule, created = PaintingSchedule.objects.get_or_create(
                date=date,
                defaults={
                    'created_by': created_by,
                    'status': 'draft',
                    **kwargs
                }
            )
            return schedule

    @staticmethod
    def assign_to_schedule(schedule, production_operation, worker, painting_stage, scheduled_start, scheduled_end, **kwargs):
        with transaction.atomic():
            item = PaintingScheduleItem.objects.create(
                schedule=schedule,
                production_operation=production_operation,
                worker=worker,
                painting_stage=painting_stage,
                scheduled_start=scheduled_start,
                scheduled_end=scheduled_end,
                **kwargs
            )
            return item

    @staticmethod
    def get_worker_availability(worker, date):
        schedule_items = PaintingScheduleItem.objects.filter(
            worker=worker,
            scheduled_start__date=date,
        ).order_by('scheduled_start')
        return schedule_items
