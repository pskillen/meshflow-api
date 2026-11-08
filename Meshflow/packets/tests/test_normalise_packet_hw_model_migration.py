from importlib import import_module

from django.apps import apps

import pytest

from packets.models import NodeInfoPacket

migration = import_module("packets.migrations.0021_normalise_hw_model")


@pytest.mark.django_db
def test_migration_rewrites_packet_hw_models(node_info_packet_data):
    def make(packet_id, hw_model):
        data = dict(node_info_packet_data, packet_id=packet_id, hw_model=hw_model)
        return NodeInfoPacket.objects.create(**data)

    numeric = make(1, "150")
    renamed = make(2, "SENSELORA_S3")
    known = make(3, "HELTEC_V3")
    unknown = make(4, "999")

    migration.normalise_stored_hw_models(apps, None)

    def stored(packet):
        return NodeInfoPacket.objects.get(pk=packet.pk).hw_model

    assert stored(numeric) == "THINKNODE_MX"
    assert stored(renamed) == "MAKERFABS_RESERVED"
    assert stored(known) == "HELTEC_V3"
    assert stored(unknown) == "HW_999"
    migration.Migration.operations[0].reverse_code(apps, None)
    assert stored(numeric) == "THINKNODE_MX"
