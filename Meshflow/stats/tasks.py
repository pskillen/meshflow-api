"""Celery tasks for stats snapshot collection."""

import datetime as dt
import logging
import os
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional

from django.db.models import Count, Exists, Min, OuterRef, Q
from django.db.models.functions import Coalesce, Substr, TruncDate
from django.utils import timezone

from celery import shared_task
from tqdm import tqdm

from common.meshtastic_firmware import (
    ADOPTION_WINDOW_HOURS,
    BASIS_FEEDER_REPORT,
    BASIS_KEY_IDENTITY,
    BASIS_PREDICTED_ID,
)
from common.protocol import Protocol
from constellations.models import Constellation
from meshcore_packets.models import MeshCorePacketObservation, MeshCorePayloadType, MeshCoreRawPacket
from nodes.models import ObservedNode
from packets.models import MtRawPacket, PacketObservation

from .models import StatsSnapshot

logger = logging.getLogger(__name__)

ONLINE_NODE_WINDOW_HOURS = int(os.environ.get("ONLINE_NODE_WINDOW_HOURS", "2"))


def _get_last_run_started_at(stat_type: str) -> Optional[datetime]:
    """Return the recorded_at of the most recent global snapshot for stat_type, or None."""
    last = (
        StatsSnapshot.objects.filter(stat_type=stat_type, constellation__isnull=True)
        .order_by("-recorded_at")
        .values("recorded_at")
        .first()
    )
    return last["recorded_at"] if last else None


def _snapshot_exists(recorded_at: datetime, stat_type: str, constellation_id: Optional[int]) -> bool:
    """Check if a snapshot already exists. Used for idempotent backfill."""
    qs = StatsSnapshot.objects.filter(recorded_at=recorded_at, stat_type=stat_type)
    if constellation_id is None:
        qs = qs.filter(constellation__isnull=True)
    else:
        qs = qs.filter(constellation_id=constellation_id)
    return qs.exists()


def _online_window(recorded_at: datetime) -> tuple[datetime, datetime]:
    """
    The closed window an online snapshot counts: ONLINE_NODE_WINDOW_HOURS long, centred on recorded_at.

    recorded_at is the start of the hour the point is plotted at, so with the default 2 h the point at H
    counts [H - 1h, H + 1h]. That includes the hour just finished (H to H + 1h), the same hour the
    packet-volume point at H covers, and the job only runs once that hour is complete.
    """
    half = timedelta(hours=ONLINE_NODE_WINDOW_HOURS) / 2
    return recorded_at - half, recorded_at + half


def _mt_online_count(recorded_at: datetime, constellation: Optional[Constellation] = None) -> int:
    """
    Distinct Meshtastic senders heard in the online window around recorded_at (see _online_window).

    Counted from packets, not ObservedNode.last_heard: last_heard only moves forward, so a node heard
    again after recorded_at would drop out of a last_heard upper bound. Packets whose only observations
    are 2.8 connect-time replays are ignored. Any transport (RF or MQTT) counts as heard.
    """
    start, end = _online_window(recorded_at)
    # Two time bases: the global count uses first_reported_time (this API's clock when the packet was first
    # stored), the constellation count uses rx_time (the feeder's clock). They differ by feeder clock skew
    # and upload delay, so the constellation counts need not sum to the global one.
    if constellation is None:
        return (
            MtRawPacket.objects.filter(
                from_int__isnull=False,
                first_reported_time__gte=start,
                first_reported_time__lte=end,
            )
            .filter(Exists(PacketObservation.objects.filter(packet_id=OuterRef("id"), replayed=False)))
            .values("from_int")
            .distinct()
            .count()
        )
    return (
        PacketObservation.objects.filter(
            observer__constellation=constellation,
            packet__from_int__isnull=False,
            rx_time__gte=start,
            rx_time__lte=end,
            replayed=False,
        )
        .values("packet__from_int")
        .distinct()
        .count()
    )


