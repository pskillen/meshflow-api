# Create feeder slot links and switch mc_channels M2M to explicit through table

import django.db.models.deletion
from django.db import migrations, models


def populate_mc_channel_links(apps, schema_editor):
    MessageChannel = apps.get_model("constellations", "MessageChannel")
    Link = apps.get_model("nodes", "ManagedNodeMcChannelLink")
    Through = apps.get_model("nodes", "ManagedNode_mc_channels")

    for row in Through.objects.all().iterator():
        try:
            channel = MessageChannel.objects.get(id=row.messagechannel_id)
        except MessageChannel.DoesNotExist:
            continue
        idx = channel.mc_channel_idx
        if idx is None:
            continue
        Link.objects.update_or_create(
            managed_node_id=row.managednode_id,
            mc_channel_idx=idx,
            defaults={"message_channel_id": channel.id},
        )


def remove_legacy_mc_channels_m2m(apps, schema_editor):
    """Drop implicit M2M table before re-adding mc_channels with through=."""
    schema_editor.execute("DROP TABLE IF EXISTS nodes_managednode_mc_channels")


class Migration(migrations.Migration):

    dependencies = [
        ("constellations", "0012_remove_mc_idx_constraint"),
        ("nodes", "0050_managednode_protocol_identity"),
    ]

    operations = [
        migrations.CreateModel(
            name="ManagedNodeMcChannelLink",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "mc_channel_idx",
                    models.PositiveSmallIntegerField(
                        help_text="MeshCore device channel index (0–63) for this feeder."
                    ),
                ),
                (
                    "managed_node",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mc_channel_links",
                        to="nodes.managednode",
                    ),
                ),
                (
                    "message_channel",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="feeder_links",
                        to="constellations.messagechannel",
                    ),
                ),
            ],
            options={
                "verbose_name": "MeshCore feeder channel link",
                "verbose_name_plural": "MeshCore feeder channel links",
            },
        ),
        migrations.RunPython(populate_mc_channel_links, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="managednode",
            name="mc_channels",
        ),
        migrations.RunPython(remove_legacy_mc_channels_m2m, migrations.RunPython.noop),
        migrations.AddField(
            model_name="managednode",
            name="mc_channels",
            field=models.ManyToManyField(
                blank=True,
                help_text="MeshCore channels mirrored from the feeder device (protocol=MeshCore only).",
                related_name="managed_nodes_mc",
                through="nodes.ManagedNodeMcChannelLink",
                to="constellations.messagechannel",
            ),
        ),
        migrations.AddConstraint(
            model_name="managednodemcchannellink",
            constraint=models.UniqueConstraint(
                fields=("managed_node", "mc_channel_idx"),
                name="managednode_mc_channel_idx_unique",
            ),
        ),
    ]
