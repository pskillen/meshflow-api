"""
Read-only report of API keys linked to more than one active feeder.

New shared links are refused (#438); this lists the ones that still exist so they can be
replaced by one key per feeder before the legacy URLs go away. Writes nothing.
"""

from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from common.protocol import Protocol
from nodes.models import NodeAPIKey


class Command(BaseCommand):
    help = "List API keys linked to more than one active feeder (read-only)"

    def handle(self, *args, **options):
        active = Q(node_links__node__deleted_at__isnull=True)
        keys = (
            NodeAPIKey.objects.annotate(active_links=Count("node_links", filter=active, distinct=True))
            .filter(active_links__gt=1)
            .select_related("owner", "constellation")
            .order_by("name", "id")
        )

        shared = 0
        cross_protocol = 0
        for key in keys:
            links = list(
                key.node_links.filter(node__deleted_at__isnull=True).select_related("node").order_by("node__name")
            )
            protocols = {link.node.protocol for link in links}
            shared += 1
            if len(protocols) > 1:
                cross_protocol += 1

            last_used = key.last_used.isoformat() if key.last_used else "never"
            self.stdout.write(f"Key: {key.name} ({key.id})")
            self.stdout.write(f"  owner: {key.owner.username}")
            self.stdout.write(f"  constellation: {key.constellation.name}")
            self.stdout.write(f"  last_used: {last_used}")
            self.stdout.write("  feeders:")
            for link in links:
                node = link.node
                self.stdout.write(f"    - {node.name} [{node.node_id_str}] {Protocol(node.protocol).label}")

        self.stdout.write("")
        self.stdout.write(f"Keys shared by more than one feeder: {shared}")
        self.stdout.write(f"Keys linked across both protocols: {cross_protocol}")
