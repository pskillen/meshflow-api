# Generated manually for MeshCore Phase 1 (ADR-0001)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nodes", "0035_protocol_help_text_managed_channels"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="observednode",
            name="nodes_observednode_protocol_node_id",
        ),
        migrations.AlterField(
            model_name="observednode",
            name="node_id_str",
            field=models.CharField(
                db_index=True,
                help_text="Display id: !hex8 (Meshtastic) or mc:prefix12 (MeshCore).",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="observednode",
            name="mc_pubkey",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="MeshCore Ed25519 public key (64 hex chars) when known.",
                max_length=64,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="observednode",
            name="mc_pubkey_prefix",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="MeshCore 6-byte pubkey prefix (12 hex chars); from contact_message or derived from full key.",
                max_length=12,
                null=True,
            ),
        ),
        migrations.AddConstraint(
            model_name="observednode",
            constraint=models.CheckConstraint(
                condition=models.Q(protocol=1, node_id__isnull=False)
                | (
                    models.Q(protocol=2)
                    & (models.Q(mc_pubkey__isnull=False) | models.Q(mc_pubkey_prefix__isnull=False))
                ),
                name="nodes_observednode_protocol_identity",
            ),
        ),
        migrations.AddConstraint(
            model_name="observednode",
            constraint=models.UniqueConstraint(
                condition=models.Q(protocol=2, mc_pubkey__isnull=False),
                fields=("mc_pubkey",),
                name="nodes_observednode_mc_pubkey_unique",
            ),
        ),
    ]
