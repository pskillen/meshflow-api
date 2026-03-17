"""Reusable service for environment metrics queries."""

from datetime import datetime
from typing import Optional

from django.utils import timezone

from nodes.models import EnvironmentMetrics


def get_environment_metrics_bulk(
    node_ids: list[int],
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
):
    """
    Return EnvironmentMetrics for multiple nodes in one query.

    Reusable by any endpoint that needs bulk environment metrics (weather page, etc.).

    Args:
        node_ids: List of ObservedNode.node_id values to filter by.
        start_date: Optional start of date range (inclusive).
        end_date: Optional end of date range (inclusive).

    Returns:
        QuerySet of EnvironmentMetrics ordered by node_id, reported_time.
    """
    if not node_ids:
        return EnvironmentMetrics.objects.none()

    qs = EnvironmentMetrics.objects.filter(node__node_id__in=node_ids).select_related("node")

    if start_date:
        if timezone.is_naive(start_date):
            start_date = timezone.make_aware(start_date)
        qs = qs.filter(reported_time__gte=start_date)
    if end_date:
        if timezone.is_naive(end_date):
            end_date = timezone.make_aware(end_date)
        qs = qs.filter(reported_time__lte=end_date)

    return qs.order_by("node__node_id", "reported_time")
