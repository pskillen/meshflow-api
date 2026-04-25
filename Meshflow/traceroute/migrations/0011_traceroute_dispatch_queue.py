# Traceroute dispatch queue fields and periodic dispatch task (meshflow-api#226)

from django.db import migrations, models
from django.db.models import F


def backfill_dispatch_fields(apps, schema_editor):
    AutoTraceRoute = apps.get_model("traceroute", "AutoTraceRoute")
    AutoTraceRoute.objects.update(earliest_send_at=F("triggered_at"))
    AutoTraceRoute.objects.filter(status__in=["sent", "completed"], dispatched_at__isnull=True).update(
        dispatched_at=F("triggered_at")
    )


def reverse_backfill(apps, schema_editor):
    pass


def create_dispatch_periodic_task(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    schedule, _ = IntervalSchedule.objects.get_or_create(every=15, period="seconds")

    PeriodicTask.objects.get_or_create(
        name="dispatch_pending_traceroutes",
        defaults={
            "task": "traceroute.tasks.dispatch_pending_traceroutes",
            "interval": schedule,
            "enabled": True,
        },
    )


def remove_dispatch_periodic_task(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="dispatch_pending_traceroutes").delete()


class Migration(migrations.Migration):
    # RunPython + AlterField in one transaction can fail on PostgreSQL (pending trigger events).
    atomic = False

    dependencies = [
        ("traceroute", "0010_integer_trigger_type"),
        ("django_celery_beat", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="autotraceroute",
            name="dispatch_attempts",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Failed delivery attempts to Channels (keeps status pending)",
            ),
        ),
        migrations.AddField(
            model_name="autotraceroute",
            name="dispatch_error",
            field=models.TextField(
                blank=True,
                help_text="Last error from the channel layer or dispatch logic",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="autotraceroute",
            name="dispatched_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Set when the traceroute command is sent to the source node's WebSocket group",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="autotraceroute",
            name="earliest_send_at",
            field=models.DateTimeField(db_index=True, help_text="Not before this time: dispatch to source node (per-feeder spacing in the dispatcher)", null=True),
        ),
        migrations.RunPython(backfill_dispatch_fields, reverse_backfill),
        migrations.AlterField(
            model_name="autotraceroute",
            name="earliest_send_at",
            field=models.DateTimeField(
                db_index=True,
                help_text="Not before this time: dispatch to source node (per-feeder spacing in the dispatcher)",
            ),
        ),
        migrations.AddIndex(
            model_name="autotraceroute",
            index=models.Index(fields=["status", "earliest_send_at"], name="traceroute__status_b7e6f0_idx"),
        ),
        migrations.RunPython(create_dispatch_periodic_task, remove_dispatch_periodic_task),
    ]
