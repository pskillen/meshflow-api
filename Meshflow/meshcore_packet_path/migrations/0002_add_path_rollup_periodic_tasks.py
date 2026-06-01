"""Add PeriodicTasks for path edge rollup and eviction."""

from django.db import migrations


def create_periodic_tasks(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    hourly, _ = CrontabSchedule.objects.get_or_create(
        minute="5",
        hour="*",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        defaults={"timezone": "UTC"},
    )
    PeriodicTask.objects.get_or_create(
        name="collect_path_edge_buckets",
        defaults={
            "task": "meshcore_packet_path.tasks.collect_path_edge_buckets",
            "crontab": hourly,
            "enabled": True,
        },
    )

    daily, _ = CrontabSchedule.objects.get_or_create(
        minute="15",
        hour="2",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        defaults={"timezone": "UTC"},
    )
    PeriodicTask.objects.get_or_create(
        name="evict_old_path_data",
        defaults={
            "task": "meshcore_packet_path.tasks.evict_old_path_data",
            "crontab": daily,
            "enabled": True,
        },
    )


def remove_periodic_tasks(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(
        name__in=("collect_path_edge_buckets", "evict_old_path_data")
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("meshcore_packet_path", "0001_initial"),
        ("django_celery_beat", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_periodic_tasks, remove_periodic_tasks),
    ]
