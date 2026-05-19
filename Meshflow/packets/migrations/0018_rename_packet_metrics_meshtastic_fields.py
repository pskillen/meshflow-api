# SP-08: Meshtastic metrics columns on packet payload tables

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("packets", "0017_rename_rawpacket_to_mtrawpacket"),
    ]

    operations = [
        migrations.RenameField(
            model_name="positionpacket",
            old_name="location_source",
            new_name="meshtastic_location_source",
        ),
        migrations.RenameField(
            model_name="positionpacket",
            old_name="precision_bits",
            new_name="meshtastic_precision_bits",
        ),
        migrations.RenameField(
            model_name="devicemetricspacket",
            old_name="channel_utilization",
            new_name="meshtastic_channel_utilization",
        ),
        migrations.RenameField(
            model_name="devicemetricspacket",
            old_name="air_util_tx",
            new_name="meshtastic_air_util_tx",
        ),
        migrations.RenameField(
            model_name="localstatspacket",
            old_name="channel_utilization",
            new_name="meshtastic_channel_utilization",
        ),
        migrations.RenameField(
            model_name="localstatspacket",
            old_name="air_util_tx",
            new_name="meshtastic_air_util_tx",
        ),
    ]
