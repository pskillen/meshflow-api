# SP-03: node_id → meshtastic_node_id on ObservedNode and ManagedNode

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nodes", "0036_observednode_mc_identity"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="observednode",
            name="nodes_observednode_protocol_identity",
        ),
        migrations.RenameField(
            model_name="observednode",
            old_name="node_id",
            new_name="meshtastic_node_id",
        ),
        migrations.RenameField(
            model_name="managednode",
            old_name="node_id",
            new_name="meshtastic_node_id",
        ),
        migrations.AddConstraint(
            model_name="observednode",
            constraint=models.CheckConstraint(
                condition=models.Q(protocol=1, meshtastic_node_id__isnull=False)
                | (
                    models.Q(protocol=2)
                    & (models.Q(mc_pubkey__isnull=False) | models.Q(mc_pubkey_prefix__isnull=False))
                ),
                name="nodes_observednode_protocol_identity",
            ),
        ),
    ]
