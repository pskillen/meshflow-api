# Generated manually for Phase 2.2 MC channels

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("constellations", "0008_rename_constellation_bot_meshtastic_defaults"),
    ]

    operations = [
        migrations.AddField(
            model_name="messagechannel",
            name="mc_channel_type",
            field=models.PositiveSmallIntegerField(
                blank=True,
                choices=[(1, "PUBLIC"), (2, "HASHTAG")],
                help_text="MeshCore channel type when protocol is MeshCore.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="messagechannel",
            name="mc_hashtag",
            field=models.CharField(
                blank=True,
                help_text="Hashtag string when mc_channel_type is HASHTAG (no leading #).",
                max_length=64,
                null=True,
            ),
        ),
        migrations.AddConstraint(
            model_name="messagechannel",
            constraint=models.UniqueConstraint(
                condition=models.Q(("mc_channel_idx__isnull", False), ("protocol", 2)),
                fields=("constellation", "protocol", "mc_channel_idx"),
                name="messagechannel_mc_idx_constellation_unique",
            ),
        ),
    ]
