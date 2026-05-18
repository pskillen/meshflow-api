# Generated manually for MeshCore Phase 1.0 (protocol prep)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nodes", "0033_managednode_deleted_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="managednode",
            name="protocol",
            field=models.PositiveSmallIntegerField(
                choices=[(1, "Meshtastic"), (2, "MeshCore")],
                db_index=True,
                default=1,
                help_text="Mesh protocol for this managed node (constellation must match).",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="observednode",
            name="protocol",
            field=models.PositiveSmallIntegerField(
                choices=[(1, "Meshtastic"), (2, "MeshCore")],
                db_index=True,
                default=1,
                help_text="Mesh protocol for this observed node.",
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="observednode",
            name="node_id",
            field=models.BigIntegerField(
                blank=True,
                db_index=True,
                help_text="Meshtastic numeric node id when protocol is Meshtastic; null for MeshCore rows once supported.",
                null=True,
            ),
        ),
        migrations.AddConstraint(
            model_name="observednode",
            constraint=models.CheckConstraint(
                condition=models.Q(protocol=1, node_id__isnull=False) | models.Q(protocol=2),
                name="nodes_observednode_protocol_node_id",
            ),
        ),
    ]
