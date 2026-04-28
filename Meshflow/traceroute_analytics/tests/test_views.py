"""Tests for traceroute analytics HTTP endpoints (stats, reach, coverage)."""

from datetime import timedelta

from django.utils import timezone

import pytest
from rest_framework.test import APIClient

import nodes.tests.conftest  # noqa: F401
import packets.tests.conftest  # noqa: F401
import users.tests.conftest  # noqa: F401
from traceroute.models import AutoTraceRoute


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
class TestTracerouteStats:
    def test_stats_requires_auth(self, api_client):
        resp = api_client.get("/api/traceroutes/stats/")
        assert resp.status_code == 401

    def test_stats_includes_by_source_for_two_sources(
        self,
        api_client,
        create_user,
        create_managed_node,
        create_observed_node,
        create_auto_traceroute,
    ):
        user = create_user()
        mn_a = create_managed_node(node_id=111_111_111)
        mn_b = create_managed_node(node_id=222_222_222)
        on = create_observed_node()
        api_client.force_authenticate(user=user)

        create_auto_traceroute(
            source_node=mn_a, target_node=on, triggered_by=user, status=AutoTraceRoute.STATUS_COMPLETED
        )
        create_auto_traceroute(
            source_node=mn_a, target_node=on, triggered_by=user, status=AutoTraceRoute.STATUS_COMPLETED
        )
        create_auto_traceroute(source_node=mn_a, target_node=on, triggered_by=user, status=AutoTraceRoute.STATUS_FAILED)
        create_auto_traceroute(
            source_node=mn_b, target_node=on, triggered_by=user, status=AutoTraceRoute.STATUS_PENDING
        )
        create_auto_traceroute(source_node=mn_b, target_node=on, triggered_by=user, status=AutoTraceRoute.STATUS_SENT)

        resp = api_client.get("/api/traceroutes/stats/")
        assert resp.status_code == 200
        data = resp.json()
        assert "by_source" in data
        by_internal_id = {row["managed_node_id"]: row for row in data["by_source"]}

        row_a = by_internal_id[str(mn_a.internal_id)]
        assert row_a["total"] == 3
        assert row_a["completed"] == 2
        assert row_a["failed"] == 1
        assert row_a["success_rate"] == pytest.approx(2 / 3)
        assert row_a["node_id"] == mn_a.node_id
        assert row_a["name"] == mn_a.name

        row_b = by_internal_id[str(mn_b.internal_id)]
        assert row_b["total"] == 2
        assert row_b["completed"] == 0
        assert row_b["failed"] == 0
        assert row_b["success_rate"] is None

    def test_by_source_respects_triggered_at_after(
        self,
        api_client,
        create_user,
        create_managed_node,
        create_observed_node,
        create_auto_traceroute,
    ):
        user = create_user()
        mn = create_managed_node(node_id=333_333_333)
        on = create_observed_node()
        api_client.force_authenticate(user=user)

        old_time = timezone.now() - timedelta(days=30)
        tr_old = create_auto_traceroute(
            source_node=mn,
            target_node=on,
            triggered_by=user,
            status=AutoTraceRoute.STATUS_COMPLETED,
        )
        AutoTraceRoute.objects.filter(pk=tr_old.pk).update(triggered_at=old_time)

        create_auto_traceroute(
            source_node=mn,
            target_node=on,
            triggered_by=user,
            status=AutoTraceRoute.STATUS_COMPLETED,
        )

        resp_all = api_client.get("/api/traceroutes/stats/")
        assert resp_all.status_code == 200
        rows_all = {r["managed_node_id"]: r for r in resp_all.json()["by_source"]}
        assert rows_all[str(mn.internal_id)]["total"] == 2

        since = (timezone.now() - timedelta(days=7)).isoformat()
        resp_filtered = api_client.get("/api/traceroutes/stats/", {"triggered_at_after": since})
        assert resp_filtered.status_code == 200
        rows_f = {r["managed_node_id"]: r for r in resp_filtered.json()["by_source"]}
        assert rows_f[str(mn.internal_id)]["total"] == 1

    def test_stats_by_target_empty_when_no_traceroutes(
        self,
        api_client,
        create_user,
    ):
        user = create_user()
        api_client.force_authenticate(user=user)

        resp = api_client.get("/api/traceroutes/stats/")
        assert resp.status_code == 200
        data = resp.json()
        assert "by_target" in data
        assert data["by_target"] == []

    def test_stats_includes_by_target_for_two_targets(
        self,
        api_client,
        create_user,
        create_managed_node,
        create_observed_node,
        create_auto_traceroute,
    ):
        user = create_user()
        mn = create_managed_node(node_id=444_444_444)
        on_a = create_observed_node(node_id=100_000_001, short_name="AAAA", long_name="Target A")
        on_b = create_observed_node(node_id=100_000_002, short_name="BBBB", long_name="Target B")
        api_client.force_authenticate(user=user)

        # Target A: 2 completed, 1 failed -> success_rate 2/3
        create_auto_traceroute(
            source_node=mn, target_node=on_a, triggered_by=user, status=AutoTraceRoute.STATUS_COMPLETED
        )
        create_auto_traceroute(
            source_node=mn, target_node=on_a, triggered_by=user, status=AutoTraceRoute.STATUS_COMPLETED
        )
        create_auto_traceroute(source_node=mn, target_node=on_a, triggered_by=user, status=AutoTraceRoute.STATUS_FAILED)
        # Target B: 1 pending, 1 sent -> no finished runs, success_rate is null
        create_auto_traceroute(
            source_node=mn, target_node=on_b, triggered_by=user, status=AutoTraceRoute.STATUS_PENDING
        )
        create_auto_traceroute(source_node=mn, target_node=on_b, triggered_by=user, status=AutoTraceRoute.STATUS_SENT)

        resp = api_client.get("/api/traceroutes/stats/")
        assert resp.status_code == 200
        data = resp.json()
        assert "by_target" in data
        by_node_id = {row["node_id"]: row for row in data["by_target"]}

        row_a = by_node_id[on_a.node_id]
        assert row_a["total"] == 3
        assert row_a["completed"] == 2
        assert row_a["failed"] == 1
        assert row_a["success_rate"] == pytest.approx(2 / 3)
        assert row_a["short_name"] == on_a.short_name
        assert row_a["long_name"] == on_a.long_name
        assert "node_id_str" in row_a

        row_b = by_node_id[on_b.node_id]
        assert row_b["total"] == 2
        assert row_b["completed"] == 0
        assert row_b["failed"] == 0
        assert row_b["success_rate"] is None

    def test_by_target_respects_triggered_at_after(
        self,
        api_client,
        create_user,
        create_managed_node,
        create_observed_node,
        create_auto_traceroute,
    ):
        user = create_user()
        mn = create_managed_node(node_id=555_555_555)
        on = create_observed_node(node_id=200_000_001)
        api_client.force_authenticate(user=user)

        old_time = timezone.now() - timedelta(days=30)
        tr_old = create_auto_traceroute(
            source_node=mn,
            target_node=on,
            triggered_by=user,
            status=AutoTraceRoute.STATUS_COMPLETED,
        )
        AutoTraceRoute.objects.filter(pk=tr_old.pk).update(triggered_at=old_time)

        create_auto_traceroute(
            source_node=mn,
            target_node=on,
            triggered_by=user,
            status=AutoTraceRoute.STATUS_FAILED,
        )

        resp_all = api_client.get("/api/traceroutes/stats/")
        rows_all = {r["node_id"]: r for r in resp_all.json()["by_target"]}
        assert rows_all[on.node_id]["total"] == 2
        assert rows_all[on.node_id]["completed"] == 1
        assert rows_all[on.node_id]["failed"] == 1

        since = (timezone.now() - timedelta(days=7)).isoformat()
        resp_filtered = api_client.get("/api/traceroutes/stats/", {"triggered_at_after": since})
        rows_f = {r["node_id"]: r for r in resp_filtered.json()["by_target"]}
        assert rows_f[on.node_id]["total"] == 1
        assert rows_f[on.node_id]["completed"] == 0
        assert rows_f[on.node_id]["failed"] == 1


