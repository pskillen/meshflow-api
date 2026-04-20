"""Tests for traceroute views."""

from datetime import timedelta

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

import pytest
from rest_framework.test import APIClient

import nodes.tests.conftest  # noqa: F401 - load fixtures
import packets.tests.conftest  # noqa: F401 - load fixtures
import users.tests.conftest  # noqa: F401 - load fixtures
from constellations.models import ConstellationUserMembership, MessageChannel
from packets.models import PacketObservation
from traceroute.models import AutoTraceRoute


@pytest.fixture
def add_traceroute_source_ingestion(create_raw_packet):
    """Record a PacketObservation for observer (no extra ManagedNode). Depends only on create_raw_packet."""

    def _add(observer):
        packet = create_raw_packet()
        channel = MessageChannel.objects.create(
            name=f"tr-ingest-{observer.internal_id}",
            constellation=observer.constellation,
        )
        return PacketObservation.objects.create(
            packet=packet,
            observer=observer,
            channel=channel,
            hop_limit=3,
            hop_start=3,
            rx_time=timezone.now(),
            rx_rssi=-60.0,
            rx_snr=10.0,
            upload_time=timezone.now(),
            relay_node=None,
        )

    return _add


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def staff_user(create_user):
    user = create_user()
    user.is_staff = True
    user.save()
    return user


@pytest.fixture
def editor_user(create_user, create_constellation):
    """User with editor role in a constellation (created by another user)."""
    creator = create_user()
    constellation = create_constellation(created_by=creator)
    editor = create_user()
    ConstellationUserMembership.objects.create(user=editor, constellation=constellation, role="editor")
    return editor


@pytest.fixture
def editor_managed_node(editor_user, create_constellation, create_managed_node, add_traceroute_source_ingestion):
    """Managed node in a constellation where editor_user has editor role."""
    membership = ConstellationUserMembership.objects.filter(user=editor_user, role="editor").first()
    constellation = membership.constellation
    mn = create_managed_node(
        owner=membership.constellation.created_by,
        constellation=constellation,
        allow_auto_traceroute=True,
    )
    add_traceroute_source_ingestion(mn)
    return mn


@pytest.fixture
def viewer_user(create_user, create_constellation):
    """User with viewer role only (no admin/editor)."""
    creator = create_user()
    constellation = create_constellation(created_by=creator)
    viewer = create_user()
    ConstellationUserMembership.objects.create(user=viewer, constellation=constellation, role="viewer")
    return viewer


@pytest.mark.django_db
class TestTracerouteList:
    def test_list_requires_auth(self, api_client):
        resp = api_client.get("/api/traceroutes/")
        assert resp.status_code == 401

    def test_list_returns_200_for_authenticated(self, api_client, create_user, create_auto_traceroute):
        user = create_user()
        api_client.force_authenticate(user=user)
        create_auto_traceroute(triggered_by=user)
        resp = api_client.get("/api/traceroutes/")
        assert resp.status_code == 200
        assert "results" in resp.json()
        assert resp.json()["count"] >= 1

    def test_list_status_comma_separated(self, api_client, create_user, create_auto_traceroute):
        """status param accepts comma-separated values."""
        user = create_user()
        api_client.force_authenticate(user=user)
        create_auto_traceroute(triggered_by=user, status=AutoTraceRoute.STATUS_COMPLETED)
        resp = api_client.get("/api/traceroutes/?status=completed,pending,sent")
        assert resp.status_code == 200
        assert "results" in resp.json()

    def test_list_response_shape(self, api_client, create_user, create_auto_traceroute):
        """List response has expected structure for source_node and target_node."""
        user = create_user()
        api_client.force_authenticate(user=user)
        create_auto_traceroute(triggered_by=user)
        resp = api_client.get("/api/traceroutes/")
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) >= 1
        tr = results[0]
        # TracerouteListSourceNodeSerializer fields
        assert "source_node" in tr
        sn = tr["source_node"]
        assert "node_id" in sn
        assert "name" in sn
        assert "short_name" in sn
        assert "node_id_str" in sn
        assert "constellation" in sn
        assert "allow_auto_traceroute" in sn
        # TracerouteTargetNodeSerializer fields
        assert "target_node" in tr
        tn = tr["target_node"]
        assert "node_id" in tn
        assert "node_id_str" in tn
        assert "short_name" in tn
        assert "last_heard" in tn
        assert "latest_position" in tn
        assert "claim" in tn

    def test_list_query_count_bounded(self, api_client, create_user, create_auto_traceroute):
        """List endpoint uses bounded queries (no N+1)."""
        user = create_user()
        api_client.force_authenticate(user=user)
        # Create 10 traceroutes to exercise bulk prefetch
        for _ in range(10):
            create_auto_traceroute(triggered_by=user)
        with CaptureQueriesContext(connection) as ctx:
            resp = api_client.get("/api/traceroutes/")
        assert resp.status_code == 200
        # Should be well under 50 queries (was 400+ before optimization)
        assert len(ctx.captured_queries) < 25


