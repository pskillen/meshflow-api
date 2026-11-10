"""Merge duplicate Meshtastic ObservedNode rows (same node number) into one.

Used by the ``dedupe_observed_nodes`` command. Migration 0059 holds a frozen copy of these rules against historical
models, so changes here do not reach it.

Rules, per duplicate set (each set merges in its own ``transaction.atomic()``):

* **Keeper**: the oldest row, ``created_at`` (nulls last) then ``internal_id`` (the same order the lookup helpers
  use, so ingest has been attaching data to the keeper all along).
* **Fields on the keeper**: ``last_heard`` is the max over the set. Each name is the first *real* one (not blank, not
  a placeholder per ``common.meshtastic_identity.is_placeholder_name``) going from the most recently heard row
  down; if no row has one, the keeper's own. Identity fields (``meshtastic_public_key``,
  ``meshtastic_public_key_hex``, ``meshtastic_key_node_id``, ``mac_addr``, ``meshtastic_hw_model``,
  ``meshtastic_role``, ``inferred_firmware``, ``inferred_firmware_basis``, ``inferred_firmware_at``) keep the
  keeper's value and are filled from another row (most recently heard first) only when the keeper's is blank.
  ``claimed_by`` is the keeper's, else filled from another row; two different owners in one set is a
  conflict and the set is left alone.
* **Relations**: every reverse relation in ``ObservedNode._meta.related_objects`` is re-pointed at the keeper.
  One-to-ones keep the keeper's row (else the row of the most recently heard duplicate moves across) and drop the
  rest. If re-pointing a foreign-key row would break a unique constraint on the related table, the keeper's row
  wins and the duplicate's row is deleted (an identity link that staff confirmed displaces a weaker clashing one).

Dry-run does the merge for real inside the set's transaction and rolls it back, so it reports exactly the numbers a
real run writes (no dry-run that reads its own unwritten changes).
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field

from django.db import IntegrityError, transaction
from django.db.models import Count, Q

from common.mesh_node_helpers import meshtastic_id_to_hex
from common.meshtastic_identity import is_placeholder_name
from common.protocol import Protocol
from nodes.models import ObservedNode, ObservedNodeIdentityLink
from nodes.services.observed_nodes import KEEPER_ORDERING

logger = logging.getLogger(__name__)

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

# Every reverse relation of ObservedNode, as "app_label.Model.field". The merge handles any relation generically
# (one-to-one: keep one row; foreign key: re-point), but a new relation may need a decision, so a test pins this set
# to ``ObservedNode._meta.related_objects`` and fails until someone has looked at it and added it here.
HANDLED_RELATIONS = frozenset(
    {
        "dx_monitoring.DxEvent.destination",
        "dx_monitoring.DxNodeMetadata.observed_node",
        "mesh_monitoring.NodeMonitoringConfig.observed_node",
        "mesh_monitoring.NodePresence.observed_node",
        "mesh_monitoring.NodeWatch.observed_node",
        "meshcore_packet_path.MeshCorePathEdgeBucket.from_node",
        "meshcore_packet_path.MeshCorePathEdgeBucket.to_node",
        "meshcore_packet_path.MeshCorePathSegmentResolution.observed_node",
        "nodes.AirQualityMetrics.node",
        "nodes.DeviceMetrics.node",
        "nodes.EnvironmentMetrics.node",
        "nodes.HealthMetrics.node",
        "nodes.HostMetrics.node",
        "nodes.NodeLatestStatus.node",
        "nodes.ObservedNodeIdentityLink.new_node",  # re-pointed; on a clash the weaker row goes
        "nodes.ObservedNodeIdentityLink.old_node",
        "nodes.NodeOwnerClaim.node",
        "nodes.NodeRfProfile.observed_node",
        "nodes.NodeRfPropagationRender.observed_node",
        "nodes.Position.node",
        "nodes.PowerMetrics.node",
        "text_messages.TextMessage.sender",
        "traceroute.AutoTraceRoute.target_node",
    }
)


def relation_label(related) -> str:
    """``app_label.Model.field`` for a reverse relation of ObservedNode."""
    return f"{related.related_model._meta.label}.{related.field.name}"


def current_relations() -> set[str]:
    return {relation_label(r) for r in ObservedNode._meta.related_objects}


@dataclass
class MergeReport:
    sets_found: int = 0
    sets_merged: int = 0
    rows_merged: int = 0  # duplicate ObservedNode rows folded into their keeper
    moved: dict[str, int] = field(default_factory=lambda: defaultdict(int))  # relation -> rows re-pointed
    dropped: dict[str, int] = field(default_factory=lambda: defaultdict(int))  # relation -> rows deleted
    conflicts: list[str] = field(default_factory=list)  # "!xxxxxxxx: reason"

    @property
    def conflicts_skipped(self) -> int:
        return len(self.conflicts)

    def as_dict(self) -> dict:
        return {
            "sets_found": self.sets_found,
            "sets_merged": self.sets_merged,
            "rows_merged": self.rows_merged,
            "moved": dict(sorted(self.moved.items())),
            "dropped": dict(sorted(self.dropped.items())),
            "conflicts": list(self.conflicts),
        }


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _is_real_name(name, node_id, name_field) -> bool:
    return not _is_blank(name) and not is_placeholder_name(name, node_id, name_field)


def _heard_sort_key(node: ObservedNode):
    """Most recently heard first; never-heard last; ties by age then pk (stable)."""
    heard = node.last_heard.timestamp() if node.last_heard else float("-inf")
    created = node.created_at.timestamp() if node.created_at else float("inf")
    return (-heard, created, str(node.pk))


def _keeper_updates(keeper: ObservedNode, losers: list[ObservedNode]) -> dict:
    """Field values to write onto the keeper (only the ones that change)."""
    by_heard = sorted([keeper, *losers], key=_heard_sort_key)
    updates = {}

    heard_values = [n.last_heard for n in by_heard if n.last_heard]
    if heard_values and max(heard_values) != keeper.last_heard:
        updates["last_heard"] = max(heard_values)

    for name_field in NAME_FIELDS:
        best = next(
            (
                getattr(n, name_field)
                for n in by_heard
                if _is_real_name(getattr(n, name_field), keeper.meshtastic_node_id, name_field)
            ),
            None,
        )
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


def _owner_conflict(rows: list[ObservedNode]) -> bool:
    return len({n.claimed_by_id for n in rows if n.claimed_by_id is not None}) > 1


def _repoint_foreign_key(related, keeper_pk, loser_pks) -> tuple[int, int]:
    """Point every row of ``related`` that references a loser at the keeper. Returns (moved, dropped)."""
    model = related.related_model
    attname = related.field.attname
    rows = model._base_manager.filter(**{f"{attname}__in": loser_pks})
    try:
        with transaction.atomic():
            return rows.update(**{attname: keeper_pk}), 0
    except IntegrityError:
        pass
    # A unique constraint on the related table clashed: go row by row; the keeper's row wins.
    moved = dropped = 0
    for pk in list(rows.values_list("pk", flat=True)):
        try:
            with transaction.atomic():
                model._base_manager.filter(pk=pk).update(**{attname: keeper_pk})
            moved += 1
        except IntegrityError:
            if _displace_for_confirmed_link(model, pk, attname, keeper_pk):
                moved += 1
                continue
            model._base_manager.filter(pk=pk).delete()
            dropped += 1
    return moved, dropped


def _displace_for_confirmed_link(model, pk, attname, keeper_pk) -> bool:
    """A staff-confirmed link that clashes with the keeper's weaker one wins: the weaker rows go, then it moves.

    Only for identity links, only for ``confirmed``, and only against rows that are not themselves confirmed.
    """
    if model is not ObservedNodeIdentityLink:
        return False
    row = model._base_manager.filter(pk=pk).first()
    if row is None or row.state != ObservedNodeIdentityLink.State.CONFIRMED:
        return False
    old_pk = keeper_pk if attname == "old_node_id" else row.old_node_id
    new_pk = keeper_pk if attname == "new_node_id" else row.new_node_id
    clash = (
        Q(old_node_id=old_pk, new_node_id=new_pk)
        | Q(state__in=ObservedNodeIdentityLink.LIVE_STATES, old_node_id=old_pk)
        | Q(state__in=ObservedNodeIdentityLink.LIVE_STATES, new_node_id=new_pk)
    )
    weaker = model._base_manager.filter(clash).exclude(pk=pk).exclude(state=ObservedNodeIdentityLink.State.CONFIRMED)
    try:
        with transaction.atomic():
            weaker.delete()
            model._base_manager.filter(pk=pk).update(**{attname: keeper_pk})
    except IntegrityError:
        return False
    return True


def _repoint_one_to_one(related, keeper_pk, losers_by_heard) -> tuple[int, int]:
    """Keep the keeper's row, else move the most recently heard duplicate's row across; delete the rest."""
    model = related.related_model
    attname = related.field.attname
    if model._base_manager.filter(**{attname: keeper_pk}).exists():
        moved = 0
    else:
        moved = None
    rows_by_loser = {pk: list(model._base_manager.filter(**{attname: pk})) for pk in (n.pk for n in losers_by_heard)}
    dropped = 0
    for loser in losers_by_heard:
        for row in rows_by_loser[loser.pk]:
            if moved is None:
                model._base_manager.filter(pk=row.pk).update(**{attname: keeper_pk})
                moved = 1
            else:
                model._base_manager.filter(pk=row.pk).delete()
                dropped += 1
    return (moved or 0), dropped


def _merge_set(node_id: int, rows: list[ObservedNode], report: MergeReport, dry_run: bool) -> None:
    label = meshtastic_id_to_hex(node_id)
    if _owner_conflict(rows):
        report.conflicts.append(f"{label}: rows have different claimed_by owners")
        logger.warning("Not merging duplicate ObservedNodes for %s: rows have different claimed_by owners", label)
        return

    keeper, losers = rows[0], rows[1:]
    losers_by_heard = sorted(losers, key=_heard_sort_key)
    loser_pks = [n.pk for n in losers]
    # Count into a local report: a failed set must leave the totals untouched.
    local = MergeReport()
    with transaction.atomic():
        updates = _keeper_updates(keeper, losers)
        for related in ObservedNode._meta.related_objects:
            if related.one_to_one:
                moved, dropped = _repoint_one_to_one(related, keeper.pk, losers_by_heard)
            else:
                moved, dropped = _repoint_foreign_key(related, keeper.pk, loser_pks)
            if moved:
                local.moved[relation_label(related)] += moved
            if dropped:
                local.dropped[relation_label(related)] += dropped
        if updates:
            ObservedNode.objects.filter(pk=keeper.pk).update(**updates)
        ObservedNode.objects.filter(pk__in=loser_pks).delete()
        if dry_run:
            transaction.set_rollback(True)

    report.sets_merged += 1
    report.rows_merged += len(losers)
    for key, value in local.moved.items():
        report.moved[key] += value
    for key, value in local.dropped.items():
        report.dropped[key] += value


def duplicate_node_ids() -> list[int]:
    """Meshtastic node numbers that have more than one ObservedNode row."""
    return sorted(
        ObservedNode.objects.filter(protocol=Protocol.MESHTASTIC, meshtastic_node_id__isnull=False)
        .values("meshtastic_node_id")
        .annotate(n=Count("pk"))
        .filter(n__gt=1)
        .values_list("meshtastic_node_id", flat=True)
    )


def merge_duplicate_meshtastic_nodes(dry_run: bool = False, batch_size: int = 500) -> MergeReport:
    """Merge every set of Meshtastic ObservedNodes sharing a node number. Idempotent."""
    report = MergeReport()
    node_ids = duplicate_node_ids()
    report.sets_found = len(node_ids)
    for start in range(0, len(node_ids), batch_size):
        batch = node_ids[start : start + batch_size]
        grouped = defaultdict(list)
        for row in ObservedNode.objects.filter(protocol=Protocol.MESHTASTIC, meshtastic_node_id__in=batch).order_by(
            *KEEPER_ORDERING
        ):
            grouped[row.meshtastic_node_id].append(row)
        for node_id in batch:
            rows = grouped.get(node_id, [])
            if len(rows) > 1:
                _merge_set(node_id, rows, report, dry_run)
    return report
