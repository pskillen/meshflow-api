"""Cascade behaviour for schedule_traceroutes (meshflow-api#196)."""

import logging
from unittest.mock import MagicMock, patch

import pytest

import nodes.tests.conftest  # noqa: F401
import packets.tests.conftest  # noqa: F401
from traceroute.models import AutoTraceRoute
from traceroute.tasks import dispatch_pending_traceroutes, schedule_traceroutes


@pytest.mark.django_db
def test_first_strategy_wins_records_strategy(
    monkeypatch,
    create_managed_node,
    create_packet_observation,
    create_observed_node,
):
    monkeypatch.setenv("SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS", "600")
    mn = create_managed_node(allow_auto_traceroute=True)
    create_packet_observation(observer=mn)
    target = create_observed_node(node_id=999888777)

    channel_layer = MagicMock()

    def immediate_async_to_sync(async_func):
        return async_func

    with patch("traceroute.dispatch.notify_traceroute_status_changed"):
        with patch("traceroute.dispatch.async_to_sync", side_effect=immediate_async_to_sync):
            with patch("traceroute.dispatch.get_channel_layer", return_value=channel_layer):
                with patch("traceroute.tasks.eligible_traceroute_sources_ordered", return_value=[mn]):
                    with patch(
                        "traceroute.tasks.ordered_strategies_for_feeder",
                        return_value=[AutoTraceRoute.TARGET_STRATEGY_DX_ACROSS],
                    ):
                        with patch("traceroute.tasks.pick_traceroute_target", return_value=target):
                            with patch("traceroute.tasks.record_strategy_run") as rec:
                                assert schedule_traceroutes() == {"created": 1}
                                assert dispatch_pending_traceroutes()["dispatched"] == 1

    rec.assert_called_once_with(mn, AutoTraceRoute.TARGET_STRATEGY_DX_ACROSS)
    tr = AutoTraceRoute.objects.get()
    assert tr.status == AutoTraceRoute.STATUS_SENT
    assert tr.target_strategy == AutoTraceRoute.TARGET_STRATEGY_DX_ACROSS


@pytest.mark.django_db
def test_strategy_cascade_then_legacy_skips_record_strategy_run(
    monkeypatch,
    create_managed_node,
    create_packet_observation,
    create_observed_node,
):
    monkeypatch.setenv("SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS", "600")
    mn = create_managed_node(allow_auto_traceroute=True)
    create_packet_observation(observer=mn)
    target = create_observed_node(node_id=444555666)

    channel_layer = MagicMock()

    def immediate_async_to_sync(async_func):
        return async_func

    with patch("traceroute.dispatch.notify_traceroute_status_changed"):
        with patch("traceroute.dispatch.async_to_sync", side_effect=immediate_async_to_sync):
            with patch("traceroute.dispatch.get_channel_layer", return_value=channel_layer):
                with patch("traceroute.tasks.eligible_traceroute_sources_ordered", return_value=[mn]):
                    with patch(
                        "traceroute.tasks.ordered_strategies_for_feeder",
                        return_value=[
                            AutoTraceRoute.TARGET_STRATEGY_INTRA_ZONE,
                            AutoTraceRoute.TARGET_STRATEGY_DX_ACROSS,
                        ],
                    ):
                        with patch(
                            "traceroute.tasks.pick_traceroute_target",
                            side_effect=[None, None, target],
                        ):
                            with patch("traceroute.tasks.record_strategy_run") as rec:
                                assert schedule_traceroutes() == {"created": 1}
                                assert dispatch_pending_traceroutes()["dispatched"] == 1

    rec.assert_not_called()
    tr = AutoTraceRoute.objects.get()
    assert tr.target_strategy == AutoTraceRoute.TARGET_STRATEGY_LEGACY


@pytest.mark.django_db
def test_total_failure_logs_attempts(
    monkeypatch,
    create_managed_node,
    create_packet_observation,
    caplog,
):
    monkeypatch.setenv("SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS", "600")
    mn1 = create_managed_node(allow_auto_traceroute=True, node_id=101010101)
    mn2 = create_managed_node(allow_auto_traceroute=True, node_id=202020202)
    create_packet_observation(observer=mn1)
    create_packet_observation(observer=mn2)

    with patch("traceroute.tasks.eligible_traceroute_sources_ordered", return_value=[mn1, mn2]):
        with patch(
            "traceroute.tasks.ordered_strategies_for_feeder",
            return_value=[AutoTraceRoute.TARGET_STRATEGY_DX_ACROSS],
        ):
            with patch("traceroute.tasks.pick_traceroute_target", return_value=None):
                with caplog.at_level(logging.WARNING):
                    assert schedule_traceroutes() == {"created": 0}

    assert "cascade exhausted" in caplog.text
    assert AutoTraceRoute.objects.count() == 0


@pytest.mark.django_db
def test_second_source_after_first_exhausts_including_legacy(
    monkeypatch,
    create_managed_node,
    create_packet_observation,
    create_observed_node,
):
    """First source: hypothesis miss + legacy miss; second source wins on first strategy."""
    monkeypatch.setenv("SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS", "600")
    mn1 = create_managed_node(allow_auto_traceroute=True, node_id=301301301)
    mn2 = create_managed_node(allow_auto_traceroute=True, node_id=302302302)
    create_packet_observation(observer=mn1)
    create_packet_observation(observer=mn2)
    target = create_observed_node(node_id=888777666)

    channel_layer = MagicMock()

    def immediate_async_to_sync(async_func):
        return async_func

    with patch("traceroute.dispatch.notify_traceroute_status_changed"):
        with patch("traceroute.dispatch.async_to_sync", side_effect=immediate_async_to_sync):
            with patch("traceroute.dispatch.get_channel_layer", return_value=channel_layer):
                with patch(
                    "traceroute.tasks.eligible_traceroute_sources_ordered",
                    return_value=[mn1, mn2],
                ):
                    with patch(
                        "traceroute.tasks.ordered_strategies_for_feeder",
                        return_value=[AutoTraceRoute.TARGET_STRATEGY_DX_ACROSS],
                    ):
                        with patch(
                            "traceroute.tasks.pick_traceroute_target",
                            side_effect=[None, None, target],
                        ):
                            with patch("traceroute.tasks.record_strategy_run") as rec:
                                assert schedule_traceroutes() == {"created": 1}
                                assert dispatch_pending_traceroutes()["dispatched"] == 1

    rec.assert_called_once_with(mn2, AutoTraceRoute.TARGET_STRATEGY_DX_ACROSS)
    assert AutoTraceRoute.objects.filter(source_node=mn2).exists()
