"""Tests for traceroute views."""

from django.db import connection
from django.test.utils import CaptureQueriesContext

import pytest
from rest_framework.test import APIClient

import nodes.tests.conftest  # noqa: F401 - load fixtures
import users.tests.conftest  # noqa: F401 - load fixtures
from constellations.models import ConstellationUserMembership
from traceroute.models import AutoTraceRoute


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
def editor_managed_node(editor_user, create_constellation, create_managed_node):
    """Managed node in a constellation where editor_user has editor role."""
    membership = ConstellationUserMembership.objects.filter(user=editor_user, role="editor").first()
    constellation = membership.constellation
    return create_managed_node(
        owner=membership.constellation.created_by,
        constellation=constellation,
        allow_auto_traceroute=True,
    )


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


@pytest.mark.django_db
class TestTracerouteCanTrigger:
    def test_can_trigger_requires_auth(self, api_client):
        resp = api_client.get("/api/traceroutes/can_trigger/")
        assert resp.status_code == 401

    def test_can_trigger_true_for_staff(self, api_client, staff_user):
        api_client.force_authenticate(user=staff_user)
        resp = api_client.get("/api/traceroutes/can_trigger/")
        assert resp.status_code == 200
        assert resp.json()["can_trigger"] is True

    def test_can_trigger_true_for_editor(self, api_client, editor_user):
        api_client.force_authenticate(user=editor_user)
        resp = api_client.get("/api/traceroutes/can_trigger/")
        assert resp.status_code == 200
        assert resp.json()["can_trigger"] is True

    def test_can_trigger_false_for_viewer(self, api_client, viewer_user):
        api_client.force_authenticate(user=viewer_user)
        resp = api_client.get("/api/traceroutes/can_trigger/")
        assert resp.status_code == 200
        assert resp.json()["can_trigger"] is False


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
        create_user,
        create_managed_node,
        create_observed_node,
        create_constellation,
    ):
        """Trigger returns 400 when managed node has allow_auto_traceroute=False."""
        creator = create_user()
        constellation = create_constellation(created_by=creator)
        ConstellationUserMembership.objects.create(user=editor_user, constellation=constellation, role="editor")
        mn = create_managed_node(
            owner=creator,
            constellation=constellation,
            allow_auto_traceroute=False,
        )
        on = create_observed_node()
        api_client.force_authenticate(user=editor_user)
        resp = api_client.post(
            "/api/traceroutes/trigger/",
            {"managed_node_id": mn.node_id, "target_node_id": on.node_id},
            format="json",
        )
        assert resp.status_code == 400
        assert "allow_auto_traceroute" in resp.json().get("detail", "").lower()