def _collect_online_nodes(
    recorded_at: datetime,
    *,
    run_id: Optional[uuid.UUID] = None,
    skip_existing: bool = False,
) -> tuple[int, int]:
    """
    Collect online_nodes snapshots (hourly) for global and per-constellation: nodes heard in the
    ONLINE_NODE_WINDOW_HOURS centred on recorded_at (see _online_window, _mt_online_count). Returns (created, skipped).
    """
    created = 0
    skipped = 0

    if skip_existing and _snapshot_exists(recorded_at, "online_nodes", None):
        skipped += 1
    else:
        StatsSnapshot.objects.create(
            recorded_at=recorded_at,
            stat_type="online_nodes",
            constellation=None,
            value={"count": _mt_online_count(recorded_at), "window_hours": ONLINE_NODE_WINDOW_HOURS},
            run_id=run_id,
        )
        created += 1

    for constellation in Constellation.objects.all():
        if skip_existing and _snapshot_exists(recorded_at, "online_nodes", constellation.id):
            skipped += 1
        else:
            StatsSnapshot.objects.create(
                recorded_at=recorded_at,
                stat_type="online_nodes",
                constellation=constellation,
                value={"count": _mt_online_count(recorded_at, constellation), "window_hours": ONLINE_NODE_WINDOW_HOURS},
                run_id=run_id,
            )
            created += 1

    return (created, skipped)


PACKET_TYPE_FILTERS = {
    "text_message": Q(messagepacket__isnull=False),
    "position": Q(positionpacket__isnull=False),
    "node_info": Q(nodeinfopacket__isnull=False),
    "device_metrics": Q(devicemetricspacket__isnull=False),
    "local_stats": Q(localstatspacket__isnull=False),
    "environment_metrics": Q(environmentmetricspacket__isnull=False),
    "traceroute": Q(traceroutepacket__isnull=False),
}


def _collect_packet_volume(
    recorded_at: datetime,
    *,
    run_id: Optional[uuid.UUID] = None,
    skip_existing: bool = False,
) -> tuple[int, int]:
    """
    Collect packet_volume snapshot (hourly) for global - count of MtRawPacket rows in the hour,
    with per-type breakdown. Returns (created, skipped).
    """
    if skip_existing and _snapshot_exists(recorded_at, "packet_volume", None):
        return (0, 1)

    hour_end = recorded_at + timedelta(hours=1)
    # A packet whose only observations are 2.8 connect-time replays is not counted.
    base_qs = MtRawPacket.objects.filter(
        first_reported_time__gte=recorded_at,
        first_reported_time__lt=hour_end,
    ).filter(Exists(PacketObservation.objects.filter(packet_id=OuterRef("id"), replayed=False)))
    # Exclude device metrics that were only observed by the sender (self-ingested)
    base_qs = base_qs.exclude(
        Q(devicemetricspacket__isnull=False)
        & ~Exists(
            PacketObservation.objects.filter(packet_id=OuterRef("id"), replayed=False).exclude(
                observer__meshtastic_node_id=OuterRef("from_int")
            )
        )
    )

    annotate_kwargs = {f"_{k}": Count("id", filter=v) for k, v in PACKET_TYPE_FILTERS.items()}
    agg = base_qs.aggregate(**annotate_kwargs)

    by_type = {k: agg[f"_{k}"] for k in PACKET_TYPE_FILTERS}
    total = base_qs.count()

    StatsSnapshot.objects.create(
        recorded_at=recorded_at,
        stat_type="packet_volume",
        constellation=None,
        value={"count": total, "by_type": by_type},
        run_id=run_id,
    )
    return (1, 0)


