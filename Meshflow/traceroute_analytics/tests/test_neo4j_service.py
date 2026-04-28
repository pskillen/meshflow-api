"""Tests for traceroute_analytics.neo4j_service."""

from unittest.mock import MagicMock, patch

import pytest

import nodes.tests.conftest  # noqa: F401 - load fixtures
import users.tests.conftest  # noqa: F401 - load fixtures
from traceroute_analytics.neo4j_service import (
    UNKNOWN_NODE_ID,
    _extract_edges,
    add_traceroute_edges,
    clear_all_routed_to_edges,
    run_heatmap_query,
)


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


def _mock_driver():
    """Build a mocked Neo4j driver whose session() context yields a MagicMock session."""
    mock_session = MagicMock()
    mock_driver = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_session
    mock_cm.__exit__.return_value = False
    mock_driver.session.return_value = mock_cm
    return mock_driver, mock_session


def _edge_param_pairs(mock_session):
    """Extract (a_id, b_id) tuples from every session.run(..., a_id=..., b_id=...) call."""
    pairs = []
    for call in mock_session.run.call_args_list:
        kwargs = call[1] if len(call) > 1 and isinstance(call[1], dict) else {}
        if "a_id" in kwargs and "b_id" in kwargs:
            pairs.append((kwargs["a_id"], kwargs["b_id"]))
    return pairs


def _create_observed_with_coords(node_id: int, lat: float, lng: float, short_name: str = "PEER"):
    """Create an ObservedNode with a NodeLatestStatus carrying coords."""
    from common.mesh_node_helpers import meshtastic_id_to_hex
    from nodes.models import NodeLatestStatus, ObservedNode

    obs = ObservedNode.objects.create(
        node_id=node_id,
        node_id_str=meshtastic_id_to_hex(node_id),
        short_name=short_name,
        long_name=f"Node {short_name}",
    )
    NodeLatestStatus.objects.create(node=obs, latitude=lat, longitude=lng)
    return obs


