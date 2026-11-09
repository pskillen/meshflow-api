"""NodePresence learned offline threshold fields and the daily task that fills them."""

from django.db import migrations, models


def create_task(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute="30",
        hour="3",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        defaults={"timezone": "UTC"},
    )
    PeriodicTask.objects.get_or_create(
        name="update_learned_offline_thresholds",
        defaults={
            "task": "mesh_monitoring.tasks.update_learned_offline_thresholds",
            "crontab": schedule,
            "enabled": True,
        },
    )


def remove_task(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="update_learned_offline_thresholds").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("mesh_monitoring", "0008_sync_field_metadata"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="nodepresence",
            name="learned_offline_after_seconds",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                help_text=(
                    "Silence threshold learned from this node's own packet cadence (3 x p90 of recent gaps, "
                    "clamped to 6 h - 48 h); null when there is too little history. Written daily."
                ),
            ),
        ),
        migrations.AddField(
            model_name="nodepresence",
            name="learned_offline_computed_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="When learned_offline_after_seconds was last computed.",
            ),
        ),
        migrations.RunPython(create_task, remove_task),
    ]
