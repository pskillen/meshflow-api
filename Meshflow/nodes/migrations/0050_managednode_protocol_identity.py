# ManagedNode protocol identity (#362): NULL meshtastic_node_id for MeshCore, CHECK constraints

from django.db import migrations, models


def _backfill_mc_placeholder_zero(apps, schema_editor):
    ManagedNode = apps.get_model("nodes", "ManagedNode")
    bad_mc = ManagedNode.objects.filter(protocol=2, meshtastic_node_id=0, mc_pubkey__isnull=True)
    if bad_mc.exists():
        raise RuntimeError(
            "Cannot migrate: MeshCore ManagedNode rows have meshtastic_node_id=0 without mc_pubkey. "
            "Set mc_pubkey in Django admin, then re-run migrate."
        )
    bad_mt = ManagedNode.objects.filter(protocol=1, meshtastic_node_id__isnull=True)
    if bad_mt.exists():
        raise RuntimeError(
            "Cannot migrate: Meshtastic ManagedNode rows have NULL meshtastic_node_id."
        )
    ManagedNode.objects.filter(protocol=2, meshtastic_node_id=0).update(meshtastic_node_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ("nodes", "0049_managednode_mc_flood_advert_interval"),
    ]

    operations = [
        migrations.AlterField(
            model_name="managednode",
            name="meshtastic_node_id",
            field=models.BigIntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.RunPython(_backfill_mc_placeholder_zero, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="managednode",
            constraint=models.CheckConstraint(
                condition=models.Q(protocol=1, meshtastic_node_id__isnull=False, mc_pubkey__isnull=True)
                | models.Q(protocol=2, meshtastic_node_id__isnull=True, mc_pubkey__isnull=False),
                name="managednode_protocol_identity",
            ),
        ),
        migrations.AddConstraint(
            model_name="managednode",
            constraint=models.UniqueConstraint(
                condition=models.Q(protocol=1, deleted_at__isnull=True),
                fields=("meshtastic_node_id",),
                name="managednode_unique_meshtastic_node_id_active",
            ),
        ),
    ]