@pytest.mark.django_db
class TestTracerouteDetail:
    def test_detail_requires_auth(self, api_client, create_auto_traceroute):
        tr = create_auto_traceroute()
        resp = api_client.get(f"/api/traceroutes/{tr.id}/")
        assert resp.status_code == 401

    def test_detail_returns_200_for_authenticated(self, api_client, create_user, create_auto_traceroute):
        user = create_user()
        api_client.force_authenticate(user=user)
        tr = create_auto_traceroute(triggered_by=user)
        resp = api_client.get(f"/api/traceroutes/{tr.id}/")
        assert resp.status_code == 200
        assert resp.json()["id"] == tr.id


@pytest.fixture
def owner_managed_node(create_user, create_managed_node, create_constellation, add_traceroute_source_ingestion):
    """ManagedNode owned by owner_user with allow_auto_traceroute=True."""
    owner = create_user()
    constellation = create_constellation(created_by=owner)
    mn = create_managed_node(
        owner=owner,
        constellation=constellation,
        allow_auto_traceroute=True,
    )
    add_traceroute_source_ingestion(mn)
    return mn


@pytest.mark.django_db
class TestTracerouteCanTrigger:
    def test_can_trigger_requires_auth(self, api_client):
        resp = api_client.get("/api/traceroutes/can_trigger/")
        assert resp.status_code == 401

    def test_can_trigger_true_for_staff(
        self, api_client, staff_user, create_managed_node, add_traceroute_source_ingestion
    ):
        """Staff has can_trigger=True when at least one eligible node exists."""
        mn = create_managed_node(allow_auto_traceroute=True)
        add_traceroute_source_ingestion(mn)
        api_client.force_authenticate(user=staff_user)
        resp = api_client.get("/api/traceroutes/can_trigger/")
        assert resp.status_code == 200
        assert resp.json()["can_trigger"] is True

    def test_can_trigger_true_for_editor(self, api_client, editor_user, editor_managed_node):
        """Editor has can_trigger=True when they have triggerable nodes in their constellation."""
        api_client.force_authenticate(user=editor_user)
        resp = api_client.get("/api/traceroutes/can_trigger/")
        assert resp.status_code == 200
        assert resp.json()["can_trigger"] is True

    def test_can_trigger_true_for_owner(self, api_client, owner_managed_node):
        """Owner of a node with allow_auto_traceroute can trigger."""
        owner = owner_managed_node.owner
        api_client.force_authenticate(user=owner)
        resp = api_client.get("/api/traceroutes/can_trigger/")
        assert resp.status_code == 200
        assert resp.json()["can_trigger"] is True

    def test_can_trigger_false_for_viewer(self, api_client, viewer_user):
        api_client.force_authenticate(user=viewer_user)
        resp = api_client.get("/api/traceroutes/can_trigger/")
        assert resp.status_code == 200
        assert resp.json()["can_trigger"] is False