def _collect_new_nodes(
    recorded_at: datetime,
    *,
    run_id: Optional[uuid.UUID] = None,
    skip_existing: bool = False,
    last_run_started_at: Optional[datetime] = None,
    for_backfill: bool = False,
) -> tuple[int, int]:
    """
    Collect new_nodes snapshots for global and per-constellation.
    Returns (created, skipped).

    When for_backfill=True: counts nodes with created_at in [recorded_at, recorded_at+1h).
    When for_backfill=False: counts nodes with created_at >= last_run_started_at (delta since last run).
    """
    hour_end = recorded_at + timedelta(hours=1)
    created = 0
    skipped = 0

    if for_backfill:
        # Hour window: nodes created in [recorded_at, hour_end)
        global_filter = {"created_at__gte": recorded_at, "created_at__lt": hour_end}

        def per_constellation_filter(obs_node_ids):
            return ObservedNode.objects.filter(
                protocol=Protocol.MESHTASTIC,
                meshtastic_node_id__in=obs_node_ids,
                created_at__gte=recorded_at,
                created_at__lt=hour_end,
            )

    else:
        # Delta since last run
        if last_run_started_at is not None:
            global_filter = {"created_at__gte": last_run_started_at}

            def per_constellation_filter(obs_node_ids):
                return ObservedNode.objects.filter(
                    protocol=Protocol.MESHTASTIC,
                    meshtastic_node_id__in=obs_node_ids,
                    created_at__gte=last_run_started_at,
                )

        else:
            global_filter = {"created_at__isnull": False}

            def per_constellation_filter(obs_node_ids):
                return ObservedNode.objects.filter(
                    protocol=Protocol.MESHTASTIC,
                    meshtastic_node_id__in=obs_node_ids,
                    created_at__isnull=False,
                )

    # Global
    if skip_existing and _snapshot_exists(recorded_at, "new_nodes", None):
        skipped += 1
    else:
        count = ObservedNode.objects.filter(protocol=Protocol.MESHTASTIC, **global_filter).count()
        StatsSnapshot.objects.create(
            recorded_at=recorded_at,
            stat_type="new_nodes",
            constellation=None,
            value={"count": count},
            run_id=run_id,
        )
        created += 1

    # Per-constellation
    for constellation in Constellation.objects.all():
        if skip_existing and _snapshot_exists(recorded_at, "new_nodes", constellation.id):
            skipped += 1
        else:
            if for_backfill:
                observed_node_ids = (
                    PacketObservation.objects.filter(observer__constellation=constellation, replayed=False)
                    .values_list("packet__from_int", flat=True)
                    .distinct()
                )
            else:
                if last_run_started_at is not None:
                    observed_node_ids = (
                        PacketObservation.objects.filter(
                            observer__constellation=constellation,
                            rx_time__gte=last_run_started_at,
                            replayed=False,
                        )
                        .values_list("packet__from_int", flat=True)
                        .distinct()
                    )
                else:
                    observed_node_ids = (
                        PacketObservation.objects.filter(observer__constellation=constellation, replayed=False)
                        .values_list("packet__from_int", flat=True)
                        .distinct()
                    )
            count = per_constellation_filter(observed_node_ids).count()
            StatsSnapshot.objects.create(
                recorded_at=recorded_at,
                stat_type="new_nodes",
                constellation=constellation,
                value={"count": count},
                run_id=run_id,
            )
            created += 1

    return (created, skipped)


MC_PACKET_TYPE_FILTERS = {
    "advert": Q(payload_type=MeshCorePayloadType.ADVERT),
    "channel_text": Q(payload_type=MeshCorePayloadType.CHANNEL_TEXT),
    "contact_text": Q(payload_type=MeshCorePayloadType.CONTACT_TEXT),
    "raw": Q(payload_type=MeshCorePayloadType.RAW),
}


def _mc_sender_key():
    """
    Identity of a MeshCore sender: the 12-hex pubkey prefix. from_pubkey is nullable (contact texts and
    some adverts carry only the prefix, and those still advance last_heard), so key on the prefix of the
    full key where there is one, else the stored prefix.
    """
    return Coalesce(Substr("from_pubkey", 1, 12), "from_pubkey_prefix")


def _mc_online_count(recorded_at: datetime, constellation: Optional[Constellation] = None) -> int:
    """Distinct MeshCore senders heard in the online window around recorded_at; see _mt_online_count."""
    start, end = _online_window(recorded_at)
    if constellation is None:
        return (
            MeshCoreRawPacket.objects.filter(first_reported_time__gte=start, first_reported_time__lte=end)
            .annotate(_sender=_mc_sender_key())
            .filter(_sender__isnull=False)
            .values("_sender")
            .distinct()
            .count()
        )
    return (
        MeshCorePacketObservation.objects.filter(
            observer__constellation=constellation,
            rx_time__gte=start,
            rx_time__lte=end,
        )
        .annotate(_sender=Coalesce(Substr("packet__from_pubkey", 1, 12), "packet__from_pubkey_prefix"))
        .filter(_sender__isnull=False)
        .values("_sender")
        .distinct()
        .count()
    )


