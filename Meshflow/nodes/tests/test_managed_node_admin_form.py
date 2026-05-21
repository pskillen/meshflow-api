import pytest

from common.protocol import Protocol
from nodes.admin import MANAGED_NODE_CHANNEL_FIELDS, ManagedNodeAdmin, ManagedNodeAdminForm
from nodes.models import ManagedNode


@pytest.mark.django_db
def test_managed_node_admin_form_meshcore_node_id_defaults_to_zero(create_user, create_constellation):
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
    assert form.is_valid(), form.errors
    assert form.cleaned_data["meshtastic_node_id"] == 0


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