@pytest.mark.django_db
class TestAddTracerouteEdges:
    """Tests for add_traceroute_edges edge construction."""

    def _build_auto_tr(
        self,
        create_managed_node,
        create_observed_node,
        create_user,
        *,
        route,
        route_back,
        source_coords=(55.86, -4.25),
        target_coords=(55.85, -4.26),
        raw_packet=None,
    ):
        from nodes.models import NodeLatestStatus
        from traceroute.models import AutoTraceRoute

        user = create_user()
        source_node = create_managed_node(
            node_id=0xAAAAAAAA,
            default_location_latitude=source_coords[0] if source_coords else None,
            default_location_longitude=source_coords[1] if source_coords else None,
        )
        target_node = create_observed_node(node_id=0xBBBBBBBB)
        if target_coords is not None:
            NodeLatestStatus.objects.create(
                node=target_node,
                latitude=target_coords[0],
                longitude=target_coords[1],
            )
        return AutoTraceRoute.objects.create(
            source_node=source_node,
            target_node=target_node,
            trigger_type=AutoTraceRoute.TRIGGER_TYPE_USER,
            triggered_by=user,
            status=AutoTraceRoute.STATUS_COMPLETED,
            route=route,
            route_back=route_back,
            raw_packet=raw_packet,
        )

    def test_forward_chain_single_relay_includes_peer_to_target(
        self, create_managed_node, create_observed_node, create_user
    ):
        """route=[peer] yields (source, peer) AND (peer, target)."""
        peer_id = 0xCCCCCCCC
        _create_observed_with_coords(peer_id, 55.87, -4.25)
        auto_tr = self._build_auto_tr(
            create_managed_node,
            create_observed_node,
            create_user,
            route=[{"node_id": peer_id, "snr": -5.0}],
            route_back=[],
        )

        mock_driver, mock_session = _mock_driver()
        with patch("traceroute_analytics.neo4j_service.get_driver", return_value=mock_driver):
            add_traceroute_edges(auto_tr, driver=mock_driver)

        pairs = _edge_param_pairs(mock_session)
        assert (0xAAAAAAAA, peer_id) in pairs
        assert (peer_id, 0xBBBBBBBB) in pairs

    def test_forward_chain_multi_relay_includes_all_hops(self, create_managed_node, create_observed_node, create_user):
        """route=[p1, p2] yields (source, p1), (p1, p2), (p2, target)."""
        p1, p2 = 0xC1C1C1C1, 0xC2C2C2C2
        _create_observed_with_coords(p1, 55.87, -4.25, short_name="P1")
        _create_observed_with_coords(p2, 55.88, -4.26, short_name="P2")
        auto_tr = self._build_auto_tr(
            create_managed_node,
            create_observed_node,
            create_user,
            route=[
                {"node_id": p1, "snr": -5.0},
                {"node_id": p2, "snr": -3.0},
            ],
            route_back=[],
        )

        mock_driver, mock_session = _mock_driver()
        with patch("traceroute_analytics.neo4j_service.get_driver", return_value=mock_driver):
            add_traceroute_edges(auto_tr, driver=mock_driver)

        pairs = _edge_param_pairs(mock_session)
        assert (0xAAAAAAAA, p1) in pairs
        assert (p1, p2) in pairs
        assert (p2, 0xBBBBBBBB) in pairs

    def test_return_chain_adds_bookends(self, create_managed_node, create_observed_node, create_user):
        """route_back=[p1, p2] yields (target, p1), (p1, p2), (p2, source)."""
        p1, p2 = 0xD1D1D1D1, 0xD2D2D2D2
        _create_observed_with_coords(p1, 55.87, -4.25, short_name="P1")
        _create_observed_with_coords(p2, 55.88, -4.26, short_name="P2")
        auto_tr = self._build_auto_tr(
            create_managed_node,
            create_observed_node,
            create_user,
            route=[],
            route_back=[
                {"node_id": p1, "snr": -4.0},
                {"node_id": p2, "snr": -2.0},
            ],
        )

        mock_driver, mock_session = _mock_driver()
        with patch("traceroute_analytics.neo4j_service.get_driver", return_value=mock_driver):
            add_traceroute_edges(auto_tr, driver=mock_driver)

        pairs = _edge_param_pairs(mock_session)
        assert (0xBBBBBBBB, p1) in pairs
        assert (p1, p2) in pairs
        assert (p2, 0xAAAAAAAA) in pairs

    def test_direct_traceroute_creates_source_target_edges(
        self, create_managed_node, create_observed_node, create_user
    ):
        """Empty route and route_back: (source, target) and (target, source) when coords present."""
        auto_tr = self._build_auto_tr(
            create_managed_node,
            create_observed_node,
            create_user,
            route=[],
            route_back=[],
        )

        mock_driver, mock_session = _mock_driver()
        with patch("traceroute_analytics.neo4j_service.get_driver", return_value=mock_driver):
            add_traceroute_edges(auto_tr, driver=mock_driver)

        pairs = _edge_param_pairs(mock_session)
        assert (0xAAAAAAAA, 0xBBBBBBBB) in pairs
        assert (0xBBBBBBBB, 0xAAAAAAAA) in pairs

    def test_direct_traceroute_skipped_when_no_coords(self, create_managed_node, create_observed_node, create_user):
        """Empty route/route_back without endpoint coords: no edges written."""
        auto_tr = self._build_auto_tr(
            create_managed_node,
            create_observed_node,
            create_user,
            route=[],
            route_back=[],
            source_coords=None,
            target_coords=None,
        )

        mock_driver, mock_session = _mock_driver()
        with patch("traceroute_analytics.neo4j_service.get_driver", return_value=mock_driver):
            add_traceroute_edges(auto_tr, driver=mock_driver)

        assert _edge_param_pairs(mock_session) == []

    def test_target_snr_pulled_from_raw_packet_when_route_snr_shorter(
        self, create_managed_node, create_observed_node, create_user
    ):
        """
        raw_packet.snr_towards has one more value than route: the trailing value is
        the SNR at the target for the final (peer -> target) hop.
        """
        from packets.models import TraceroutePacket

        peer_id = 0xCCCCCCCC
        _create_observed_with_coords(peer_id, 55.87, -4.25)

        tr_packet = TraceroutePacket.objects.create(
            packet_id=987654321,
            from_int=0xBBBBBBBB,
            to_int=0xAAAAAAAA,
            route=[peer_id],
            route_back=[],
            snr_towards=[-5.0, -1.5],
            snr_back=[],
        )

        auto_tr = self._build_auto_tr(
            create_managed_node,
            create_observed_node,
            create_user,
            route=[{"node_id": peer_id, "snr": -5.0}],
            route_back=[],
            raw_packet=tr_packet,
        )

        mock_driver, mock_session = _mock_driver()
        with patch("traceroute_analytics.neo4j_service.get_driver", return_value=mock_driver):
            add_traceroute_edges(auto_tr, driver=mock_driver)

        target_hop_snrs = []
        for call in mock_session.run.call_args_list:
            kwargs = call[1] if len(call) > 1 and isinstance(call[1], dict) else {}
            if kwargs.get("a_id") == peer_id and kwargs.get("b_id") == 0xBBBBBBBB:
                target_hop_snrs.append(kwargs.get("snr"))
        assert target_hop_snrs, "Expected (peer, target) edge to be written"
        assert target_hop_snrs[0] == -1.5

    def test_add_traceroute_edges_uses_merge_with_auto_tr_id(
        self, create_managed_node, create_observed_node, create_user
    ):
        """Edge writes are MERGE-based and include auto_tr_id in params (idempotent by design)."""
        peer_id = 0xCCCCCCCC
        _create_observed_with_coords(peer_id, 55.87, -4.25)
        auto_tr = self._build_auto_tr(
            create_managed_node,
            create_observed_node,
            create_user,
            route=[{"node_id": peer_id, "snr": -5.0}],
            route_back=[],
        )

        mock_driver, mock_session = _mock_driver()
        with patch("traceroute_analytics.neo4j_service.get_driver", return_value=mock_driver):
            add_traceroute_edges(auto_tr, driver=mock_driver)

        edge_calls = [
            call for call in mock_session.run.call_args_list if "a_id" in (call[1] or {}) and "b_id" in (call[1] or {})
        ]
        assert edge_calls, "Expected at least one edge write"
        for call in edge_calls:
            cypher = call[0][0] if call[0] else ""
            params = call[1] or {}
            assert "MERGE (a)-[r:ROUTED_TO" in cypher
            assert "CREATE (a)-[:ROUTED_TO" not in cypher
            assert "auto_tr_id: $auto_tr_id" in cypher
            assert params.get("auto_tr_id") == auto_tr.id

    def test_add_traceroute_edges_reexport_does_not_duplicate(
        self, create_managed_node, create_observed_node, create_user
    ):
        """Re-invoking add_traceroute_edges with the same AutoTraceRoute keeps auto_tr_id stable."""
        peer_id = 0xCCCCCCCC
        _create_observed_with_coords(peer_id, 55.87, -4.25)
        auto_tr = self._build_auto_tr(
            create_managed_node,
            create_observed_node,
            create_user,
            route=[{"node_id": peer_id, "snr": -5.0}],
            route_back=[],
        )

        mock_driver, mock_session = _mock_driver()
        with patch("traceroute_analytics.neo4j_service.get_driver", return_value=mock_driver):
            add_traceroute_edges(auto_tr, driver=mock_driver)
            add_traceroute_edges(auto_tr, driver=mock_driver)

        edge_calls = [
            call for call in mock_session.run.call_args_list if "a_id" in (call[1] or {}) and "b_id" in (call[1] or {})
        ]
        auto_tr_ids = {(call[1] or {}).get("auto_tr_id") for call in edge_calls}
        assert auto_tr_ids == {auto_tr.id}, "Second export should reuse the same auto_tr_id"
        for call in edge_calls:
            assert "MERGE (a)-[r:ROUTED_TO" in call[0][0]