def _collect_mc_online_nodes(
    recorded_at: datetime,
    *,
    run_id: Optional[uuid.UUID] = None,
    skip_existing: bool = False,
) -> tuple[int, int]:
    """Collect mc_online_nodes snapshots (hourly) for global and per-constellation."""
    created = 0
    skipped = 0

    if skip_existing and _snapshot_exists(recorded_at, "mc_online_nodes", None):
        skipped += 1
    else:
        StatsSnapshot.objects.create(
            recorded_at=recorded_at,
            stat_type="mc_online_nodes",
            constellation=None,
            value={"count": _mc_online_count(recorded_at), "window_hours": ONLINE_NODE_WINDOW_HOURS},
            run_id=run_id,
        )
        created += 1

    for constellation in Constellation.objects.all():
        if skip_existing and _snapshot_exists(recorded_at, "mc_online_nodes", constellation.id):
            skipped += 1
        else:
            StatsSnapshot.objects.create(
                recorded_at=recorded_at,
                stat_type="mc_online_nodes",
                constellation=constellation,
                value={
                    "count": _mc_online_count(recorded_at, constellation),
                    "window_hours": ONLINE_NODE_WINDOW_HOURS,
                },
                run_id=run_id,
            )
            created += 1

    return (created, skipped)


def _collect_mc_packet_volume(
    recorded_at: datetime,
    *,
    run_id: Optional[uuid.UUID] = None,
    skip_existing: bool = False,
) -> tuple[int, int]:
    """Collect mc_packet_volume snapshot (hourly, global) for MeshCore raw packets."""
    if skip_existing and _snapshot_exists(recorded_at, "mc_packet_volume", None):
        return (0, 1)

    hour_end = recorded_at + timedelta(hours=1)
    base_qs = MeshCoreRawPacket.objects.filter(
        first_reported_time__gte=recorded_at,
        first_reported_time__lt=hour_end,
    )

    annotate_kwargs = {f"_{k}": Count("id", filter=v) for k, v in MC_PACKET_TYPE_FILTERS.items()}
    agg = base_qs.aggregate(**annotate_kwargs)

    by_type = {k: agg[f"_{k}"] for k in MC_PACKET_TYPE_FILTERS}
    total = base_qs.count()

    StatsSnapshot.objects.create(
        recorded_at=recorded_at,
        stat_type="mc_packet_volume",
        constellation=None,
        value={"count": total, "by_type": by_type},
        run_id=run_id,
    )
    return (1, 0)


def _collect_mc_new_nodes(
    recorded_at: datetime,
    *,
    run_id: Optional[uuid.UUID] = None,
    skip_existing: bool = False,
    last_run_started_at: Optional[datetime] = None,
    for_backfill: bool = False,
) -> tuple[int, int]:
    """Collect mc_new_nodes snapshots for global and per-constellation."""
    hour_end = recorded_at + timedelta(hours=1)
    created = 0
    skipped = 0

    if for_backfill:
        global_filter = {"created_at__gte": recorded_at, "created_at__lt": hour_end}

        def per_constellation_filter(pubkeys):
            return ObservedNode.objects.filter(
                protocol=Protocol.MESHCORE,
                mc_pubkey__in=pubkeys,
                created_at__gte=recorded_at,
                created_at__lt=hour_end,
            )

    else:
        if last_run_started_at is not None:
            global_filter = {"created_at__gte": last_run_started_at}

            def per_constellation_filter(pubkeys):
                return ObservedNode.objects.filter(
                    protocol=Protocol.MESHCORE,
                    mc_pubkey__in=pubkeys,
                    created_at__gte=last_run_started_at,
                )

        else:
            global_filter = {"created_at__isnull": False}

            def per_constellation_filter(pubkeys):
                return ObservedNode.objects.filter(
                    protocol=Protocol.MESHCORE,
                    mc_pubkey__in=pubkeys,
                    created_at__isnull=False,
                )

    if skip_existing and _snapshot_exists(recorded_at, "mc_new_nodes", None):
        skipped += 1
    else:
        count = ObservedNode.objects.filter(protocol=Protocol.MESHCORE, **global_filter).count()
        StatsSnapshot.objects.create(
            recorded_at=recorded_at,
            stat_type="mc_new_nodes",
            constellation=None,
            value={"count": count},
            run_id=run_id,
        )
        created += 1

    for constellation in Constellation.objects.all():
        if skip_existing and _snapshot_exists(recorded_at, "mc_new_nodes", constellation.id):
            skipped += 1
        else:
            if for_backfill:
                observed_pubkeys = (
                    MeshCorePacketObservation.objects.filter(observer__constellation=constellation)
                    .values_list("packet__from_pubkey", flat=True)
                    .distinct()
                )
            else:
                if last_run_started_at is not None:
                    observed_pubkeys = (
                        MeshCorePacketObservation.objects.filter(
                            observer__constellation=constellation,
                            rx_time__gte=last_run_started_at,
                        )
                        .values_list("packet__from_pubkey", flat=True)
                        .distinct()
                    )
                else:
                    observed_pubkeys = (
                        MeshCorePacketObservation.objects.filter(observer__constellation=constellation)
                        .values_list("packet__from_pubkey", flat=True)
                        .distinct()
                    )
            count = per_constellation_filter(observed_pubkeys).count()
            StatsSnapshot.objects.create(
                recorded_at=recorded_at,
                stat_type="mc_new_nodes",
                constellation=constellation,
                value={"count": count},
                run_id=run_id,
            )
            created += 1

    return (created, skipped)