@pytest.mark.django_db
class TestTracerouteTriggerableNodes:
    def test_triggerable_nodes_requires_auth(self, api_client):
        resp = api_client.get("/api/traceroutes/triggerable-nodes/")
        assert resp.status_code == 401

    def test_triggerable_nodes_returns_nodes_for_staff(
        self, api_client, staff_user, create_managed_node, add_traceroute_source_ingestion
    ):
        mn = create_managed_node(allow_auto_traceroute=True)
        add_traceroute_source_ingestion(mn)
        api_client.force_authenticate(user=staff_user)
        resp = api_client.get("/api/traceroutes/triggerable-nodes/")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        node_ids = [n["node_id"] for n in data]
        assert mn.node_id in node_ids

    def test_triggerable_nodes_returns_owned_nodes_for_owner(self, api_client, owner_managed_node):
        owner = owner_managed_node.owner
        api_client.force_authenticate(user=owner)
        resp = api_client.get("/api/traceroutes/triggerable-nodes/")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        node_ids = [n["node_id"] for n in data]
        assert owner_managed_node.node_id in node_ids

    def test_triggerable_nodes_returns_constellation_nodes_for_editor(
        self, api_client, editor_user, editor_managed_node
    ):
        api_client.force_authenticate(user=editor_user)
        resp = api_client.get("/api/traceroutes/triggerable-nodes/")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        node_ids = [n["node_id"] for n in data]
        assert editor_managed_node.node_id in node_ids

    def test_triggerable_nodes_empty_for_viewer(self, api_client, viewer_user, create_managed_node):
        """Viewer has no triggerable nodes (viewer role is not admin/editor)."""
        membership = ConstellationUserMembership.objects.filter(user=viewer_user, role="viewer").first()
        constellation = membership.constellation
        creator = constellation.created_by
        mn = create_managed_node(owner=creator, constellation=constellation, allow_auto_traceroute=True)
        api_client.force_authenticate(user=viewer_user)
        resp = api_client.get("/api/traceroutes/triggerable-nodes/")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        node_ids = [n["node_id"] for n in data]
        assert mn.node_id not in node_ids

    def test_triggerable_nodes_response_shape(self, api_client, editor_user, editor_managed_node):
        api_client.force_authenticate(user=editor_user)
        resp = api_client.get("/api/traceroutes/triggerable-nodes/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        node = data[0]
        assert "node_id" in node
        assert "node_id_str" in node
        assert "short_name" in node
        assert "long_name" in node
        assert "allow_auto_traceroute" in node
        assert "constellation" in node
        assert "position" in node
        assert set(node["position"].keys()) == {"latitude", "longitude"}

    def test_triggerable_nodes_position_prefers_latest_observed_location(
        self, api_client, editor_user, editor_managed_node
    ):
        """position is populated from NodeLatestStatus when the node has been heard."""
        from nodes.models import NodeLatestStatus, ObservedNode

        observed, _ = ObservedNode.objects.get_or_create(node_id=editor_managed_node.node_id)
        NodeLatestStatus.objects.update_or_create(node=observed, defaults={"latitude": 55.86, "longitude": -4.25})
        api_client.force_authenticate(user=editor_user)
        resp = api_client.get("/api/traceroutes/triggerable-nodes/")
        assert resp.status_code == 200
        node = next(n for n in resp.json() if n["node_id"] == editor_managed_node.node_id)
        assert node["position"] == {"latitude": 55.86, "longitude": -4.25}

    def test_triggerable_nodes_position_falls_back_to_default_location(
        self, api_client, editor_user, editor_managed_node
    ):
        """When no latest-observed position exists, fall back to ManagedNode default_location_*."""
        editor_managed_node.default_location_latitude = 51.5
        editor_managed_node.default_location_longitude = -0.12
        editor_managed_node.save(update_fields=["default_location_latitude", "default_location_longitude"])
        api_client.force_authenticate(user=editor_user)
        resp = api_client.get("/api/traceroutes/triggerable-nodes/")
        assert resp.status_code == 200
        node = next(n for n in resp.json() if n["node_id"] == editor_managed_node.node_id)
        assert node["position"] == {"latitude": 51.5, "longitude": -0.12}

    def test_triggerable_nodes_excludes_without_recent_ingestion(self, api_client, staff_user, create_managed_node):
        """Nodes with allow_auto_traceroute but no recent PacketObservation as observer are omitted."""
        mn = create_managed_node(allow_auto_traceroute=True)
        api_client.force_authenticate(user=staff_user)
        resp = api_client.get("/api/traceroutes/triggerable-nodes/")
        assert resp.status_code == 200
        node_ids = [n["node_id"] for n in resp.json()]
        assert mn.node_id not in node_ids


@pytest.mark.django_db
class TestTracerouteTrigger:
    def test_trigger_requires_auth(self, api_client, create_managed_node, create_observed_node):
        mn = create_managed_node()
        on = create_observed_node()
        resp = api_client.post(
            "/api/traceroutes/trigger/",
            {"managed_node_id": mn.node_id, "target_node_id": on.node_id},
            format="json",
        )
        assert resp.status_code == 401

    def test_trigger_requires_permission(self, api_client, viewer_user, create_managed_node, create_observed_node):
        mn = create_managed_node()
        on = create_observed_node()
        api_client.force_authenticate(user=viewer_user)
        resp = api_client.post(
            "/api/traceroutes/trigger/",
            {"managed_node_id": mn.node_id, "target_node_id": on.node_id},
            format="json",
        )
        assert resp.status_code == 403

    def test_trigger_creates_auto_traceroute(self, api_client, editor_user, editor_managed_node, create_observed_node):
        mn = editor_managed_node
        on = create_observed_node()
        api_client.force_authenticate(user=editor_user)
        resp = api_client.post(
            "/api/traceroutes/trigger/",
            {"managed_node_id": mn.node_id, "target_node_id": on.node_id},
            format="json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["source_node"]["node_id"] == mn.node_id
        assert data["target_node"]["node_id"] == on.node_id
        assert data["trigger_type"] == "user"
        assert data["status"] == "sent"
        assert AutoTraceRoute.objects.filter(id=data["id"]).exists()

    def test_trigger_rejects_when_allow_auto_traceroute_disabled(
        self,
        api_client,
        editor_user,
        editor_managed_node,
        create_managed_node,
        create_observed_node,
    ):
        """Trigger returns 400 when managed node has allow_auto_traceroute=False."""
        # editor_managed_node gives editor permission (triggerable node); create a second node
        # in same constellation with allow_auto_traceroute=False
        constellation = editor_managed_node.constellation
        creator = constellation.created_by
        mn_disabled = create_managed_node(
            node_id=editor_managed_node.node_id + 1,
            owner=creator,
            constellation=constellation,
            allow_auto_traceroute=False,
        )
        on = create_observed_node()
        api_client.force_authenticate(user=editor_user)
        resp = api_client.post(
            "/api/traceroutes/trigger/",
            {"managed_node_id": mn_disabled.node_id, "target_node_id": on.node_id},
            format="json",
        )
        assert resp.status_code == 400
        assert "allow_auto_traceroute" in resp.json().get("detail", "").lower()

    def test_trigger_rejects_when_rate_limited(
        self, api_client, editor_user, editor_managed_node, create_observed_node
    ):
        """Trigger returns 429 when node's last traceroute was within 30s."""
        mn = editor_managed_node
        on = create_observed_node()
        api_client.force_authenticate(user=editor_user)
        resp1 = api_client.post(
            "/api/traceroutes/trigger/",
            {"managed_node_id": mn.node_id, "target_node_id": on.node_id},
            format="json",
        )
        assert resp1.status_code == 201
        resp2 = api_client.post(
            "/api/traceroutes/trigger/",
            {"managed_node_id": mn.node_id, "target_node_id": on.node_id},
            format="json",
        )
        assert resp2.status_code == 429
        assert "rate limited" in resp2.json().get("detail", "").lower()

    def test_trigger_staff_can_trigger_from_any_node(
        self, api_client, staff_user, create_managed_node, create_observed_node, add_traceroute_source_ingestion
    ):
        """Staff can trigger from any eligible ManagedNode."""
        mn = create_managed_node(allow_auto_traceroute=True)
        add_traceroute_source_ingestion(mn)
        on = create_observed_node()
        api_client.force_authenticate(user=staff_user)
        resp = api_client.post(
            "/api/traceroutes/trigger/",
            {"managed_node_id": mn.node_id, "target_node_id": on.node_id},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.json()["source_node"]["node_id"] == mn.node_id

    def test_trigger_owner_can_trigger_from_own_node(self, api_client, owner_managed_node, create_observed_node):
        """Owner can trigger from their own ManagedNode."""
        mn = owner_managed_node
        owner = mn.owner
        on = create_observed_node()
        api_client.force_authenticate(user=owner)
        resp = api_client.post(
            "/api/traceroutes/trigger/",
            {"managed_node_id": mn.node_id, "target_node_id": on.node_id},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.json()["source_node"]["node_id"] == mn.node_id

    def test_trigger_forbidden_when_no_permission(
        self, api_client, viewer_user, owner_managed_node, create_observed_node
    ):
        """User gets 403 when trying to trigger from a node they don't have permission for."""
        mn = owner_managed_node
        on = create_observed_node()
        api_client.force_authenticate(user=viewer_user)
        resp = api_client.post(
            "/api/traceroutes/trigger/",
            {"managed_node_id": mn.node_id, "target_node_id": on.node_id},
            format="json",
        )
        assert resp.status_code == 403

    def test_trigger_rejects_without_recent_ingestion(
        self,
        api_client,
        editor_user,
        create_managed_node,
        create_observed_node,
    ):
        """Trigger returns 400 when source has permission but no recent ingestion as observer."""
        membership = ConstellationUserMembership.objects.filter(user=editor_user, role="editor").first()
        constellation = membership.constellation
        creator = constellation.created_by
        mn = create_managed_node(
            owner=creator,
            constellation=constellation,
            allow_auto_traceroute=True,
            node_id=888_777_666,
        )
        on = create_observed_node()
        api_client.force_authenticate(user=editor_user)
        resp = api_client.post(
            "/api/traceroutes/trigger/",
            {"managed_node_id": mn.node_id, "target_node_id": on.node_id},
            format="json",
        )
        assert resp.status_code == 400
        assert "ingestion" in resp.json().get("detail", "").lower()


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
