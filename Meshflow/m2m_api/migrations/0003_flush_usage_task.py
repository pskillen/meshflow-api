from django.db import migrations


def create_task(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute="15",
        hour="*",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        defaults={"timezone": "UTC"},
    )
    PeriodicTask.objects.get_or_create(
        name="flush_m2m_usage",
        defaults={
            "task": "m2m_api.tasks.flush_m2m_usage_task",
            "crontab": schedule,
            "enabled": True,
        },
    )


def remove_task(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="flush_m2m_usage").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("m2m_api", "0002_m2m_api_group"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(create_task, remove_task),
    ]
