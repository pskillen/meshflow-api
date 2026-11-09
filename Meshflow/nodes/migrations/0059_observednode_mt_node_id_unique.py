"""One ObservedNode per Meshtastic node number (#480 part 2).

The merge step runs first, so any duplicates left since ``dedupe_observed_nodes`` was run are folded away before the
constraint is added. It fails closed: a duplicate set whose rows have different ``claimed_by`` owners cannot be merged
automatically, so the migration raises naming the nodes and the owner fixes the claim in admin.

The merge step uses the live merge code (``nodes.services.observed_node_merge``) rather than a frozen copy, because
it re-points every relation generically. That is only safe while the live model matches the schema at this point, so
the step first checks for duplicates with the historical model and does nothing when there are none (always the case
on a fresh database), which keeps this migration runnable after later schema changes.
"""

from django.db import migrations, models
from django.db.models import Count


def merge_duplicate_nodes(apps, schema_editor):
    ObservedNode = apps.get_model("nodes", "ObservedNode")
    duplicated = (
        ObservedNode.objects.filter(protocol=1, meshtastic_node_id__isnull=False)
        .values("meshtastic_node_id")
        .annotate(n=Count("pk"))
        .filter(n__gt=1)
        .exists()
    )
    if not duplicated:
        return

    from nodes.services.observed_node_merge import merge_duplicate_meshtastic_nodes

    report = merge_duplicate_meshtastic_nodes()
    if report.conflicts:
        raise RuntimeError(
            "Cannot add the unique Meshtastic node number constraint: these duplicate ObservedNode sets cannot be "
            "merged automatically. Fix the claims in admin (leave one owner per node), then migrate again. "
            + "; ".join(report.conflicts)
        )


class Migration(migrations.Migration):

    dependencies = [
        ("nodes", "0058_managednode_reported_firmware"),
    ]

    operations = [
        migrations.RunPython(merge_duplicate_nodes, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="observednode",
            constraint=models.UniqueConstraint(
                condition=models.Q(("protocol", 1)),
                fields=("meshtastic_node_id",),
                name="nodes_observednode_mt_node_id_unique",
            ),
        ),
    ]
