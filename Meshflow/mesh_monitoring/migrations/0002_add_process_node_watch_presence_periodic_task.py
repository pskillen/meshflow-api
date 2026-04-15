"""Add PeriodicTask for process_node_watch_presence (every 60 seconds)."""

from django.db import migrations


def create_process_node_watch_presence_task(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    schedule, _ = IntervalSchedule.objects.get_or_create(every=60, period="seconds")

    PeriodicTask.objects.get_or_create(
        name="process_node_watch_presence",
        defaults={
            "task": "mesh_monitoring.tasks.process_node_watch_presence",
            "interval": schedule,
            "enabled": True,
        },
    )


def remove_process_node_watch_presence_task(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="process_node_watch_presence").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("mesh_monitoring", "0001_mesh_monitoring_and_monitor_trigger"),
        ("django_celery_beat", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_process_node_watch_presence_task, remove_process_node_watch_presence_task),
    ]
