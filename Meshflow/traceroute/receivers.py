"""Signal handlers for traceroute side effects."""

from django.dispatch import receiver

from packets.signals import new_node_observed
from traceroute.new_node_baseline import enqueue_new_node_baseline


@receiver(new_node_observed)
def on_new_node_observed_enqueue_baseline_traceroute(sender, node, observer, **kwargs):
    """Queue a baseline route capture for a brand-new ObservedNode (non-DX infrastructure)."""
    enqueue_new_node_baseline(node, observer)
