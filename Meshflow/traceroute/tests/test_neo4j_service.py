"""Tests for traceroute neo4j_service."""

from unittest.mock import MagicMock, patch

import pytest

import nodes.tests.conftest  # noqa: F401 - load fixtures
import users.tests.conftest  # noqa: F401 - load fixtures
from traceroute.neo4j_service import UNKNOWN_NODE_ID, _extract_edges, add_traceroute_edges


class TestExtractEdges:
    """Tests for _extract_edges."""

    def test_extract_edges_basic(self):
        """Consecutive pairs with SNR at receiving node."""
        route_data = [
            {"node_id": 0x11111111, "snr": -5.0},
            {"node_id": 0x22222222, "snr": -3.0},
            {"node_id": 0x33333333, "snr": 2.0},
        ]
        result = _extract_edges(route_data)
        assert result == [
            (0x11111111, 0x22222222, -3.0),
            (0x22222222, 0x33333333, 2.0),
        ]

    def test_extract_edges_skips_unknown_node_id(self):
        """UNKNOWN_NODE_ID (0xFFFFFFFF) filtered out - edges involving it yield nothing."""
        route_data = [
            {"node_id": 0x11111111, "snr": -5.0},
            {"node_id": UNKNOWN_NODE_ID, "snr": -3.0},
            {"node_id": 0x33333333, "snr": 2.0},
        ]
        result = _extract_edges(route_data)
        # Consecutive pairs: (A, UNKNOWN) and (UNKNOWN, B) - both filtered due to UNKNOWN
        assert result == []

    def test_extract_edges_single_hop(self):
        """One element yields no edges (no consecutive pair)."""
        route_data = [{"node_id": 0x11111111, "snr": -5.0}]
        result = _extract_edges(route_data)
        assert result == []

    def test_extract_edges_none_snr(self):
        """Missing SNR yields None in edge."""
        route_data = [
            {"node_id": 0x11111111},
            {"node_id": 0x22222222},
        ]
        result = _extract_edges(route_data)
        assert result == [(0x11111111, 0x22222222, None)]


@pytest.mark.django_db
class TestAddTracerouteEdges:
    """Tests for add_traceroute_edges including source-edge logic."""

    def test_add_traceroute_edges_includes_source_to_first_hop(
        self, create_managed_node, create_observed_node, create_user
    ):
        """With mocked Neo4j, verify edge (source, route[0]) is created when both have coords."""
        from nodes.models import NodeLatestStatus, ObservedNode

        user = create_user()
        source_node = create_managed_node(
            node_id=0xAAAAAAAA,
            default_location_latitude=55.86,
            default_location_longitude=-4.25,
        )
        target_node = create_observed_node(node_id=0xBBBBBBBB)
        NodeLatestStatus.objects.create(
            node=target_node,
            latitude=55.85,
            longitude=-4.26,
        )
        # ObservedNode for peer (route[0]) - need coords via NodeLatestStatus
        peer_node_id = 0xCCCCCCCC
        peer_obs = ObservedNode.objects.create(
            node_id=peer_node_id,
            node_id_str="!cccccccc",
            short_name="PEER",
            long_name="Peer Node",
        )
        NodeLatestStatus.objects.create(
            node=peer_obs,
            latitude=55.87,
            longitude=-4.25,
        )

        from traceroute.models import AutoTraceRoute

        auto_tr = AutoTraceRoute.objects.create(
            source_node=source_node,
            target_node=target_node,
            trigger_type=AutoTraceRoute.TRIGGER_TYPE_USER,
            triggered_by=user,
            status=AutoTraceRoute.STATUS_COMPLETED,
            route=[{"node_id": peer_node_id, "snr": -5.0}],
            route_back=[{"node_id": peer_node_id, "snr": -4.0}],
        )

        mock_session = MagicMock()
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_session
        mock_cm.__exit__.return_value = False
        mock_driver.session.return_value = mock_cm

        with patch("traceroute.neo4j_service.get_driver", return_value=mock_driver):
            add_traceroute_edges(auto_tr, driver=mock_driver)

        # Should have created edge (source, peer) - our synthetic edge for source -> route[0]
        # route has one element (peer); route_back has one element - no consecutive pairs from _extract_edges
        calls = mock_session.run.call_args_list
        assert len(calls) >= 1
        param_pairs = []
        for call in calls:
            kwargs = call[1] if len(call) > 1 and isinstance(call[1], dict) else {}
            if "a_id" in kwargs and "b_id" in kwargs:
                param_pairs.append((kwargs["a_id"], kwargs["b_id"]))
        assert (0xAAAAAAAA, 0xCCCCCCCC) in param_pairs, "Expected edge (source, peer) to be created"
