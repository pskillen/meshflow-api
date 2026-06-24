from unittest.mock import Mock

from django.contrib.admin.sites import AdminSite

import pytest

from common.protocol import Protocol
from nodes.admin import ManagedNodeAdmin, ManagedNodeAdminForm
from nodes.managed_node_bootstrap import ensure_observed_node_for_managed_node
from nodes.models import ManagedNode, ObservedNode


@pytest.mark.django_db
def test_ensure_observed_node_creates_meshcore_row(create_user, create_constellation, create_managed_node):
    owner = create_user()
    constellation = create_constellation(protocol=Protocol.MESHCORE, created_by=owner)
    pubkey = "a" * 64
    managed = create_managed_node(
        owner=owner,
        constellation=constellation,
        protocol=Protocol.MESHCORE,
        meshtastic_node_id=None,
        mc_pubkey=pubkey,
        name="Bootstrap MC",
    )

    observed, created = ensure_observed_node_for_managed_node(managed)

    assert created is True
    assert observed.mc_pubkey == pubkey
    assert observed.claimed_by_id == owner.id
    assert ObservedNode.objects.filter(protocol=Protocol.MESHCORE, mc_pubkey=pubkey).count() == 1


@pytest.mark.django_db
def test_ensure_observed_node_creates_meshtastic_row(create_user, create_constellation, create_managed_node):
    owner = create_user()
    constellation = create_constellation(created_by=owner)
    node_id = 0x40440440
    managed = create_managed_node(
        owner=owner,
        constellation=constellation,
        protocol=Protocol.MESHTASTIC,
        meshtastic_node_id=node_id,
        name="Bootstrap MT",
    )

    observed, created = ensure_observed_node_for_managed_node(managed)

    assert created is True
    assert observed.meshtastic_node_id == node_id
    assert observed.claimed_by_id == owner.id
    assert observed.long_name == "Bootstrap MT"


@pytest.mark.django_db
def test_ensure_observed_node_claims_unclaimed_existing(create_user, create_observed_node, create_managed_node):
    owner = create_user()
    pubkey = "b" * 64
    observed = create_observed_node(
        protocol=Protocol.MESHCORE,
        meshtastic_node_id=None,
        mc_pubkey=pubkey,
        claimed_by=None,
    )
    managed = create_managed_node(
        owner=owner,
        protocol=Protocol.MESHCORE,
        meshtastic_node_id=None,
        mc_pubkey=pubkey,
    )

    result, created = ensure_observed_node_for_managed_node(managed)

    assert created is False
    assert result.pk == observed.pk
    result.refresh_from_db()
    assert result.claimed_by_id == owner.id
    assert ObservedNode.objects.filter(mc_pubkey=pubkey).count() == 1


@pytest.mark.django_db
def test_ensure_observed_node_does_not_steal_existing_claim(create_user, create_observed_node, create_managed_node):
    owner = create_user()
    other = create_user()
    pubkey = "c" * 64
    observed = create_observed_node(
        protocol=Protocol.MESHCORE,
        meshtastic_node_id=None,
        mc_pubkey=pubkey,
        claimed_by=other,
    )
    managed = create_managed_node(
        owner=owner,
        protocol=Protocol.MESHCORE,
        meshtastic_node_id=None,
        mc_pubkey=pubkey,
    )

    result, created = ensure_observed_node_for_managed_node(managed)

    assert created is False
    assert result.pk == observed.pk
    result.refresh_from_db()
    assert result.claimed_by_id == other.id


@pytest.mark.django_db
def test_managed_node_admin_save_model_bootstraps_meshcore_observed_node(create_user, create_constellation):
    owner = create_user()
    constellation = create_constellation(protocol=Protocol.MESHCORE, created_by=owner)
    pubkey = "d" * 64
    form = ManagedNodeAdminForm(
        data={
            "protocol": str(Protocol.MESHCORE),
            "meshtastic_node_id": "",
            "mc_pubkey": pubkey,
            "name": "Admin Bootstrap MC",
            "owner": owner.pk,
            "constellation": constellation.pk,
            "allow_auto_traceroute": False,
            "mc_flood_advert_interval_hours": 6,
            "latlong_0": "",
            "latlong_1": "",
        }
    )
    assert form.is_valid(), form.errors

    admin = ManagedNodeAdmin(ManagedNode, AdminSite())
    request = Mock()
    obj = form.save(commit=False)
    admin.save_model(request, obj, form, change=False)

    observed = ObservedNode.objects.get(mc_pubkey=pubkey)
    assert observed.claimed_by_id == owner.id
    assert ManagedNode.objects.filter(mc_pubkey=pubkey).exists()


@pytest.mark.django_db
def test_managed_node_admin_save_model_bootstraps_meshtastic_observed_node(create_user, create_constellation):
    owner = create_user()
    constellation = create_constellation(created_by=owner)
    node_id = 0x40440441
    form = ManagedNodeAdminForm(
        data={
            "protocol": str(Protocol.MESHTASTIC),
            "meshtastic_node_id": str(node_id),
            "name": "Admin Bootstrap MT",
            "owner": owner.pk,
            "constellation": constellation.pk,
            "allow_auto_traceroute": False,
            "latlong_0": "",
            "latlong_1": "",
        }
    )
    assert form.is_valid(), form.errors

    admin = ManagedNodeAdmin(ManagedNode, AdminSite())
    request = Mock()
    obj = form.save(commit=False)
    admin.save_model(request, obj, form, change=False)

    observed = ObservedNode.objects.get(meshtastic_node_id=node_id)
    assert observed.claimed_by_id == owner.id
    assert ManagedNode.objects.filter(meshtastic_node_id=node_id).exists()
