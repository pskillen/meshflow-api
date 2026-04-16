"""DM text formatting for mesh_monitoring notify_watchers_* services (#164)."""

from unittest.mock import patch

from django.test.utils import override_settings

import pytest

import nodes.tests.conftest  # noqa: F401
from common.mesh_node_helpers import meshtastic_id_to_hex
from mesh_monitoring.models import NodeWatch
from mesh_monitoring.services import notify_watchers_node_offline, notify_watchers_verification_started


@pytest.mark.django_db
def test_offline_dm_includes_short_name_and_deep_link(create_user, create_observed_node):
    user = create_user()
    node_id = 0x11223344
    obs = create_observed_node(
        node_id=node_id,
        node_id_str=meshtastic_id_to_hex(node_id),
        long_name="My Long Node Name",
        short_name="MLNN",
        claimed_by=user,
    )
    NodeWatch.objects.create(user=user, observed_node=obs, offline_after=60, enabled=True)

    with override_settings(FRONTEND_URL="https://mesh.example/"):
        with patch("mesh_monitoring.services.user_has_verified_discord_dm_target", return_value=True):
            with patch("mesh_monitoring.services.send_dm") as send_dm:
                attempted = notify_watchers_node_offline(obs)

    assert attempted == 1
    send_dm.assert_called_once()
    body = send_dm.call_args[0][1]
    assert obs.node_id_str in body
    assert "MLNN" in body
    assert "My Long Node Name" in body
    assert f"https://mesh.example/nodes/{obs.node_id}" in body
    assert "appears offline" in body


@pytest.mark.django_db
def test_offline_dm_omits_url_when_frontend_unset(create_user, create_observed_node):
    user = create_user()
    node_id = 0x22334455
    obs = create_observed_node(
        node_id=node_id,
        node_id_str=meshtastic_id_to_hex(node_id),
        long_name="Another Node",
        short_name="ANOD",
        claimed_by=user,
    )
    NodeWatch.objects.create(user=user, observed_node=obs, offline_after=60, enabled=True)

    with override_settings(FRONTEND_URL=""):
        with patch("mesh_monitoring.services.user_has_verified_discord_dm_target", return_value=True):
            with patch("mesh_monitoring.services.send_dm") as send_dm:
                notify_watchers_node_offline(obs)

    body = send_dm.call_args[0][1]
    assert "ANOD" in body
    assert "/nodes/" not in body


@pytest.mark.django_db
def test_verification_start_dm_includes_short_name_and_deep_link(create_user, create_observed_node):
    user = create_user()
    node_id = 0x33445566
    obs = create_observed_node(
        node_id=node_id,
        node_id_str=meshtastic_id_to_hex(node_id),
        long_name="Verify Me",
        short_name="VFYM",
        claimed_by=user,
    )
    NodeWatch.objects.create(user=user, observed_node=obs, offline_after=90, enabled=True)

    with override_settings(FRONTEND_URL="https://mesh.example"):
        with patch("mesh_monitoring.services.user_has_verified_discord_dm_target", return_value=True):
            with patch("mesh_monitoring.services.send_dm") as send_dm:
                attempted = notify_watchers_verification_started(obs, silence_threshold_seconds=90)

    assert attempted == 1
    body = send_dm.call_args[0][1]
    assert obs.node_id_str in body
    assert "VFYM" in body
    assert "Verify Me" in body
    assert "90" in body
    assert f"https://mesh.example/nodes/{obs.node_id}" in body
