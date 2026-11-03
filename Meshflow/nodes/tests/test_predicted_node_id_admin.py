"""Admin search / filter on the predicted Meshtastic 2.8 node id."""

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

import pytest

from nodes.admin import ObservedNodeAdmin, PredictedNodeIdFilter
from nodes.models import ObservedNode

KEY_HEX = "a0b3a9cf5a7b5bcfd38bc67488e5384ea6406150177b75309bc105fe6d732c5b"


@pytest.fixture
def node_with_prediction(create_observed_node):
    return create_observed_node(
        meshtastic_node_id=0xDA545C78,
        meshtastic_public_key_hex=KEY_HEX,
        meshtastic_key_node_id=0x4396524C,
    )


@pytest.mark.django_db
def test_admin_search_finds_node_by_predicted_id(node_with_prediction, create_observed_node):
    create_observed_node(meshtastic_node_id=42, short_name="OTHR", long_name="Other")
    model_admin = ObservedNodeAdmin(ObservedNode, AdminSite())
    request = RequestFactory().get("/")

    qs, _ = model_admin.get_search_results(request, ObservedNode.objects.all(), "!4396524c")
    assert list(qs) == [node_with_prediction]

    qs, _ = model_admin.get_search_results(request, ObservedNode.objects.all(), KEY_HEX[:16])
    assert list(qs) == [node_with_prediction]


@pytest.mark.django_db
def test_admin_filter_on_predicted_id(node_with_prediction, create_observed_node):
    other = create_observed_node(meshtastic_node_id=43, short_name="OTHR", long_name="Other")
    model_admin = ObservedNodeAdmin(ObservedNode, AdminSite())
    request = RequestFactory().get("/")

    yes = PredictedNodeIdFilter(request, {"predicted_28_id": ["yes"]}, ObservedNode, model_admin)
    no = PredictedNodeIdFilter(request, {"predicted_28_id": ["no"]}, ObservedNode, model_admin)
    assert list(yes.queryset(request, ObservedNode.objects.all())) == [node_with_prediction]
    assert list(no.queryset(request, ObservedNode.objects.all())) == [other]


@pytest.mark.django_db
def test_admin_displays_predicted_id(node_with_prediction):
    model_admin = ObservedNodeAdmin(ObservedNode, AdminSite())
    assert model_admin.predicted_node_id_str(node_with_prediction) == "!4396524c"
