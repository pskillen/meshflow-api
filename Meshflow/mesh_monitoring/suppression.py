"""Observed nodes excluded from random auto traceroute target selection."""

from django.db.models import Q


def suppressed_observed_node_ids():
    """PKs (ObservedNode UUIDs) under active verification or offline confirmed."""
    from .models import NodePresence

    return NodePresence.objects.filter(
        Q(verification_started_at__isnull=False) | Q(offline_confirmed_at__isnull=False)
    ).values_list("observed_node_id", flat=True)
