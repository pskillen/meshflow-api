# SP-06: Meshtastic bot defaults on Constellation

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("constellations", "0007_protocol_help_text_managed_channels"),
    ]

    operations = [
        migrations.RenameField(
            model_name="constellation",
            old_name="bot_default_ignore_portnums",
            new_name="bot_default_ignore_meshtastic_portnums",
        ),
        migrations.RenameField(
            model_name="constellation",
            old_name="bot_default_hop_limit",
            new_name="bot_default_meshtastic_hop_limit",
        ),
    ]
