# Generated manually for UI #148 — canonical silence threshold on NodePresence.

from django.db import migrations, models
from django.db.models import Min


def forwards_copy_offline_after_to_presence(apps, schema_editor):
    NodeWatch = apps.get_model("mesh_monitoring", "NodeWatch")
    NodePresence = apps.get_model("mesh_monitoring", "NodePresence")

    for row in NodeWatch.objects.values("observed_node_id").distinct():
        oid = row["observed_node_id"]
        enabled_min = NodeWatch.objects.filter(observed_node_id=oid, enabled=True).aggregate(
            m=Min("offline_after"),
        )["m"]
        if enabled_min is not None:
            val = enabled_min
        else:
            val = NodeWatch.objects.filter(observed_node_id=oid).aggregate(m=Min("offline_after"))["m"]
            if val is None:
                val = 21600

        pres, created = NodePresence.objects.get_or_create(
            observed_node_id=oid,
            defaults={
                "offline_after": val,
                "tr_sent_count": 0,
                "is_offline": False,
            },
        )
        if not created:
            NodePresence.objects.filter(pk=oid).update(offline_after=val)


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("mesh_monitoring", "0005_nodepresence_last_verification_notify_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="nodepresence",
            name="offline_after",
            field=models.PositiveIntegerField(
                default=21600,
                help_text="Seconds without packets (last_heard) before verification may start.",
            ),
        ),
        migrations.RunPython(forwards_copy_offline_after_to_presence, backwards_noop),
        migrations.RemoveField(
            model_name="nodewatch",
            name="offline_after",
        ),
    ]
