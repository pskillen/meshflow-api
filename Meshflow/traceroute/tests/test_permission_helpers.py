"""Tests for traceroute permission_helpers."""

import pytest

import nodes.tests.conftest  # noqa: F401 - load fixtures
import users.tests.conftest  # noqa: F401 - load fixtures
from constellations.models import ConstellationUserMembership
from traceroute.permission_helpers import user_can_trigger_from_node


@pytest.fixture
def staff_user(create_user):
    user = create_user()
    user.is_staff = True
    user.save()
    return user


@pytest.fixture
def owner_managed_node(create_user, create_managed_node, create_constellation):
    """ManagedNode owned by owner_user with allow_auto_traceroute=True."""
    owner = create_user()
    constellation = create_constellation(created_by=owner)
    return create_managed_node(
        owner=owner,
        constellation=constellation,
        allow_auto_traceroute=True,
    )


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
    """ManagedNode in constellation where editor_user has editor role (not owner)."""
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
class TestUserCanTriggerFromNode:
    def test_staff_can_trigger_from_any_node(self, staff_user, create_managed_node):
        """Staff can trigger from any ManagedNode."""
        mn = create_managed_node(allow_auto_traceroute=True)
        assert user_can_trigger_from_node(staff_user, mn) is True

    def test_owner_can_trigger_from_own_node(self, owner_managed_node):
        """Owner can trigger from their own ManagedNode."""
        owner = owner_managed_node.owner
        assert user_can_trigger_from_node(owner, owner_managed_node) is True

    def test_editor_can_trigger_from_constellation_node(self, editor_user, editor_managed_node):
        """Constellation editor can trigger from nodes in that constellation."""
        assert user_can_trigger_from_node(editor_user, editor_managed_node) is True

    def test_admin_can_trigger_from_constellation_node(self, create_user, create_constellation, create_managed_node):
        """Constellation admin can trigger from nodes in that constellation."""
        creator = create_user()
        constellation = create_constellation(created_by=creator)
        admin_user = create_user()
        ConstellationUserMembership.objects.create(user=admin_user, constellation=constellation, role="admin")
        mn = create_managed_node(owner=creator, constellation=constellation, allow_auto_traceroute=True)
        assert user_can_trigger_from_node(admin_user, mn) is True

    def test_viewer_cannot_trigger_from_constellation_node(self, viewer_user, create_managed_node):
        """Viewer cannot trigger (viewer role is not admin/editor)."""
        membership = ConstellationUserMembership.objects.filter(user=viewer_user, role="viewer").first()
        constellation = membership.constellation
        creator = constellation.created_by
        mn = create_managed_node(owner=creator, constellation=constellation, allow_auto_traceroute=True)
        assert user_can_trigger_from_node(viewer_user, mn) is False

    def test_owner_cannot_trigger_from_other_owners_node(self, owner_managed_node, create_user):
        """User cannot trigger from a node they don't own and aren't admin/editor for."""
        other_user = create_user()
        assert user_can_trigger_from_node(other_user, owner_managed_node) is False