NODE_FIRMWARE_STAT = "node_firmware"

UNKNOWN_FIRMWARE = "unknown"
NO_BASIS = "none"


def _node_firmware_value(rows) -> dict:
    """
    Build the node_firmware snapshot value from (firmware, basis, count) rows.

    by_type keys are open (a new generation appears without an API change); null firmware is "unknown".
    by_basis seeds the known bases at 0; feeder_report is written as "reported" and null as "none".
    """
    by_type: dict[str, int] = {}
    by_basis: dict[str, int] = {
        BASIS_KEY_IDENTITY: 0,
        BASIS_PREDICTED_ID: 0,
        "reported": 0,
        NO_BASIS: 0,
    }
    total = 0
    for firmware, basis, count in rows:
        type_key = firmware or UNKNOWN_FIRMWARE
        if basis is None:
            basis_key = NO_BASIS
        elif basis == BASIS_FEEDER_REPORT:
            basis_key = "reported"
        else:
            basis_key = basis
        by_type[type_key] = by_type.get(type_key, 0) + count
        by_basis[basis_key] = by_basis.get(basis_key, 0) + count
        total += count
    return {
        "count": total,
        "window_hours": ADOPTION_WINDOW_HOURS,
        "by_type": by_type,
        "by_basis": by_basis,
    }


def _collect_node_firmware(
    recorded_at: datetime,
    *,
    run_id: Optional[uuid.UUID] = None,
    skip_existing: bool = False,
) -> tuple[int, int]:
    """
    Collect the daily global node_firmware snapshot. Returns (created, skipped).

    recorded_at is midnight UTC of the day it runs. The window has no upper bound on last_heard:
    last_heard only moves forward, so a bound would drop nodes heard just after midnight.
    """
    if skip_existing and _snapshot_exists(recorded_at, NODE_FIRMWARE_STAT, None):
        return (0, 1)
    rows = (
        ObservedNode.objects.filter(
            protocol=Protocol.MESHTASTIC,
            last_heard__gte=recorded_at - timedelta(hours=ADOPTION_WINDOW_HOURS),
        )
        .values("inferred_firmware", "inferred_firmware_basis")
        .annotate(n=Count("internal_id"))
        .values_list("inferred_firmware", "inferred_firmware_basis", "n")
    )
    StatsSnapshot.objects.create(
        recorded_at=recorded_at,
        stat_type=NODE_FIRMWARE_STAT,
        constellation=None,
        value=_node_firmware_value(rows),
        run_id=run_id,
    )
    return (1, 0)


