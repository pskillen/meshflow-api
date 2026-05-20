"""Signal handlers for traceroute side effects."""

from django.dispatch import receiver

from packets.signals import new_node_observed
from traceroute.models import AutoTraceRoute
from traceroute.new_node_baseline import enqueue_new_node_baseline


@receiver(new_node_observed)
def on_new_node_observed_enqueue_baseline_traceroute(sender, node, observer, **kwargs):
    """Queue a baseline route capture for a brand-new ObservedNode (non-DX infrastructure)."""
    enqueue_new_node_baseline(node, observer)


def on_auto_traceroute_completed_from_packet(sender, auto_tr, **kwargs):
    """Notify WebSocket clients and enqueue Neo4j export after packet-driven completion."""
    from traceroute.lifecycle import schedule_completed_traceroute_neo4j_export
    from traceroute.ws_notify import notify_traceroute_status_changed

    notify_traceroute_status_changed(auto_tr.id, AutoTraceRoute.STATUS_COMPLETED)
    schedule_completed_traceroute_neo4j_export(auto_tr.id)
