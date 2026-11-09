"""One ObservedNode per Meshtastic node number (#480 part 2).

The merge step runs first, so any duplicates left since ``dedupe_observed_nodes`` was run are folded away before the
constraint is added. It fails closed: a duplicate set whose rows have different ``claimed_by`` owners cannot be merged
automatically, so the migration raises naming the nodes and changes nothing (recovery: ``docs/DEPLOY.md``).

The merge is a frozen copy of the rules in ``nodes.services.observed_node_merge``, written against the historical
models, so a database still at 0058 with duplicates can migrate whatever the live models have become. Later changes
to the live merge do not belong here.
"""

from collections import defaultdict

from django.db import IntegrityError, migrations, models, transaction
from django.db.models import Count, F

MESHTASTIC = 1
NAME_FIELDS = ("long_name", "short_name")
IDENTITY_FIELDS = (
    "meshtastic_public_key",
    "meshtastic_public_key_hex",
    "meshtastic_key_node_id",
    "mac_addr",
    "meshtastic_hw_model",
    "meshtastic_role",
    "inferred_firmware",
    "inferred_firmware_basis",
    "inferred_firmware_at",
)


def _is_blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def _is_real_name(name, node_id, name_field):
    if _is_blank(name):
        return False
    full = f"{node_id & 0xFFFFFFFF:08x}"
    value = name.strip().lower()
    if name_field == "long_name":
        return value not in (f"meshtastic {full[-4:]}", f"unknown node !{full}")
    return value != full[-4:]


def _heard_sort_key(node):
    """Most recently heard first; never-heard last; ties by age then pk."""
    heard = node.last_heard.timestamp() if node.last_heard else float("-inf")
    created = node.created_at.timestamp() if node.created_at else float("inf")
    return (-heard, created, str(node.pk))


def _keeper_updates(keeper, losers):
    by_heard = sorted([keeper, *losers], key=_heard_sort_key)
    updates = {}

    heard_values = [n.last_heard for n in by_heard if n.last_heard]
    if heard_values and max(heard_values) != keeper.last_heard:
        updates["last_heard"] = max(heard_values)

    for name_field in NAME_FIELDS:
        names = (getattr(n, name_field) for n in by_heard)
        best = next((name for name in names if _is_real_name(name, keeper.meshtastic_node_id, name_field)), None)
        if best is not None and best != getattr(keeper, name_field):
            updates[name_field] = best

    for identity_field in IDENTITY_FIELDS:
        if not _is_blank(getattr(keeper, identity_field)):
            continue
        donor = next((n for n in by_heard if not _is_blank(getattr(n, identity_field))), None)
        if donor is not None:
            updates[identity_field] = getattr(donor, identity_field)

    if keeper.claimed_by_id is None:
        donor = next((n for n in by_heard if n.claimed_by_id is not None), None)
        if donor is not None:
            updates["claimed_by_id"] = donor.claimed_by_id
    return updates


def _repoint_foreign_key(related, keeper_pk, loser_pks):
    """Point rows that reference a loser at the keeper; where a unique constraint clashes the keeper's row wins."""
    model = related.related_model
    attname = related.field.attname
    rows = model._base_manager.filter(**{f"{attname}__in": loser_pks})
    try:
        with transaction.atomic():
            rows.update(**{attname: keeper_pk})
        return
    except IntegrityError:
        pass
    for pk in list(rows.values_list("pk", flat=True)):
        try:
            with transaction.atomic():
                model._base_manager.filter(pk=pk).update(**{attname: keeper_pk})
        except IntegrityError:
            model._base_manager.filter(pk=pk).delete()


def _repoint_one_to_one(related, keeper_pk, losers_by_heard):
    """Keep the keeper's row, else move the most recently heard duplicate's row across; delete the rest."""
    model = related.related_model
    attname = related.field.attname
    keeper_has_row = model._base_manager.filter(**{attname: keeper_pk}).exists()
    for loser in losers_by_heard:
        for row in list(model._base_manager.filter(**{attname: loser.pk})):
            if keeper_has_row:
                model._base_manager.filter(pk=row.pk).delete()
            else:
                model._base_manager.filter(pk=row.pk).update(**{attname: keeper_pk})
                keeper_has_row = True


def _merge_set(ObservedNode, rows):
    keeper, losers = rows[0], rows[1:]
    losers_by_heard = sorted(losers, key=_heard_sort_key)
    loser_pks = [n.pk for n in losers]
    updates = _keeper_updates(keeper, losers)
    for related in ObservedNode._meta.related_objects:
        if related.one_to_one:
            _repoint_one_to_one(related, keeper.pk, losers_by_heard)
        else:
            _repoint_foreign_key(related, keeper.pk, loser_pks)
    if updates:
        ObservedNode.objects.filter(pk=keeper.pk).update(**updates)
    ObservedNode.objects.filter(pk__in=loser_pks).delete()


def merge_duplicate_nodes(apps, schema_editor):
    ObservedNode = apps.get_model("nodes", "ObservedNode")
    node_ids = list(
        ObservedNode.objects.filter(protocol=MESHTASTIC, meshtastic_node_id__isnull=False)
        .values("meshtastic_node_id")
        .annotate(n=Count("pk"))
        .filter(n__gt=1)
        .order_by("meshtastic_node_id")
        .values_list("meshtastic_node_id", flat=True)
    )
    if not node_ids:
        return

    grouped = defaultdict(list)
    rows = ObservedNode.objects.filter(protocol=MESHTASTIC, meshtastic_node_id__in=node_ids).order_by(
        F("created_at").asc(nulls_last=True), "internal_id"
    )
    for row in rows:
        grouped[row.meshtastic_node_id].append(row)

    conflicts = []
    for node_id in node_ids:
        if len({n.claimed_by_id for n in grouped[node_id] if n.claimed_by_id is not None}) > 1:
            conflicts.append(f"!{node_id:08x}: rows have different claimed_by owners")
        else:
            _merge_set(ObservedNode, grouped[node_id])
    if conflicts:
        raise RuntimeError(
            "Cannot add the unique Meshtastic node number constraint: these duplicate ObservedNode sets cannot be "
            "merged automatically. Leave one owner per node (see docs/DEPLOY.md), then migrate again. "
            + "; ".join(conflicts)
        )

    # The deletes queue deferred foreign key checks on this table, and Postgres refuses CREATE INDEX on a table with
    # pending trigger events in the same transaction. Run the checks now. (SQLite has no such queue.)
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.connection.check_constraints()


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