def backfill_node_firmware_snapshots(days: int = 90, dry_run: bool = False) -> dict:
    """
    Backfill daily node_firmware snapshots for the last ``days`` midnights (UTC), idempotently.

    One query against MtRawPacket gives the (day, from_int) pairs; active sets are unioned in Python.
    History uses today's classification of each node.
    """
    if days < 1:
        return {"created": 0, "skipped": 0, "scanned": 0, "scan_seconds": 0.0, "dry_run": dry_run}
    utc = dt.timezone.utc
    end = timezone.now().astimezone(utc).replace(hour=0, minute=0, second=0, microsecond=0)
    targets = [end - timedelta(days=i) for i in range(days - 1, -1, -1)]
    window_days = ADOPTION_WINDOW_HOURS // 24
    scan_start = targets[0] - timedelta(days=window_days)

    started = time.monotonic()
    nodes_by_day: dict = {}
    scanned = 0
    pairs = (
        MtRawPacket.objects.filter(first_reported_time__gte=scan_start, first_reported_time__lt=end)
        # A packet whose only observations are 2.8 connect-time replays is not node activity.
        .filter(Exists(PacketObservation.objects.filter(packet_id=OuterRef("id"), replayed=False)))
        .annotate(day=TruncDate("first_reported_time", tzinfo=utc))
        .values_list("day", "from_int")
        .distinct()
        .iterator(chunk_size=5000)
    )
    for day, from_int in pairs:
        nodes_by_day.setdefault(day, set()).add(from_int)
        scanned += 1
    scan_seconds = time.monotonic() - started

    classification: dict = {}
    for node_id, firmware, basis in ObservedNode.objects.filter(protocol=Protocol.MESHTASTIC).values_list(
        "meshtastic_node_id", "inferred_firmware", "inferred_firmware_basis"
    ):
        if node_id is None:
            continue
        if node_id not in classification or (classification[node_id][0] is None and firmware is not None):
            classification[node_id] = (firmware, basis)

    run_id = uuid.uuid4()
    created = 0
    skipped = 0
    for target in targets:
        if _snapshot_exists(target, NODE_FIRMWARE_STAT, None):
            skipped += 1
            continue
        created += 1
        if dry_run:
            continue
        active: set = set()
        for offset in range(1, window_days + 1):
            active |= nodes_by_day.get((target - timedelta(days=offset)).date(), set())
        counts: dict = {}
        for node_id in active:
            key = classification.get(node_id, (None, None))
            counts[key] = counts.get(key, 0) + 1
        StatsSnapshot.objects.create(
            recorded_at=target,
            stat_type=NODE_FIRMWARE_STAT,
            constellation=None,
            value=_node_firmware_value((fw, basis, n) for (fw, basis), n in counts.items()),
            run_id=run_id,
        )

    return {
        "created": created,
        "skipped": skipped,
        "scanned": scanned,
        "scan_seconds": scan_seconds,
        "dry_run": dry_run,
    }


@shared_task
def collect_stats_snapshots():
    """
    Run periodically (hourly). Collect Meshtastic and MeshCore snapshot types for the
    completed previous hour (global and per-constellation where applicable).

    Records the *completed* previous hour (not the current hour), since the current hour
    has only just started when this runs at minute 5.
    """
    run_id = uuid.uuid4()
    current_hour = timezone.now().replace(minute=0, second=0, microsecond=0)
    hour_start = current_hour - timedelta(hours=1)  # Record completed previous hour
    last_run_mt = _get_last_run_started_at("new_nodes")
    last_run_mc = _get_last_run_started_at("mc_new_nodes")

    created = 0
    c, _ = _collect_online_nodes(hour_start, run_id=run_id)
    created += c
    c, _ = _collect_packet_volume(hour_start, run_id=run_id)
    created += c
    c, _ = _collect_new_nodes(hour_start, run_id=run_id, last_run_started_at=last_run_mt)
    created += c
    c, _ = _collect_mc_online_nodes(hour_start, run_id=run_id)
    created += c
    c, _ = _collect_mc_packet_volume(hour_start, run_id=run_id)
    created += c
    c, _ = _collect_mc_new_nodes(hour_start, run_id=run_id, last_run_started_at=last_run_mc)
    created += c
    # Every run, so a late or failed 00:05 run does not lose the day; skip_existing makes it once a day.
    c, _ = _collect_node_firmware(current_hour.replace(hour=0), run_id=run_id, skip_existing=True)
    created += c

    logger.info(
        "collect_stats_snapshots: completed run_id=%s, created=%d",
        run_id,
        created,
    )
    return {"created": created, "run_id": str(run_id)}


