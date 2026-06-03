# Add region_scope, backfill from mc_hashtag, merge duplicates, drop mc_hashtag

from django.db import migrations, models

MC_PROTOCOL = 2


def _normalize_tag(value):
    if not value:
        return ""
    return str(value).strip().lstrip("#").lower()[:100]


def _logical_key(channel):
    name = str(channel.name or "").strip().lower()
    if channel.mc_channel_type == 2 and channel.mc_hashtag:
        tag = _normalize_tag(channel.mc_hashtag)
        if tag:
            name = tag
    return (channel.mc_channel_type, name, channel.region_scope)


def _repoint_channel_fks(apps, old_id, new_id):
    if old_id == new_id:
        return
    TextMessage = apps.get_model("text_messages", "TextMessage")
    TextMessage.objects.filter(channel_id=old_id).update(channel_id=new_id)

    try:
        MeshCoreTextPacket = apps.get_model("meshcore_packets", "MeshCoreTextPacket")
        MeshCoreTextPacket.objects.filter(channel_id=old_id).update(channel_id=new_id)
    except LookupError:
        pass

    try:
        MeshCorePacketObservation = apps.get_model("meshcore_packets", "MeshCorePacketObservation")
        MeshCorePacketObservation.objects.filter(channel_id=old_id).update(channel_id=new_id)
    except LookupError:
        pass

    Link = apps.get_model("nodes", "ManagedNodeMcChannelLink")
    Link.objects.filter(message_channel_id=old_id).update(message_channel_id=new_id)


def backfill_hashtag_names(apps, schema_editor):
    MessageChannel = apps.get_model("constellations", "MessageChannel")
    for ch in MessageChannel.objects.filter(protocol=MC_PROTOCOL, mc_channel_type=2):
        tag = _normalize_tag(ch.mc_hashtag or ch.name)
        if tag and ch.name != tag:
            ch.name = tag
            ch.save(update_fields=["name"])


def merge_duplicate_mc_channels(apps, schema_editor):
    MessageChannel = apps.get_model("constellations", "MessageChannel")
    channels = list(MessageChannel.objects.filter(protocol=MC_PROTOCOL))
    groups = {}
    for ch in channels:
        key = (ch.constellation_id, _logical_key(ch))
        groups.setdefault(key, []).append(ch)

    for _key, group in groups.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda c: c.id)
        survivor = group[0]
        for dup in group[1:]:
            _repoint_channel_fks(apps, dup.id, survivor.id)
            MessageChannel.objects.filter(id=dup.id).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("constellations", "0014_mc_canonical_channels_finalize"),
        ("text_messages", "0008_textmessage_mc_provenance"),
        ("meshcore_packets", "0004_observation_path_hash_size_mode"),
    ]

    operations = [
        migrations.AddField(
            model_name="messagechannel",
            name="region_scope",
            field=models.CharField(
                blank=True,
                help_text=(
                    "MeshCore region scope when protocol is MeshCore (lowercase alphanumeric + "
                    "hyphen; null = legacy / no scope)."
                ),
                max_length=29,
                null=True,
            ),
        ),
        migrations.RunPython(backfill_hashtag_names, migrations.RunPython.noop),
        migrations.RunPython(merge_duplicate_mc_channels, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="messagechannel",
            name="messagechannel_mc_hashtag_constellation_unique",
        ),
        migrations.RemoveConstraint(
            model_name="messagechannel",
            name="messagechannel_mc_public_name_constellation_unique",
        ),
        migrations.RemoveField(
            model_name="messagechannel",
            name="mc_hashtag",
        ),
        migrations.AddConstraint(
            model_name="messagechannel",
            constraint=models.UniqueConstraint(
                condition=models.Q(("protocol", MC_PROTOCOL), ("region_scope__isnull", True)),
                fields=("constellation", "protocol", "name", "mc_channel_type"),
                name="messagechannel_mc_null_scope_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="messagechannel",
            constraint=models.UniqueConstraint(
                condition=models.Q(("protocol", MC_PROTOCOL), ("region_scope__isnull", False)),
                fields=("constellation", "protocol", "name", "mc_channel_type", "region_scope"),
                name="messagechannel_mc_region_scope_unique",
            ),
        ),
    ]
