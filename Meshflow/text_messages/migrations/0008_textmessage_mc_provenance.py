# Generated manually for Phase 2.2 MC text messages

import django.db.models.deletion
from django.db import migrations, models

import common.protocol


def backfill_protocol(apps, schema_editor):
    TextMessage = apps.get_model("text_messages", "TextMessage")
    TextMessage.objects.filter(original_packet_id__isnull=False).update(protocol=1)


class Migration(migrations.Migration):

    dependencies = [
        ("meshcore_packets", "0001_initial"),
        ("text_messages", "0007_rename_textmessage_meshtastic_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="textmessage",
            name="protocol",
            field=models.PositiveSmallIntegerField(
                choices=[(1, "Meshtastic"), (2, "MeshCore")],
                db_index=True,
                default=common.protocol.Protocol.MESHTASTIC,
                help_text="Mesh protocol for this message row.",
            ),
        ),
        migrations.AddField(
            model_name="textmessage",
            name="original_mc_packet",
            field=models.ForeignKey(
                blank=True,
                help_text="Provenance: MeshCore text packet.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="text_messages",
                to="meshcore_packets.meshcoretextpacket",
            ),
        ),
        migrations.AlterField(
            model_name="textmessage",
            name="original_packet",
            field=models.ForeignKey(
                blank=True,
                help_text="Provenance: Meshtastic MessagePacket.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="text_messages",
                to="packets.messagepacket",
            ),
        ),
        migrations.AlterField(
            model_name="textmessage",
            name="sender",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="nodes.observednode",
            ),
        ),
        migrations.AlterField(
            model_name="textmessage",
            name="sent_at",
            field=models.DateTimeField(),
        ),
        migrations.RunPython(backfill_protocol, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="textmessage",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(original_packet__isnull=False, original_mc_packet__isnull=True)
                    | models.Q(original_packet__isnull=True, original_mc_packet__isnull=False)
                ),
                name="textmessage_single_provenance",
            ),
        ),
    ]
