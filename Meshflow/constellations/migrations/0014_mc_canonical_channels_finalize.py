# Merge duplicate MC channels and drop per-row device index from MessageChannel

from django.db import migrations, models


MC_PROTOCOL = 2
MC_PUBLIC = 1
MC_HASHTAG = 2


def _logical_key(channel):
    if channel.mc_channel_type == MC_HASHTAG and channel.mc_hashtag:
        tag = str(channel.mc_hashtag).strip().lstrip("#").lower()
        if tag:
            return ("hashtag", tag)
    name = str(channel.name or "").strip().lower()
    return ("public", name)


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


def merge_duplicate_mc_channels(apps, schema_editor):
    MessageChannel = apps.get_model("constellations", "MessageChannel")
    channels = list(
        MessageChannel.objects.filter(protocol=MC_PROTOCOL).exclude(mc_channel_idx__isnull=True)
    )
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
        ("constellations", "0013_mc_canonical_channels_backfill_links"),
        ("text_messages", "0008_textmessage_mc_provenance"),
        ("meshcore_packets", "0004_observation_path_hash_size_mode"),
    ]

    operations = [
        migrations.RunPython(merge_duplicate_mc_channels, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="messagechannel",
            name="mc_channel_idx",
        ),
        migrations.AddConstraint(
            model_name="messagechannel",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("mc_channel_type", MC_HASHTAG),
                    ("mc_hashtag__isnull", False),
                    ("protocol", MC_PROTOCOL),
                ),
                fields=("constellation", "protocol", "mc_hashtag"),
                name="messagechannel_mc_hashtag_constellation_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="messagechannel",
            constraint=models.UniqueConstraint(
                condition=models.Q(("mc_channel_type", MC_PUBLIC), ("protocol", MC_PROTOCOL)),
                fields=("constellation", "protocol", "name"),
                name="messagechannel_mc_public_name_constellation_unique",
            ),
        ),
    ]
