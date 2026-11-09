"""The unique Meshtastic node number constraint and the migration that adds it (#480 part 2)."""

from importlib import import_module

from django.apps import apps
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

import pytest

from common.protocol import Protocol
from nodes.models import ObservedNode

migration = import_module("nodes.migrations.0059_observednode_mt_node_id_unique")

NODE = 0x1A2B3C4D
INDEX = "nodes_observednode_mt_node_id_unique"


def _drop_index():
    with connection.cursor() as cursor:
        cursor.execute(f"DROP INDEX {INDEX}")


def _mt(node_id=NODE, **fields):
    return ObservedNode.objects.create(protocol=Protocol.MESHTASTIC, meshtastic_node_id=node_id, **fields)


def _count(node_id=NODE):
    return ObservedNode.objects.filter(protocol=Protocol.MESHTASTIC, meshtastic_node_id=node_id).count()


@pytest.mark.django_db
def test_second_meshtastic_row_with_same_number_is_rejected():
    _mt()
    with pytest.raises(IntegrityError), transaction.atomic():
        _mt()
    assert _count() == 1


@pytest.mark.django_db
def test_meshcore_rows_with_null_node_number_are_unaffected():
    for i in range(2):
        ObservedNode.objects.create(
            protocol=Protocol.MESHCORE, meshtastic_node_id=None, mc_pubkey=f"{i:064x}", long_name=f"mc{i}"
        )
    assert ObservedNode.objects.filter(protocol=Protocol.MESHCORE).count() == 2


@pytest.mark.django_db
def test_migration_on_clean_data_changes_nothing():
    _mt()
    _mt(NODE + 1)
    before = sorted(ObservedNode.objects.values_list("pk", flat=True))
    migration.merge_duplicate_nodes(apps, None)
    assert sorted(ObservedNode.objects.values_list("pk", flat=True)) == before


@pytest.mark.django_db
def test_migration_merges_a_duplicate_set_into_one_row():
    keeper = _mt()
    _drop_index()
    dup = _mt(long_name="Real Name", short_name="REAL", last_heard=timezone.now())
    _mt(NODE + 1)
    assert _count() == 2

    migration.merge_duplicate_nodes(apps, None)

    assert _count() == 1
    row = ObservedNode.objects.get(meshtastic_node_id=NODE)
    assert row.pk == keeper.pk
    assert row.long_name == "Real Name"
    assert not ObservedNode.objects.filter(pk=dup.pk).exists()
    assert _count(NODE + 1) == 1


@pytest.mark.django_db
def test_migration_raises_naming_the_nodes_when_a_set_cannot_merge(django_user_model):
    alice = django_user_model.objects.create_user(username="alice", password="x")
    bob = django_user_model.objects.create_user(username="bob", password="x")
    _mt(claimed_by=alice)
    _drop_index()
    _mt(claimed_by=bob)

    with pytest.raises(RuntimeError) as exc:
        migration.merge_duplicate_nodes(apps, None)

    assert "!1a2b3c4d" in str(exc.value)
    assert _count() == 2


def test_migration_reverse_is_a_noop_and_adds_the_constraint():
    ops = migration.Migration.operations
    assert ops[0].reverse_code is migration.migrations.RunPython.noop
    assert ops[1].constraint.name == INDEX
