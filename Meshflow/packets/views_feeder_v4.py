"""v4 feeder URLs (``/api/v4/feeder/``): the API key alone identifies the feeder (ADR-0005).

Each view reuses the legacy view's body and response; only authorisation differs. There is no
node number in the path, so a Meshtastic 2.8 feeder whose number changes keeps working.
"""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.feeder_auth import FeederScopedPermission
from common.protocol import Protocol
from nodes.authentication import NodeAPIKeyAuthentication

from .views import ManagedNodeBotVersionView, NodeUpsertViewV3, PacketIngestView

_PROTOCOL_WIRE = {
    Protocol.MESHTASTIC: "meshtastic",
    Protocol.MESHCORE: "meshcore",
}


def identity_mismatch(managed_node) -> bool:
    """True when the feeder last reported a node number other than the stored one."""
    reported = getattr(managed_node, "reported_meshtastic_node_id", None)
    return reported is not None and reported != managed_node.meshtastic_node_id


class FeederIdentityView(APIView):
    """``GET identity/``: which feeder this API key identifies. The bot's v4 probe."""

    authentication_classes = [NodeAPIKeyAuthentication]
    permission_classes = [FeederScopedPermission]
    feeder_protocol = None

    def get(self, request, format=None):
        node = request.auth.node
        return Response(
            {
                "internal_id": str(node.internal_id),
                "protocol": _PROTOCOL_WIRE.get(node.protocol, str(node.protocol)),
                "name": node.name,
                "constellation_id": node.constellation_id,
                "meshtastic_node_id": node.meshtastic_node_id,
                "node_id_str": node.node_id_str,
                "reported_meshtastic_node_id": getattr(node, "reported_meshtastic_node_id", None),
                "identity_mismatch": identity_mismatch(node),
            },
            status=status.HTTP_200_OK,
        )


class FeederBotVersionViewV4(ManagedNodeBotVersionView):
    """``bot-version/`` for any protocol; same body and response as the legacy view."""

    permission_classes = [FeederScopedPermission]
    feeder_protocol = None


class FeederMeshtasticIngestViewV4(PacketIngestView):
    """``meshtastic/ingest/``; same body and response as the legacy ingest view."""

    permission_classes = [FeederScopedPermission]
    feeder_protocol = Protocol.MESHTASTIC


class FeederMeshtasticNodeUpsertViewV4(NodeUpsertViewV3):
    """``meshtastic/nodes/``; strict ``meshtastic_*`` wire as v3, with no path-number check."""

    permission_classes = [FeederScopedPermission]
    feeder_protocol = Protocol.MESHTASTIC
