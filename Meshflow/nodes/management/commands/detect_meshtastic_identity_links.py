"""Link Meshtastic rows that are the same radio under two numbers, from the keys already in the database.

Idempotent: a second run changes nothing. The whole run is one transaction. ``--dry-run`` does the same work and
rolls it back, so it reports exactly the numbers a real run would. Only key evidence is used here (MAC evidence needs a
live on-air NodeInfo). Keys held by several nodes are never linked: each gets one flagged row naming every holder.
Run it after the deploy that adds the link table, pre-prod first. See
docs/features/packet-ingestion/adr/0006-meshtastic-identity-linking.md.
"""

from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from common.protocol import Protocol
from nodes.models import ObservedNode, ObservedNodeIdentityLink
from nodes.services.identity_links import Outcome, evaluate_key


class _Rollback(Exception):
    """Raised to end the dry-run transaction without keeping its writes."""


class Command(BaseCommand):
    help = (
        "Create identity links (old number -> new number) from stored public keys: one auto link where exactly one "
        "other node holds a key whose crc32 is the node's number, one flagged row per key held by several nodes."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report what would change; write nothing.")
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Keys per slice of the loop (default 500); the whole run is one transaction.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        batch_size = max(1, options["batch_size"])
        prefix = "[dry-run] " if dry_run else ""

        keyed = ObservedNode.objects.filter(protocol=Protocol.MESHTASTIC, meshtastic_public_key_hex__isnull=False)
        keyed_rows = keyed.count()
        shared_keys = list(
            keyed.values("meshtastic_public_key_hex")
            .annotate(holders=Count("pk"))
            .filter(holders__gt=1)
            .order_by("-holders", "meshtastic_public_key_hex")
            .values_list("meshtastic_public_key_hex", "holders")
        )

        results = Counter()
        flagged_keys = []
        state_counts = {}
        try:
            with transaction.atomic():
                for start in range(0, len(shared_keys), batch_size):
                    for key_hex, holders in shared_keys[start : start + batch_size]:
                        outcome = evaluate_key(key_hex)
                        results[outcome] += 1
                        if outcome.flagged:
                            flagged_keys.append((key_hex, holders))
                state_counts = dict(
                    ObservedNodeIdentityLink.objects.values_list("state").annotate(n=Count("pk")).order_by("state")
                )
                if dry_run:
                    raise _Rollback
        except _Rollback:
            pass

        self.stdout.write(
            f"{prefix}Scanned {keyed_rows} keyed Meshtastic rows; {len(shared_keys)} key(s) held by more than one row"
        )
        self.stdout.write(
            f"{prefix}Links created {results[Outcome.CREATED]}, promoted {results[Outcome.PROMOTED]}, "
            f"already recorded {results[Outcome.UNCHANGED] + results[Outcome.FLAGGED_UNCHANGED]}, "
            f"rejected (left alone) {results[Outcome.REJECTED]}, reverse pair (skipped) {results[Outcome.REVERSE]}, "
            f"refused by a live link {results[Outcome.CONFLICT]}"
        )
        self.stdout.write(
            f"{prefix}Flagged rows created {results[Outcome.FLAGGED_CREATED]}, "
            f"updated {results[Outcome.FLAGGED_UPDATED]}"
        )
        self.stdout.write(f"{prefix}Unlinkable (shared) keys: {len(flagged_keys)}")
        for key_hex, holders in flagged_keys[:20]:
            self.stdout.write(f"  {key_hex[:16]}...: {holders} holders")
        if len(flagged_keys) > 20:
            self.stdout.write(f"  ... and {len(flagged_keys) - 20} more")
        total = ", ".join(f"{state} {state_counts.get(state, 0)}" for state in ObservedNodeIdentityLink.State.values)
        self.stdout.write(f"{prefix}Links by state after this run: {total}")
