# SP-06: Meshtastic channel slots on ManagedNode

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("nodes", "0039_rename_observednode_meshtastic_identity_fields"),
    ]

    operations = [
        migrations.RenameField(
            model_name="managednode",
            old_name="channel_0",
            new_name="meshtastic_channel_0",
        ),
        migrations.RenameField(
            model_name="managednode",
            old_name="channel_1",
            new_name="meshtastic_channel_1",
        ),
        migrations.RenameField(
            model_name="managednode",
            old_name="channel_2",
            new_name="meshtastic_channel_2",
        ),
        migrations.RenameField(
            model_name="managednode",
            old_name="channel_3",
            new_name="meshtastic_channel_3",
        ),
        migrations.RenameField(
            model_name="managednode",
            old_name="channel_4",
            new_name="meshtastic_channel_4",
        ),
        migrations.RenameField(
            model_name="managednode",
            old_name="channel_5",
            new_name="meshtastic_channel_5",
        ),
        migrations.RenameField(
            model_name="managednode",
            old_name="channel_6",
            new_name="meshtastic_channel_6",
        ),
        migrations.RenameField(
            model_name="managednode",
            old_name="channel_7",
            new_name="meshtastic_channel_7",
        ),
    ]