class TestClearAllRoutedToEdges:
    """Tests for clear_all_routed_to_edges."""

    def test_clear_all_routed_to_edges_runs_delete(self):
        mock_result = MagicMock()
        mock_result.single.return_value = {"deleted": 42}
        mock_session = MagicMock()
        mock_session.run.return_value = mock_result
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_session
        mock_cm.__exit__.return_value = False
        mock_driver.session.return_value = mock_cm

        with patch("traceroute_analytics.neo4j_service.get_driver", return_value=mock_driver):
            deleted = clear_all_routed_to_edges(driver=mock_driver)

        assert deleted == 42
        assert mock_session.run.call_count == 1
        cypher = mock_session.run.call_args[0][0]
        assert "ROUTED_TO" in cypher
        assert "DELETE r" in cypher


@pytest.mark.django_db
class TestRunHeatmapQuery:
    """Tests for run_heatmap_query with mocked Neo4j."""

    def test_run_heatmap_query_packets_returns_weight_only(self):
        """edge_metric=packets returns edges with weight, no avg_snr."""
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter(
            [
                {
                    "from_node_id": 1,
                    "to_node_id": 2,
                    "from_lat": 55.0,
                    "from_lng": -4.0,
                    "to_lat": 55.1,
                    "to_lng": -4.1,
                    "from_node_id_str": "!00000001",
                    "from_short_name": "A",
                    "from_long_name": "Node A",
                    "to_node_id_str": "!00000002",
                    "to_short_name": "B",
                    "to_long_name": "Node B",
                    "weight": 5,
                }
            ]
        )
        mock_session = MagicMock()
        mock_session.run.return_value = mock_result
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_session
        mock_cm.__exit__.return_value = False
        mock_driver.session.return_value = mock_cm

        with patch("traceroute_analytics.neo4j_service.get_driver", return_value=mock_driver):
            data = run_heatmap_query(edge_metric="packets", driver=mock_driver)

        assert len(data["edges"]) == 1
        assert data["edges"][0]["weight"] == 5
        assert "avg_snr" not in data["edges"][0]
        assert len(data["nodes"]) == 2

    def test_run_heatmap_query_snr_returns_avg_snr_when_present(self):
        """edge_metric=snr returns edges with weight and avg_snr when Neo4j has snr."""
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter(
            [
                {
                    "from_node_id": 1,
                    "to_node_id": 2,
                    "from_lat": 55.0,
                    "from_lng": -4.0,
                    "to_lat": 55.1,
                    "to_lng": -4.1,
                    "from_node_id_str": "!00000001",
                    "from_short_name": "A",
                    "from_long_name": "Node A",
                    "to_node_id_str": "!00000002",
                    "to_short_name": "B",
                    "to_long_name": "Node B",
                    "weight": 3,
                    "avg_snr": -2.5,
                }
            ]
        )
        mock_session = MagicMock()
        mock_session.run.return_value = mock_result
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_session
        mock_cm.__exit__.return_value = False
        mock_driver.session.return_value = mock_cm

        with patch("traceroute_analytics.neo4j_service.get_driver", return_value=mock_driver):
            data = run_heatmap_query(edge_metric="snr", driver=mock_driver)

        assert len(data["edges"]) == 1
        assert data["edges"][0]["weight"] == 3
        assert data["edges"][0]["avg_snr"] == -2.5
        assert len(data["nodes"]) == 2

    def test_run_heatmap_query_snr_omits_avg_snr_when_null(self):
        """edge_metric=snr omits avg_snr when Neo4j returns null (no snr on relationships)."""
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter(
            [
                {
                    "from_node_id": 1,
                    "to_node_id": 2,
                    "from_lat": 55.0,
                    "from_lng": -4.0,
                    "to_lat": 55.1,
                    "to_lng": -4.1,
                    "from_node_id_str": "!00000001",
                    "from_short_name": "A",
                    "from_long_name": "Node A",
                    "to_node_id_str": "!00000002",
                    "to_short_name": "B",
                    "to_long_name": "Node B",
                    "weight": 2,
                    "avg_snr": None,
                }
            ]
        )
        mock_session = MagicMock()
        mock_session.run.return_value = mock_result
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_session
        mock_cm.__exit__.return_value = False
        mock_driver.session.return_value = mock_cm

        with patch("traceroute_analytics.neo4j_service.get_driver", return_value=mock_driver):
            data = run_heatmap_query(edge_metric="snr", driver=mock_driver)

        assert len(data["edges"]) == 1
        assert data["edges"][0]["weight"] == 2
        assert "avg_snr" not in data["edges"][0]
