"""Add PeriodicTask for collect_traceroute_success_daily (daily at 1:05 AM)."""

from django.db import migrations


def create_task(apps, schema_editor):
    """Create PeriodicTask to run collect_traceroute_success_daily daily at 1:05 AM."""
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute="5",
        hour="1",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        defaults={"timezone": "UTC"},
    )

    PeriodicTask.objects.get_or_create(
        name="collect_traceroute_success_daily",
        defaults={
            "task": "traceroute.tasks.collect_traceroute_success_daily",
            "crontab": schedule,
            "enabled": True,
        },
    )


def remove_task(apps, schema_editor):
    """Remove the collect_traceroute_success_daily PeriodicTask."""
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="collect_traceroute_success_daily").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("traceroute", "0005_add_trigger_type_inferred"),
        ("django_celery_beat", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_task, remove_task),
    ]
