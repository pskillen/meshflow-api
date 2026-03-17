"""Add PeriodicTask for collect_stats_snapshots (hourly)."""

from django.db import migrations


def create_collect_stats_task(apps, schema_editor):
    """Create PeriodicTask to run collect_stats_snapshots every hour."""
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute="5",
        hour="*",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        defaults={"timezone": "UTC"},
    )

    PeriodicTask.objects.get_or_create(
        name="collect_stats_snapshots",
        defaults={
            "task": "stats.tasks.collect_stats_snapshots",
            "crontab": schedule,
            "enabled": True,
        },
    )


def remove_collect_stats_task(apps, schema_editor):
    """Remove the collect_stats_snapshots PeriodicTask."""
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="collect_stats_snapshots").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("stats", "0001_stats_snapshot_and_observed_node_created_at"),
        ("django_celery_beat", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_collect_stats_task, remove_collect_stats_task),
    ]
