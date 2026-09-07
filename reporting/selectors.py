from django.db.models import Count, Sum, F, Q
from django.utils import timezone
from datetime import timedelta
from .models import BusinessEvent, AuditLog, MigrationRun, MigrationMap

class ReportingSelectors:
    @staticmethod
    def get_business_events(category=None, event_type=None, date_from=None, date_to=None):
        qs = BusinessEvent.objects.all()
        if category:
            qs = qs.filter(category=category)
        if event_type:
            qs = qs.filter(event_type=event_type)
        if date_from:
            qs = qs.filter(occurred_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(occurred_at__date__lte=date_to)
        return qs.select_related('created_by').order_by('-occurred_at')

    @staticmethod
    def get_audit_logs(user=None, action=None, date_from=None, date_to=None):
        qs = AuditLog.objects.all()
        if user:
            qs = qs.filter(user=user)
        if action:
            qs = qs.filter(action=action)
        if date_from:
            qs = qs.filter(timestamp__date__gte=date_from)
        if date_to:
            qs = qs.filter(timestamp__date__lte=date_to)
        return qs.select_related('user').order_by('-timestamp')

    @staticmethod
    def get_migration_stats():
        return MigrationRun.objects.aggregate(
            total_runs=Count('id'),
            completed=Count('id', filter=Q(status='completed')),
            failed=Count('id', filter=Q(status='failed')),
            total_processed=Sum('records_processed'),
            total_failed=Sum('records_failed'),
        )

    @staticmethod
    def get_legacy_mappings():
        return MigrationMap.objects.filter(is_legacy=True).select_related('migration_run')
