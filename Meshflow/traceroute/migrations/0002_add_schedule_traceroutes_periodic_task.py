"""Add PeriodicTask for schedule_traceroutes (every 2 hours)."""

from django.db import migrations


def create_schedule_traceroutes_task(apps, schema_editor):
    """Create PeriodicTask to run schedule_traceroutes every 2 hours."""
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute="0",
        hour="*/2",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        defaults={"timezone": "UTC"},
    )

    PeriodicTask.objects.get_or_create(
        name="schedule_traceroutes",
        defaults={
            "task": "traceroute.tasks.schedule_traceroutes",
            "crontab": schedule,
            "enabled": True,
        },
    )


def remove_schedule_traceroutes_task(apps, schema_editor):
    """Remove the schedule_traceroutes PeriodicTask."""
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="schedule_traceroutes").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("traceroute", "0001_initial"),
        ("django_celery_beat", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_schedule_traceroutes_task, remove_schedule_traceroutes_task),
    ]