@shared_task
def backfill_stats_snapshots(days: int = 30):
    """
    Backfill Meshtastic and MeshCore stats snapshots for the last N days.
    Idempotent: skips hours that already have snapshots (when run sequentially).
    """
    now = timezone.now()
    run_id = uuid.uuid4()
    end_hour = now.replace(minute=0, second=0, microsecond=0)
    start_hour = end_hour - timedelta(days=days)

    created = 0
    skipped = 0
    total_hours = int((end_hour - start_hour).total_seconds() / 3600)

    for i in tqdm(range(total_hours), unit="stats", desc="Backfilling stats"):
        hour = start_hour + timedelta(hours=i)
        c, s = _collect_online_nodes(hour, run_id=run_id, skip_existing=True)
        created += c
        skipped += s

        c2, s2 = _collect_packet_volume(hour, run_id=run_id, skip_existing=True)
        created += c2
        skipped += s2

        c3, s3 = _collect_new_nodes(hour, run_id=run_id, skip_existing=True, for_backfill=True)
        created += c3
        skipped += s3

        c4, s4 = _collect_mc_online_nodes(hour, run_id=run_id, skip_existing=True)
        created += c4
        skipped += s4

        c5, s5 = _collect_mc_packet_volume(hour, run_id=run_id, skip_existing=True)
        created += c5
        skipped += s5

        c6, s6 = _collect_mc_new_nodes(hour, run_id=run_id, skip_existing=True, for_backfill=True)
        created += c6
        skipped += s6

    logger.info(
        "Finished backfilling stats snapshots for the last %d days: created=%d, skipped=%d",
        days,
        created,
        skipped,
    )
    return {"created": created, "skipped": skipped, "days": days}


ONLINE_SNAPSHOT_TYPES = {
    "online_nodes": (MtRawPacket, _mt_online_count),
    "mc_online_nodes": (MeshCoreRawPacket, _mc_online_count),
}


@shared_task
def rewrite_online_node_snapshots(days: int = 30, dry_run: bool = False):
    """
    Recompute the count of existing online_nodes / mc_online_nodes rows from raw packets, using the
    bounded window centred on recorded_at (see _online_window).

    Rewrites rows in place and never inserts: an hour with no row stays without one (the snapshot gap is
    accepted). A row is only rewritten when raw packets cover its whole window, i.e. the oldest raw packet
    of that protocol is at or before the window start; otherwise (packets pruned or never stored) it is
    left as it is, since recomputing would undercount or turn real history into zero. Idempotent: a second
    run changes nothing. Returns the counts and `earliest_corrected`, the first hour whose value changed.
    """
    end_hour = timezone.now().replace(minute=0, second=0, microsecond=0)
    start_hour = end_hour - timedelta(days=days)

    rewritten = unchanged = left_alone = 0
    earliest_corrected: Optional[datetime] = None
    earliest_covered: Optional[datetime] = None
    # One Min per protocol: where raw packets begin. A window starting before that is only partly covered.
    oldest_raw = {
        stat_type: raw_model.objects.aggregate(oldest=Min("first_reported_time"))["oldest"]
        for stat_type, (raw_model, _) in ONLINE_SNAPSHOT_TYPES.items()
    }

    rows = (
        StatsSnapshot.objects.filter(
            stat_type__in=ONLINE_SNAPSHOT_TYPES, recorded_at__gte=start_hour, recorded_at__lt=end_hour
        )
        .select_related("constellation")
        .order_by("recorded_at")
    )
    for row in tqdm(rows.iterator(), unit="rows", desc="Rewriting online snapshots"):
        raw_model, count_fn = ONLINE_SNAPSHOT_TYPES[row.stat_type]
        oldest = oldest_raw[row.stat_type]
        if oldest is None or oldest > _online_window(row.recorded_at)[0]:
            left_alone += 1
            continue
        if earliest_covered is None:
            earliest_covered = row.recorded_at

        new_count = count_fn(row.recorded_at, row.constellation)
        if row.value.get("count") == new_count and row.value.get("window_hours") == ONLINE_NODE_WINDOW_HOURS:
            unchanged += 1
            continue
        if earliest_corrected is None or row.recorded_at < earliest_corrected:
            earliest_corrected = row.recorded_at
        rewritten += 1
        if not dry_run:
            row.value = {**row.value, "count": new_count, "window_hours": ONLINE_NODE_WINDOW_HOURS}
            row.save(update_fields=["value"])

    logger.info(
        "rewrite_online_node_snapshots: days=%d dry_run=%s rewritten=%d unchanged=%d left_alone=%d",
        days,
        dry_run,
        rewritten,
        unchanged,
        left_alone,
    )
    return {
        "rewritten": rewritten,
        "unchanged": unchanged,
        "left_alone": left_alone,
        "earliest_corrected": earliest_corrected.isoformat() if earliest_corrected else None,
        "earliest_covered": earliest_covered.isoformat() if earliest_covered else None,
        "days": days,
        "dry_run": dry_run,
    }
