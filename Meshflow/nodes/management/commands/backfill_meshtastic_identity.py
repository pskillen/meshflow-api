"""Backfill Meshtastic identity evidence (normalised key + predicted 2.8 node id).

Idempotent and batched. Safe to re-run; ``--dry-run`` writes nothing. Run in prod straight after deploy.
See docs/features/packet-ingestion/adr/0006-meshtastic-identity-linking.md.
"""

from collections import defaultdict

from django.core.management.base import BaseCommand

from common.meshtastic_identity import identity_fields, key_node_id, normalise_pubkey
from common.protocol import Protocol
from nodes.models import ManagedNode, ObservedNode
from packets.models import NodeInfoPacket

OBSERVED_FIELDS = ("meshtastic_public_key_hex", "meshtastic_key_node_id")


class Command(BaseCommand):
    help = (
        "Fill ObservedNode.meshtastic_public_key_hex / meshtastic_key_node_id from the stored key (falling back to "
        "the latest NodeInfoPacket key), copy the key onto matching ManagedNodes, and report shared keys."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report what would change; write nothing.")
        parser.add_argument("--batch-size", type=int, default=500, help="Rows per batch (default 500).")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        batch_size = options["batch_size"]
        prefix = "[dry-run] " if dry_run else ""

        # The observed pass derives every key; the managed pass and shared-key report read that, not the database,
        # so a dry-run (which writes nothing) reports exactly what a real run would.
        index = _KeyIndex()
        observed_stats = self._backfill_observed(dry_run, batch_size, index)
        managed_stats = self._backfill_managed(dry_run, batch_size, index)

        self.stdout.write(
            f"{prefix}ObservedNode: scanned {observed_stats['scanned']}, updated {observed_stats['updated']}, "
            f"key from NodeInfoPacket fallback {observed_stats['fallback']}, no usable key {observed_stats['no_key']}"
        )
        self.stdout.write(
            f"{prefix}ManagedNode: scanned {managed_stats['scanned']}, updated {managed_stats['updated']}, "
            f"no matching observed key {managed_stats['no_key']}"
        )
        self._report_shared_keys(index)

    def _latest_packet_keys(self, node_ids):
        """Latest non-empty NodeInfoPacket.public_key per from_int, for the given node numbers."""
        found = {}
        packets = (
            NodeInfoPacket.objects.filter(from_int__in=node_ids)
            .exclude(public_key__isnull=True)
            .exclude(public_key="")
            .order_by("from_int", "-first_reported_time")
            .values_list("from_int", "public_key")
        )
        for from_int, key in packets:
            found.setdefault(from_int, key)
        return found

    def _backfill_observed(self, dry_run, batch_size, index):
        stats = {"scanned": 0, "updated": 0, "fallback": 0, "no_key": 0}
        qs = ObservedNode.objects.filter(protocol=Protocol.MESHTASTIC).order_by("pk")
        last_pk = None
        while True:
            batch_qs = qs if last_pk is None else qs.filter(pk__gt=last_pk)
            batch = list(batch_qs[:batch_size])
            if not batch:
                break
            last_pk = batch[-1].pk

            # Only nodes whose own key is unusable need the packet fallback.
            needs_fallback = [n.meshtastic_node_id for n in batch if normalise_pubkey(n.meshtastic_public_key) is None]
            fallback_keys = self._latest_packet_keys([i for i in needs_fallback if i is not None])

            to_update = []
            for node in batch:
                stats["scanned"] += 1
                source = node.meshtastic_public_key
                used_fallback = False
                if normalise_pubkey(source) is None:
                    candidate = fallback_keys.get(node.meshtastic_node_id)
                    if candidate is not None and normalise_pubkey(candidate) is not None:
                        source = candidate
                        used_fallback = True
                derived = identity_fields(source)
                index.add(node, derived["meshtastic_public_key_hex"])
                if derived["meshtastic_key_node_id"] is None:
                    stats["no_key"] += 1
                if all(getattr(node, f) == derived[f] for f in OBSERVED_FIELDS):
                    continue
                for field, value in derived.items():
                    setattr(node, field, value)
                to_update.append(node)
                stats["updated"] += 1
                if used_fallback:
                    stats["fallback"] += 1
            if to_update and not dry_run:
                ObservedNode.objects.bulk_update(to_update, list(OBSERVED_FIELDS))
        return stats

    def _backfill_managed(self, dry_run, batch_size, index):
        stats = {"scanned": 0, "updated": 0, "no_key": 0}
        qs = ManagedNode.objects.filter(protocol=Protocol.MESHTASTIC, meshtastic_node_id__isnull=False).order_by("pk")
        last_pk = None
        while True:
            batch_qs = qs if last_pk is None else qs.filter(pk__gt=last_pk)
            batch = list(batch_qs[:batch_size])
            if not batch:
                break
            last_pk = batch[-1].pk
            to_update = []
            for node in batch:
                stats["scanned"] += 1
                key_hex = index.key_for_number(node.meshtastic_node_id)
                if key_hex is None:
                    # Never clear a key we already hold just because the observed row has none.
                    stats["no_key"] += 1
                    continue
                predicted = key_node_id(key_hex)
                if node.meshtastic_public_key == key_hex and node.meshtastic_key_node_id == predicted:
                    continue
                node.meshtastic_public_key = key_hex
                node.meshtastic_key_node_id = predicted
                to_update.append(node)
                stats["updated"] += 1
            if to_update and not dry_run:
                ManagedNode.objects.bulk_update(to_update, ["meshtastic_public_key", "meshtastic_key_node_id"])
        return stats

    def _report_shared_keys(self, index):
        """Report keys held by two or more *different* Meshtastic node numbers (cloned keys, or a renumbered node).

        Duplicate ObservedNode rows for one node number (a pre-existing create race) are not a shared key; they are
        counted on their own line so they stay visible.
        """
        duplicates = index.duplicate_row_count()
        if duplicates:
            self.stdout.write(f"Duplicate ObservedNode rows (same node number, several rows): {duplicates}")
        shared = index.shared_keys()
        if not shared:
            self.stdout.write("Shared keys: none")
            return
        self.stdout.write(self.style.WARNING(f"Shared keys: {len(shared)} key(s) held by several nodes"))
        for key_hex, numbers in shared:
            labels = ", ".join(f"!{n:08x}" for n in numbers)
            self.stdout.write(f"  {key_hex[:16]}…: {len(numbers)} nodes ({labels})")


class _KeyIndex:
    """Derived keys per Meshtastic node number, built from the observed pass (pk -> hex is all it keeps per row)."""

    def __init__(self):
        # number -> (rank, key_hex or None) of the chosen row; rank prefers a set key, then latest heard, then pk.
        self._chosen = {}
        self._rows = defaultdict(int)  # number -> row count
        self._numbers_by_key = defaultdict(set)  # key_hex -> {number}

    def add(self, node, key_hex):
        number = node.meshtastic_node_id
        if number is None:
            return
        self._rows[number] += 1
        heard = node.last_heard.timestamp() if node.last_heard else float("-inf")
        rank = (key_hex is not None, heard, node.pk)
        current = self._chosen.get(number)
        if current is None or rank > current[0]:
            self._chosen[number] = (rank, key_hex)
        if key_hex is not None:
            self._numbers_by_key[key_hex].add(number)

    def key_for_number(self, number):
        chosen = self._chosen.get(number)
        return chosen[1] if chosen else None

    def duplicate_row_count(self):
        return sum(1 for count in self._rows.values() if count > 1)

    def shared_keys(self):
        shared = [(k, sorted(nums)) for k, nums in self._numbers_by_key.items() if len(nums) > 1]
        return sorted(shared, key=lambda item: (-len(item[1]), item[0]))
