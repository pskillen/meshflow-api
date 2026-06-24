import pytest

from common.protocol import Protocol
from nodes.admin import MANAGED_NODE_CHANNEL_FIELDS, ManagedNodeAdmin, ManagedNodeAdminForm
from nodes.models import ManagedNode


class _PostRequest:
    def __init__(self, protocol):
        self.method = "POST"
        self.POST = {"protocol": str(protocol)}


@pytest.mark.django_db
def test_managed_node_admin_form_meshcore_clears_meshtastic_node_id(create_user, create_constellation):
    owner = create_user()
    constellation = create_constellation(created_by=owner)
    form = ManagedNodeAdminForm(
        data={
            "protocol": str(Protocol.MESHCORE),
            "meshtastic_node_id": "",
            "mc_pubkey": "a" * 64,
            "name": "MC Feeder",
            "owner": owner.pk,
            "constellation": constellation.pk,
            "allow_auto_traceroute": False,
            "latlong_0": "",
            "latlong_1": "",
        }
    )
    assert form.is_valid(), form.errors
    assert form.cleaned_data["meshtastic_node_id"] is None


@pytest.mark.django_db
def test_managed_node_admin_form_meshcore_requires_mc_pubkey(create_user, create_constellation):
    owner = create_user()
    constellation = create_constellation(created_by=owner)
    form = ManagedNodeAdminForm(
        data={
            "protocol": str(Protocol.MESHCORE),
            "meshtastic_node_id": "",
            "name": "MC Feeder",
            "owner": owner.pk,
            "constellation": constellation.pk,
            "allow_auto_traceroute": False,
            "latlong_0": "",
            "latlong_1": "",
        }
    )
    assert not form.is_valid()
    assert "mc_pubkey" in form.errors


def test_managed_node_channel_admin_fields_match_model():
    model_fields = {f.name for f in ManagedNode._meta.get_fields()}
    assert MANAGED_NODE_CHANNEL_FIELDS == tuple(f"meshtastic_channel_{i}" for i in range(8))
    assert set(MANAGED_NODE_CHANNEL_FIELDS).issubset(model_fields)


@pytest.mark.django_db
def test_managed_node_admin_fieldsets_include_meshtastic_channels(create_managed_node):
    node = create_managed_node()
    admin = ManagedNodeAdmin(ManagedNode, None)
    fieldsets = admin.get_fieldsets(request=None, obj=node)
    channel_section = next(fs for fs in fieldsets if fs[0] == "Meshtastic channels")
    assert channel_section[1]["fields"] == MANAGED_NODE_CHANNEL_FIELDS


@pytest.mark.django_db
def test_managed_node_admin_add_fieldsets_meshcore_show_pubkey():
    admin = ManagedNodeAdmin(ManagedNode, None)
    fieldsets = admin.get_fieldsets(request=_PostRequest(Protocol.MESHCORE), obj=None)
    titles = [section[0] for section in fieldsets]
    assert "MeshCore identity" in titles
    assert "Meshtastic channels" not in titles
    identity = next(section for section in fieldsets if section[0] == "MeshCore identity")
    assert identity[1]["fields"] == ("mc_pubkey",)
    feeder = next(section for section in fieldsets if section[0] == "Feeder")
    assert "meshtastic_node_id" not in feeder[1]["fields"]
    assert "mc_flood_advert_interval_hours" in feeder[1]["fields"]


@pytest.mark.django_db
def test_managed_node_admin_observed_node_link(create_managed_node, create_observed_node):
    managed = create_managed_node()
    observed = create_observed_node(meshtastic_node_id=managed.meshtastic_node_id)
    admin = ManagedNodeAdmin(ManagedNode, None)
    html = admin.observed_node_link(managed)
    assert str(observed) in html
    assert f"admin/nodes/observednode/{observed.pk}/change/" in html


@pytest.mark.django_db
def test_managed_node_admin_observed_node_link_missing(create_managed_node):
    managed = create_managed_node(meshtastic_node_id=0x99999999)
    admin = ManagedNodeAdmin(ManagedNode, None)
    assert admin.observed_node_link(managed) == "—"


@pytest.mark.django_db
def test_managed_node_admin_add_fieldsets_meshtastic_show_node_id_and_channels():
    admin = ManagedNodeAdmin(ManagedNode, None)
    fieldsets = admin.get_fieldsets(request=_PostRequest(Protocol.MESHTASTIC), obj=None)
    titles = [section[0] for section in fieldsets]
    assert "Meshtastic channels" in titles
    assert "MeshCore identity" not in titles
    feeder = next(section for section in fieldsets if section[0] == "Feeder")
    assert "meshtastic_node_id" in feeder[1]["fields"]
