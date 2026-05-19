# SP-08: Meshtastic metrics columns on NodeLatestStatus, Position, DeviceMetrics

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("nodes", "0040_rename_managednode_meshtastic_channels"),
    ]

    operations = [
        migrations.RenameField(
            model_name="nodelateststatus",
            old_name="location_source",
            new_name="meshtastic_location_source",
        ),
        migrations.RenameField(
            model_name="nodelateststatus",
            old_name="precision_bits",
            new_name="meshtastic_precision_bits",
        ),
        migrations.RenameField(
            model_name="nodelateststatus",
            old_name="channel_utilization",
            new_name="meshtastic_channel_utilization",
        ),
        migrations.RenameField(
            model_name="nodelateststatus",
            old_name="air_util_tx",
            new_name="meshtastic_air_util_tx",
        ),
        migrations.RenameField(
            model_name="nodelateststatus",
            old_name="inferred_max_hops",
            new_name="meshtastic_inferred_max_hops",
        ),
        migrations.RenameField(
            model_name="position",
            old_name="location_source",
            new_name="meshtastic_location_source",
        ),
        migrations.RenameField(
            model_name="position",
            old_name="precision_bits",
            new_name="meshtastic_precision_bits",
        ),
        migrations.RenameField(
            model_name="devicemetrics",
            old_name="channel_utilization",
            new_name="meshtastic_channel_utilization",
        ),
        migrations.RenameField(
            model_name="devicemetrics",
            old_name="air_util_tx",
            new_name="meshtastic_air_util_tx",
        ),
    ]
