"""Add PeriodicTask for update_managed_node_statuses (every 5 minutes)."""

from django.db import migrations


def create_update_managed_node_statuses_task(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    schedule, _ = IntervalSchedule.objects.get_or_create(every=300, period="seconds")

    PeriodicTask.objects.get_or_create(
        name="update_managed_node_statuses",
        defaults={
            "task": "nodes.tasks.update_managed_node_statuses",
            "interval": schedule,
            "enabled": True,
        },
    )


def remove_update_managed_node_statuses_task(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="update_managed_node_statuses").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("nodes", "0031_add_managednodestatus"),
        ("django_celery_beat", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_update_managed_node_statuses_task, remove_update_managed_node_statuses_task),
    ]