@pytest.mark.django_db
class TestFeederReach:
    def test_requires_auth(self, api_client):
        resp = api_client.get("/api/traceroutes/feeder-reach/", {"feeder_id": "1"})
        assert resp.status_code == 401

    def test_missing_feeder_id_returns_400(self, api_client, create_user):
        api_client.force_authenticate(user=create_user())
        resp = api_client.get("/api/traceroutes/feeder-reach/")
        assert resp.status_code == 400

    def test_non_int_feeder_id_returns_400(self, api_client, create_user):
        api_client.force_authenticate(user=create_user())
        resp = api_client.get("/api/traceroutes/feeder-reach/", {"feeder_id": "abc"})
        assert resp.status_code == 400

    def test_unknown_feeder_returns_404(self, api_client, create_user):
        api_client.force_authenticate(user=create_user())
        resp = api_client.get("/api/traceroutes/feeder-reach/", {"feeder_id": "999999"})
        assert resp.status_code == 404

    def test_empty_targets_when_no_traceroutes(self, api_client, create_user, create_managed_node):
        api_client.force_authenticate(user=create_user())
        feeder = create_managed_node(
            node_id=0xAAAA_AA01,
            default_location_latitude=55.86,
            default_location_longitude=-4.25,
        )
        resp = api_client.get("/api/traceroutes/feeder-reach/", {"feeder_id": str(feeder.node_id)})
        assert resp.status_code == 200
        body = resp.json()
        assert body["feeder"]["node_id"] == feeder.node_id
        assert body["feeder"]["lat"] == pytest.approx(55.86)
        assert body["targets"] == []
        assert body["meta"]["window"] == {"start": None, "end": None}

    def test_payload_includes_attempts_and_successes(
        self,
        api_client,
        create_user,
        create_managed_node,
        create_observed_node,
        create_auto_traceroute,
    ):
        from nodes.models import NodeLatestStatus

        api_client.force_authenticate(user=create_user())
        feeder = create_managed_node(
            node_id=0xAAAA_AA02,
            default_location_latitude=55.86,
            default_location_longitude=-4.25,
        )
        target = create_observed_node(node_id=0xCCCC_CC02)
        NodeLatestStatus.objects.create(node=target, latitude=55.86, longitude=-4.20)

        for _ in range(7):
            create_auto_traceroute(
                source_node=feeder,
                target_node=target,
                status=AutoTraceRoute.STATUS_COMPLETED,
            )
        for _ in range(3):
            create_auto_traceroute(
                source_node=feeder,
                target_node=target,
                status=AutoTraceRoute.STATUS_FAILED,
            )

        resp = api_client.get("/api/traceroutes/feeder-reach/", {"feeder_id": str(feeder.node_id)})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["targets"]) == 1
        row = body["targets"][0]
        assert row["node_id"] == target.node_id
        assert row["attempts"] == 10
        assert row["successes"] == 7

    def test_feeder_reach_target_strategy_filter(
        self,
        api_client,
        create_user,
        create_managed_node,
        create_observed_node,
        create_auto_traceroute,
    ):
        from nodes.models import NodeLatestStatus

        api_client.force_authenticate(user=create_user())
        feeder = create_managed_node(
            node_id=0xAAAA_AA20,
            default_location_latitude=55.86,
            default_location_longitude=-4.25,
        )
        target = create_observed_node(node_id=0xCCCC_CC20)
        NodeLatestStatus.objects.create(node=target, latitude=55.86, longitude=-4.20)

        create_auto_traceroute(
            source_node=feeder,
            target_node=target,
            status=AutoTraceRoute.STATUS_COMPLETED,
            target_strategy=AutoTraceRoute.TARGET_STRATEGY_INTRA_ZONE,
        )
        create_auto_traceroute(
            source_node=feeder,
            target_node=target,
            status=AutoTraceRoute.STATUS_COMPLETED,
            target_strategy=AutoTraceRoute.TARGET_STRATEGY_DX_ACROSS,
        )

        resp = api_client.get(
            "/api/traceroutes/feeder-reach/",
            {"feeder_id": str(feeder.node_id), "target_strategy": "intra_zone"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["targets"]) == 1
        assert body["targets"][0]["attempts"] == 1


@pytest.mark.django_db
class TestConstellationCoverage:
    def test_requires_auth(self, api_client):
        resp = api_client.get("/api/traceroutes/constellation-coverage/", {"constellation_id": "1"})
        assert resp.status_code == 401

    def test_missing_constellation_id_returns_400(self, api_client, create_user):
        api_client.force_authenticate(user=create_user())
        resp = api_client.get("/api/traceroutes/constellation-coverage/")
        assert resp.status_code == 400

    def test_non_int_constellation_id_returns_400(self, api_client, create_user):
        api_client.force_authenticate(user=create_user())
        resp = api_client.get("/api/traceroutes/constellation-coverage/", {"constellation_id": "abc"})
        assert resp.status_code == 400

    def test_empty_response_shape(self, api_client, create_user, create_constellation):
        api_client.force_authenticate(user=create_user())
        constellation = create_constellation(created_by=create_user())
        resp = api_client.get(
            "/api/traceroutes/constellation-coverage/",
            {"constellation_id": str(constellation.id)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["constellation_id"] == constellation.id
        assert body["h3_resolution"] == 6
        assert body["hexes"] == []

    def test_hex_aggregation_end_to_end(
        self,
        api_client,
        create_user,
        create_managed_node,
        create_observed_node,
        create_auto_traceroute,
        create_constellation,
    ):
        import h3

        from nodes.models import NodeLatestStatus

        owner = create_user()
        api_client.force_authenticate(user=owner)
        constellation = create_constellation(created_by=owner)

        feeder = create_managed_node(
            owner=owner,
            constellation=constellation,
            node_id=0xAAAA_AA03,
            default_location_latitude=55.86,
            default_location_longitude=-4.25,
        )
        target_a = create_observed_node(node_id=0xCCCC_CC03)
        target_b = create_observed_node(node_id=0xCCCC_CC04)
        NodeLatestStatus.objects.create(node=target_a, latitude=55.860, longitude=-4.200)
        NodeLatestStatus.objects.create(node=target_b, latitude=55.860010, longitude=-4.200010)

        for _ in range(3):
            create_auto_traceroute(
                source_node=feeder,
                target_node=target_a,
                status=AutoTraceRoute.STATUS_COMPLETED,
            )
        create_auto_traceroute(
            source_node=feeder,
            target_node=target_a,
            status=AutoTraceRoute.STATUS_FAILED,
        )
        create_auto_traceroute(
            source_node=feeder,
            target_node=target_b,
            status=AutoTraceRoute.STATUS_COMPLETED,
        )

        expected_hex = h3.latlng_to_cell(55.860, -4.200, 6)

        resp = api_client.get(
            "/api/traceroutes/constellation-coverage/",
            {"constellation_id": str(constellation.id)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["hexes"]) == 1
        hx = body["hexes"][0]
        assert hx["h3_index"] == expected_hex
        assert hx["attempts"] == 5
        assert hx["successes"] == 4
        assert hx["contributing_feeders"] == 1
        assert hx["contributing_targets"] == 2

    def test_h3_resolution_query_param(
        self,
        api_client,
        create_user,
        create_managed_node,
        create_observed_node,
        create_auto_traceroute,
        create_constellation,
    ):
        from nodes.models import NodeLatestStatus

        owner = create_user()
        api_client.force_authenticate(user=owner)
        constellation = create_constellation(created_by=owner)
        feeder = create_managed_node(
            owner=owner,
            constellation=constellation,
            node_id=0xAAAA_AA04,
            default_location_latitude=55.86,
            default_location_longitude=-4.25,
        )
        target = create_observed_node(node_id=0xCCCC_CC05)
        NodeLatestStatus.objects.create(node=target, latitude=55.86, longitude=-4.20)
        create_auto_traceroute(
            source_node=feeder,
            target_node=target,
            status=AutoTraceRoute.STATUS_COMPLETED,
        )

        resp = api_client.get(
            "/api/traceroutes/constellation-coverage/",
            {"constellation_id": str(constellation.id), "h3_resolution": "8"},
        )
        assert resp.status_code == 200
        assert resp.json()["h3_resolution"] == 8

    def test_include_targets_returns_targets_and_feeders(
        self,
        api_client,
        create_user,
        create_managed_node,
        create_observed_node,
        create_auto_traceroute,
        create_constellation,
    ):
        from nodes.models import NodeLatestStatus

        owner = create_user()
        api_client.force_authenticate(user=owner)
        constellation = create_constellation(created_by=owner)

        feeder_a = create_managed_node(
            owner=owner,
            constellation=constellation,
            node_id=0xAAAA_AA10,
            default_location_latitude=55.86,
            default_location_longitude=-4.25,
        )
        feeder_b = create_managed_node(
            owner=owner,
            constellation=constellation,
            node_id=0xAAAA_AA11,
            default_location_latitude=55.90,
            default_location_longitude=-4.30,
        )
        target = create_observed_node(node_id=0xCCCC_CC10)
        NodeLatestStatus.objects.create(node=target, latitude=55.87, longitude=-4.22)

        create_auto_traceroute(
            source_node=feeder_a,
            target_node=target,
            status=AutoTraceRoute.STATUS_COMPLETED,
        )
        create_auto_traceroute(
            source_node=feeder_b,
            target_node=target,
            status=AutoTraceRoute.STATUS_FAILED,
        )

        resp = api_client.get(
            "/api/traceroutes/constellation-coverage/",
            {
                "constellation_id": str(constellation.id),
                "include_targets": "1",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "targets" in body
        assert "feeders" in body
        assert len(body["targets"]) == 1
        assert body["targets"][0]["attempts"] == 2
        assert body["targets"][0]["successes"] == 1
        assert body["targets"][0]["contributing_feeders"] == 2
        feeder_ids = {f["node_id"] for f in body["feeders"]}
        assert feeder_a.node_id in feeder_ids
        assert feeder_b.node_id in feeder_ids

    def test_omit_include_targets_has_no_targets_key(
        self,
        api_client,
        create_user,
        create_constellation,
    ):
        owner = create_user()
        api_client.force_authenticate(user=owner)
        constellation = create_constellation(created_by=owner)
        resp = api_client.get(
            "/api/traceroutes/constellation-coverage/",
            {"constellation_id": str(constellation.id)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "targets" not in body
        assert "feeders" not in body

    def test_constellation_target_strategy_filters_hexes(
        self,
        api_client,
        create_user,
        create_managed_node,
        create_observed_node,
        create_auto_traceroute,
        create_constellation,
    ):
        from nodes.models import NodeLatestStatus

        owner = create_user()
        api_client.force_authenticate(user=owner)
        constellation = create_constellation(created_by=owner)
        feeder = create_managed_node(
            owner=owner,
            constellation=constellation,
            node_id=0xAAAA_AA12,
            default_location_latitude=55.86,
            default_location_longitude=-4.25,
        )
        target = create_observed_node(node_id=0xCCCC_CC11)
        NodeLatestStatus.objects.create(node=target, latitude=55.86, longitude=-4.20)

        create_auto_traceroute(
            source_node=feeder,
            target_node=target,
            status=AutoTraceRoute.STATUS_COMPLETED,
            target_strategy=AutoTraceRoute.TARGET_STRATEGY_INTRA_ZONE,
        )
        create_auto_traceroute(
            source_node=feeder,
            target_node=target,
            status=AutoTraceRoute.STATUS_COMPLETED,
            target_strategy=AutoTraceRoute.TARGET_STRATEGY_DX_ACROSS,
        )

        resp_all = api_client.get(
            "/api/traceroutes/constellation-coverage/",
            {"constellation_id": str(constellation.id)},
        )
        assert resp_all.status_code == 200
        assert resp_all.json()["hexes"][0]["attempts"] == 2

        resp_f = api_client.get(
            "/api/traceroutes/constellation-coverage/",
            {
                "constellation_id": str(constellation.id),
                "target_strategy": "intra_zone",
            },
        )
        assert resp_f.status_code == 200
        assert resp_f.json()["hexes"][0]["attempts"] == 1
