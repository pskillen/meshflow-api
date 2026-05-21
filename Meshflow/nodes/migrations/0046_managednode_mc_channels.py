# Generated manually for Phase 2.2 MC channels

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("constellations", "0009_messagechannel_mc_type_hashtag"),
        ("nodes", "0045_position_meshcore_provenance"),
    ]

    operations = [
        migrations.AddField(
            model_name="managednode",
            name="mc_channels_synced_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When mc_channels was last reconciled from the device via bot sync.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="managednode",
            name="mc_channels",
            field=models.ManyToManyField(
                blank=True,
                help_text="MeshCore channels mirrored from the feeder device (protocol=MeshCore only).",
                related_name="managed_nodes_mc",
                to="constellations.messagechannel",
            ),
        ),
    ]
