import pytest

from common.protocol import Protocol
from nodes.admin import ManagedNodeAdminForm


@pytest.mark.django_db
def test_managed_node_admin_form_meshcore_node_id_defaults_to_zero(create_user, create_constellation):
    owner = create_user()
    constellation = create_constellation(created_by=owner)
    form = ManagedNodeAdminForm(
        data={
            "protocol": str(Protocol.MESHCORE),
            "node_id": "",
            "name": "MC Feeder",
            "owner": owner.pk,
            "constellation": constellation.pk,
            "allow_auto_traceroute": False,
            "latlong_0": "",
            "latlong_1": "",
        }
    )
    assert form.is_valid(), form.errors
    assert form.cleaned_data["node_id"] == 0
