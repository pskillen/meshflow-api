"""Backfill ObservedNode.inferred_firmware / inferred_firmware_basis for existing Meshtastic rows.

Idempotent and batched. Safe to re-run; ``--dry-run`` writes nothing and reports what a real run would write.
A row with no evidence is left untouched (a verdict is never cleared). Reads the stored ``meshtastic_key_node_id``
and each live feeder's reported firmware, so run ``backfill_meshtastic_identity`` first in an environment that never
ran it.
"""

from collections import Counter
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from common.meshtastic_firmware import ADOPTION_WINDOW_HOURS, Evidence, classify
from common.protocol import Protocol
from nodes.models import ObservedNode
from nodes.services.node_firmware import FIRMWARE_FIELDS, apply_verdict, feeder_firmware_map


class Command(BaseCommand):
    help = (
        "Infer ObservedNode.inferred_firmware from the stored public key identity, and report how many recently "
        "active nodes have a usable key."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report what would change; write nothing.")
        parser.add_argument("--batch-size", type=int, default=500, help="Rows per batch (default 500).")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        batch_size = options["batch_size"]
        prefix = "[dry-run] " if dry_run else ""
        now = timezone.now()
        active_since = now - timedelta(hours=ADOPTION_WINDOW_HOURS)

        # One query for every key-derived id, rather than one per keyless row.
        self._key_ids = set(
            ObservedNode.objects.filter(protocol=Protocol.MESHTASTIC, meshtastic_key_node_id__isnull=False).values_list(
                "meshtastic_key_node_id", flat=True
            )
        )

        # One query for every reporting feeder, rather than one per row.
        self._feeder_firmware = feeder_firmware_map()

        scanned = updated = active = active_with_key = 0
        results = Counter()
        qs = ObservedNode.objects.filter(protocol=Protocol.MESHTASTIC).order_by("pk")
        last_pk = None
        while True:
            batch_qs = qs if last_pk is None else qs.filter(pk__gt=last_pk)
            batch = list(batch_qs[:batch_size])
            if not batch:
                break
            last_pk = batch[-1].pk

            to_update = []
            for node in batch:
                scanned += 1
                if apply_verdict(node, classify(self._evidence(node)), now=now):
                    to_update.append(node)
                    updated += 1
                if node.inferred_firmware is None:
                    results["unknown"] += 1
                else:
                    results[f"{node.inferred_firmware}/{node.inferred_firmware_basis}"] += 1
                if node.last_heard is not None and node.last_heard >= active_since:
                    active += 1
                    if node.meshtastic_key_node_id is not None:
                        active_with_key += 1
            if to_update and not dry_run:
                ObservedNode.objects.bulk_update(to_update, FIRMWARE_FIELDS)

        self.stdout.write(f"{prefix}ObservedNode: scanned {scanned}, updated {updated}")
        self.stdout.write(f"{prefix}By result: {self._format_results(results)}")
        percent = (100 * active_with_key / active) if active else 0.0
        self.stdout.write(
            f"{prefix}Active in the last {ADOPTION_WINDOW_HOURS}h: {active}, "
            f"with a usable key {active_with_key} ({percent:.1f}%)"
        )

    def _evidence(self, node):
        """What we know about one row. Kept in one place; mirrors ``nodes.services.node_firmware.build_evidence``."""
        key_id = node.meshtastic_key_node_id
        return Evidence(
            node_num=node.meshtastic_node_id,
            key_node_id=key_id,
            number_is_another_nodes_key_id=key_id is None and node.meshtastic_node_id in self._key_ids,
            feeder_firmware=self._feeder_firmware.get(node.meshtastic_node_id),
        )

    @staticmethod
    def _format_results(results):
        keys = sorted(k for k in results if k != "unknown")
        return ", ".join([f"{k} {results[k]}" for k in keys] + [f"unknown {results['unknown']}"])
