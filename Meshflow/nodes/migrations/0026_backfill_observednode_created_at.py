"""Backfill ObservedNode.created_at from earliest RawPacket.first_reported_time."""

from django.db import migrations


def backfill_created_at(apps, schema_editor):
    ObservedNode = apps.get_model("nodes", "ObservedNode")
    RawPacket = apps.get_model("packets", "RawPacket")

    from django.db.models import Min

    # Get earliest first_reported_time per from_int
    earliest = (
        RawPacket.objects.values("from_int")
        .annotate(earliest_time=Min("first_reported_time"))
        .order_by()
    )

    for row in earliest:
        from_int = row["from_int"]
        earliest_time = row["earliest_time"]
        ObservedNode.objects.filter(node_id=from_int, created_at__isnull=True).update(
            created_at=earliest_time
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("nodes", "0025_stats_snapshot_and_observed_node_created_at"),
        ("packets", "0003_rawpacket_first_reported_time"),
    ]

    operations = [
        migrations.RunPython(backfill_created_at, noop),
    ]
