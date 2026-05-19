# SP-07: Meshtastic fields on TextMessage

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("text_messages", "0006_alter_textmessage_original_packet"),
    ]

    operations = [
        migrations.RenameField(
            model_name="textmessage",
            old_name="recipient_node_id",
            new_name="recipient_meshtastic_node_id",
        ),
        migrations.RenameField(
            model_name="textmessage",
            old_name="reply_to_message_id",
            new_name="reply_to_meshtastic_packet_id",
        ),
    ]
