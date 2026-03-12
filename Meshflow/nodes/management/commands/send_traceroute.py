"""
Management command to send a traceroute command to a connected bot via the channel layer.

The bot must be connected to the WebSocket (ws/nodes/) and linked to the given
ManagedNode via NodeAPIKey. Use this to manually trigger a traceroute for testing.
"""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.management.base import BaseCommand

from nodes.models import ManagedNode, NodeAuth


class Command(BaseCommand):
    help = "Send a traceroute command to a bot connected via WebSocket"

    def add_arguments(self, parser):
        parser.add_argument(
            "target_node_id",
            type=int,
            help="Node ID of the target node to traceroute to",
        )
        parser.add_argument(
            "--managed-node-id",
            type=int,
            help="Node ID of the ManagedNode (the bot). Required unless --by-api-key is used.",
        )
        parser.add_argument(
            "--by-api-key",
            type=str,
            help="Look up managed_node_id from the NodeAPIKey (e.g. from STORAGE_API_TOKEN)",
        )

    def handle(self, *args, **options):
        target_node_id = options["target_node_id"]
        managed_node_id = options.get("managed_node_id")
        api_key = options.get("by_api_key")

        if api_key:
            node_auth = NodeAuth.objects.filter(api_key__key=api_key).select_related("node").first()
            if not node_auth:
                self.stderr.write(
                    self.style.ERROR("No NodeAuth found for API key (key may be invalid)")
                )
                return
            managed_node_id = node_auth.node.node_id
            self.stdout.write(f"Resolved managed_node_id={managed_node_id} from API key")

        if managed_node_id is None:
            self.stderr.write(
                self.style.ERROR(
                    "Provide --managed-node-id or --by-api-key to identify the bot"
                )
            )
            return

        if not ManagedNode.objects.filter(node_id=managed_node_id).exists():
            self.stderr.write(
                self.style.ERROR(
                    f"ManagedNode with node_id={managed_node_id} not found. "
                    "Ensure the node exists and is linked to a NodeAPIKey."
                )
            )
            return

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"node_{managed_node_id}",
            {"type": "node_command", "command": {"type": "traceroute", "target": target_node_id}},
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Sent traceroute command to group node_{managed_node_id}: "
                f"target={target_node_id}"
            )
        )
        self.stdout.write(
            "Tip: If the bot did not receive it, ensure managed_node_id matches the "
            "ManagedNode.node_id linked to the bot's API key. Check API logs when the "
            "bot connects for 'bot connected for node X'."
        )
