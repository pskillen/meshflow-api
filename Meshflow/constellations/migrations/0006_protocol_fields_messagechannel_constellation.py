# Generated manually for MeshCore Phase 1.0 (protocol prep)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("constellations", "0005_add_bot_default_env_vars"),
    ]

    operations = [
        migrations.AddField(
            model_name="constellation",
            name="protocol",
            field=models.PositiveSmallIntegerField(
                choices=[(1, "Meshtastic"), (2, "MeshCore")],
                db_index=True,
                default=1,
                help_text="Mesh protocol for this constellation and its channels.",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="messagechannel",
            name="protocol",
            field=models.PositiveSmallIntegerField(
                choices=[(1, "Meshtastic"), (2, "MeshCore")],
                db_index=True,
                default=1,
                help_text="Mesh protocol for this channel row.",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="messagechannel",
            name="mc_channel_idx",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                help_text="MeshCore channel index when protocol is MeshCore; null for Meshtastic.",
            ),
        ),
    ]
