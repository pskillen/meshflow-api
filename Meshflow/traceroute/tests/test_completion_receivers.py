"""Tests for auto_traceroute_completed_from_packet traceroute receiver."""

from unittest.mock import patch

import pytest

import nodes.tests.conftest  # noqa: F401
import users.tests.conftest  # noqa: F401
from traceroute.models import AutoTraceRoute
from traceroute.receivers import on_auto_traceroute_completed_from_packet
from traceroute.tests.factories import make_auto_traceroute


@pytest.mark.django_db
def test_completion_receiver_notifies_and_schedules_neo4j(create_managed_node, create_observed_node, create_user):
    auto_tr = make_auto_traceroute(
        create_managed_node,
        create_observed_node,
        create_user,
        status=AutoTraceRoute.STATUS_COMPLETED,
    )

    with patch("traceroute.ws_notify.notify_traceroute_status_changed") as mock_notify:
        with patch("traceroute.tasks.push_traceroute_to_neo4j") as mock_task:
            on_auto_traceroute_completed_from_packet(sender=None, auto_tr=auto_tr)

    mock_notify.assert_called_once_with(auto_tr.id, AutoTraceRoute.STATUS_COMPLETED)
    mock_task.delay.assert_called_once_with(auto_tr.id)
