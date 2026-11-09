from importlib import import_module

from django.apps import apps

import pytest

from nodes.models import ObservedNode

migration = import_module("nodes.migrations.0056_normalise_hw_model")


def test_normalise_leaves_non_ascii_digits_alone():
    assert migration._normalise("²") == "²"


@pytest.mark.django_db
def test_migration_rewrites_numbers_and_renames_and_leaves_names_alone():
    numeric = ObservedNode.objects.create(meshtastic_node_id=910001, meshtastic_hw_model="150")
    unknown = ObservedNode.objects.create(meshtastic_node_id=910002, meshtastic_hw_model="999")
    renamed = ObservedNode.objects.create(meshtastic_node_id=910003, meshtastic_hw_model="TRACKER_T1000_E_PRO")
    known = ObservedNode.objects.create(meshtastic_node_id=910004, meshtastic_hw_model="HELTEC_V3")
    blank = ObservedNode.objects.create(meshtastic_node_id=910005, meshtastic_hw_model="")
    unset = ObservedNode.objects.create(meshtastic_node_id=910006, meshtastic_hw_model=None)

    migration.normalise_stored_hw_models(apps, None)

    def stored(node):
        return ObservedNode.objects.get(pk=node.pk).meshtastic_hw_model

    assert stored(numeric) == "THINKNODE_MX"
    assert stored(unknown) == "HW_999"
    assert stored(renamed) == "MESH_TRACKER_X1"
    assert stored(known) == "HELTEC_V3"
    assert stored(blank) == ""
    assert stored(unset) is None


@pytest.mark.django_db
def test_migration_batches_and_reverse_is_a_noop(monkeypatch):
    monkeypatch.setattr(migration, "BATCH_SIZE", 2)
    for i in range(5):
        ObservedNode.objects.create(meshtastic_node_id=920000 + i, meshtastic_hw_model="151")

    migration.normalise_stored_hw_models(apps, None)

    assert ObservedNode.objects.filter(meshtastic_hw_model="NODARA").count() == 5
    reverse = migration.Migration.operations[0].reverse_code
    reverse(apps, None)
    assert ObservedNode.objects.filter(meshtastic_hw_model="NODARA").count() == 5
