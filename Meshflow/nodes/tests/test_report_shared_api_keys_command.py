from io import StringIO

from django.core.management import call_command
from django.utils import timezone

import pytest

from common.protocol import Protocol
from nodes.models import NodeAPIKey, NodeAuth


def _run():
    out = StringIO()
    call_command("report_shared_api_keys", stdout=out)
    return out.getvalue()


@pytest.mark.django_db
def test_report_lists_shared_keys_and_totals(
    create_user, create_managed_node, create_node_api_key, create_constellation
):
    owner = create_user(username="alice")
    mt_const = create_constellation(created_by=owner)
    mt_a = create_managed_node(owner=owner, constellation=mt_const, name="Feeder A")
    mt_b = create_managed_node(owner=owner, constellation=mt_const, name="Feeder B")
    shared = create_node_api_key(owner=owner, constellation=mt_const, name="Shared MT")
    shared.last_used = timezone.now()
    shared.save()
    NodeAuth.objects.create(api_key=shared, node=mt_a)
    NodeAuth.objects.create(api_key=shared, node=mt_b)

    # cross-protocol key
    mc_const = create_constellation(protocol=Protocol.MESHCORE, created_by=owner, name="MC")
    mc_node = create_managed_node(
        owner=owner, constellation=mc_const, protocol=Protocol.MESHCORE, mc_pubkey="c" * 64, name="MC feeder"
    )
    mixed = create_node_api_key(owner=owner, constellation=mt_const, name="Mixed")
    NodeAuth.objects.create(api_key=mixed, node=mt_a)
    NodeAuth.objects.create(api_key=mixed, node=mc_node)

    # single-link key and a key whose second link is soft-deleted are not reported
    single = create_node_api_key(owner=owner, constellation=mt_const, name="Single")
    NodeAuth.objects.create(api_key=single, node=mt_a)
    gone = create_managed_node(owner=owner, constellation=mt_const, name="Gone")
    half = create_node_api_key(owner=owner, constellation=mt_const, name="Half dead")
    NodeAuth.objects.create(api_key=half, node=mt_a)
    NodeAuth.objects.create(api_key=half, node=gone)
    type(gone).objects.filter(pk=gone.pk).update(deleted_at=timezone.now())

    before = (NodeAPIKey.objects.count(), NodeAuth.objects.count())
    output = _run()

    assert f"Key: Shared MT ({shared.id})" in output
    assert f"Key: Mixed ({mixed.id})" in output
    assert "Single" not in output
    assert "Half dead" not in output
    assert "owner: alice" in output
    assert "Feeder A" in output and "Feeder B" in output
    assert "Meshtastic" in output and "MeshCore" in output
    assert "last_used: never" in output  # Mixed
    assert "Keys shared by more than one feeder: 2" in output
    assert "Keys linked across both protocols: 1" in output
    assert (NodeAPIKey.objects.count(), NodeAuth.objects.count()) == before


@pytest.mark.django_db
def test_report_with_no_shared_keys(create_node_auth):
    create_node_auth()
    output = _run()
    assert "Keys shared by more than one feeder: 0" in output
    assert "Keys linked across both protocols: 0" in output
