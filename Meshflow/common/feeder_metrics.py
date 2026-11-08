"""Feeder API usage tracking: which URL generation each feeder uses, and what number it reports.

Prometheus (one daphne process, so in-process counters are enough):

- ``meshflow_feeder_api_requests_total{api, protocol, endpoint, status_class}``;
- ``meshflow_feeder_auth_rejections_total{api, code}``.

``api`` is ``v2``, ``v3``, ``mc_prefix`` or ``v4``. No per-feeder labels: the DB fields below
carry per-feeder state and survive restarts.

``FeederApiUsageMixin`` goes on every feeder view (legacy Meshtastic, MeshCore prefix, v4). Once
the feeder is resolved it records, in one ``update()`` and at most every 10 minutes per feeder
unless something changed:

- ``feeder_api_generation`` / ``feeder_api_last_used_at`` (and ``legacy_api_last_used_at`` for
  pre-v4 URLs), so staff can list the feeders still on legacy URLs (ADR-0005);
- ``reported_meshtastic_node_id`` / ``identity_reported_at`` from ``X-Meshtastic-Feeder-Node-Num``
  (or ``meshtastic_node_num`` in a bot-version body). Informational only: never authorises,
  never changes ``meshtastic_node_id``;
- ``reported_firmware_version`` / ``firmware_reported_at`` from ``X-Meshtastic-Feeder-Firmware`` (or
  ``meshtastic_firmware_version`` in a bot-version body), Meshtastic feeders only. It feeds the ``feeder_report``
  firmware rule (``nodes.services.node_firmware.refresh_feeder_row``).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from django.utils import timezone

from prometheus_client import Counter

from common.mesh_node_helpers import meshtastic_id_to_hex
from common.protocol import Protocol
from nodes.models import ManagedNode
from nodes.services.node_firmware import refresh_feeder_row

logger = logging.getLogger(__name__)

FEEDER_USAGE_WRITE_INTERVAL = timedelta(minutes=10)

API_V2 = ManagedNode.FeederApiGeneration.V2.value
API_V3 = ManagedNode.FeederApiGeneration.V3.value
API_MC_PREFIX = ManagedNode.FeederApiGeneration.MC_PREFIX.value
API_V4 = ManagedNode.FeederApiGeneration.V4.value

FEEDER_API_REQUESTS = Counter(
    "meshflow_feeder_api_requests_total",
    "Feeder API requests by URL generation, protocol, endpoint and status class",
    ["api", "protocol", "endpoint", "status_class"],
)
FEEDER_AUTH_REJECTIONS = Counter(
    "meshflow_feeder_auth_rejections_total",
    "Feeder API authorisation rejections by URL generation and code",
    ["api", "code"],
)

_PROTOCOL_LABELS = {
    Protocol.MESHTASTIC: "meshtastic",
    Protocol.MESHCORE: "meshcore",
}

REPORTED_NODE_NUM_HEADER = "HTTP_X_MESHTASTIC_FEEDER_NODE_NUM"
_MAX_MESHTASTIC_NODE_NUM = 0xFFFFFFFF
REPORTED_FIRMWARE_HEADER = "HTTP_X_MESHTASTIC_FEEDER_FIRMWARE"
_MAX_FIRMWARE_LENGTH = 64


def parse_reported_node_num(value) -> Optional[int]:
    """Decimal node number from a header or body value; None when absent or not a valid number."""
    if value is None or isinstance(value, bool):
        return None
    try:
        num = int(str(value).strip(), 10)
    except ValueError:
        return None
    if num < 0 or num > _MAX_MESHTASTIC_NODE_NUM:
        return None
    return num


def parse_reported_firmware(value) -> Optional[str]:
    """Stripped firmware version string from a header or body value; None when absent, blank or over-long."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > _MAX_FIRMWARE_LENGTH:
        return None
    return value


def protocol_label(protocol) -> str:
    return _PROTOCOL_LABELS.get(protocol, "unknown")


def record_feeder_request(*, api: str, protocol: str, endpoint: str, status_code: int) -> None:
    try:
        FEEDER_API_REQUESTS.labels(
            api=api,
            protocol=protocol,
            endpoint=endpoint,
            status_class=f"{int(status_code) // 100}xx",
        ).inc()
    except Exception:
        pass


def record_feeder_auth_rejection(*, api: str, code: str) -> None:
    try:
        FEEDER_AUTH_REJECTIONS.labels(api=api, code=code).inc()
    except Exception:
        pass


def _stale(when, now) -> bool:
    return when is None or now - when >= FEEDER_USAGE_WRITE_INTERVAL


def record_feeder_usage(
    node: ManagedNode,
    *,
    api: str,
    reported_node_num: Optional[int] = None,
    reported_firmware: Optional[str] = None,
    now=None,
) -> dict:
    """Write the usage, reported-identity and reported-firmware fields for ``node`` if due; return what was written."""
    now = now or timezone.now()
    fields = {}

    if node.feeder_api_generation != api or _stale(node.feeder_api_last_used_at, now):
        fields["feeder_api_generation"] = api
        fields["feeder_api_last_used_at"] = now
    if api != API_V4 and ("feeder_api_generation" in fields or _stale(node.legacy_api_last_used_at, now)):
        fields["legacy_api_last_used_at"] = now

    if reported_node_num is not None and node.protocol == Protocol.MESHTASTIC:
        if reported_node_num != node.reported_meshtastic_node_id or _stale(node.identity_reported_at, now):
            fields["reported_meshtastic_node_id"] = reported_node_num
            fields["identity_reported_at"] = now
            if reported_node_num != node.meshtastic_node_id:
                logger.warning(
                    "Feeder %s (%s) reported node number %s but is stored as %s; "
                    "ingest continues under the API key's feeder",
                    node.internal_id,
                    node.name,
                    meshtastic_id_to_hex(reported_node_num),
                    meshtastic_id_to_hex(node.meshtastic_node_id),
                )

    if reported_firmware is not None and node.protocol == Protocol.MESHTASTIC:
        if reported_firmware != node.reported_firmware_version or _stale(node.firmware_reported_at, now):
            fields["reported_firmware_version"] = reported_firmware
            fields["firmware_reported_at"] = now

    if fields:
        ManagedNode.objects.filter(pk=node.pk).update(**fields)
        for name, value in fields.items():
            setattr(node, name, value)
        if "reported_firmware_version" in fields:
            refresh_feeder_row(node, now=now)
    return fields


class FeederApiUsageMixin:
    """Track feeder API usage on a DRF view. Put it before ``APIView`` in the bases.

    Class attributes:

    - ``feeder_api``: ``"v4"`` or ``"mc_prefix"``; None means a legacy Meshtastic view, told
      apart as v2 or v3 by its URL name.
    - ``feeder_endpoint``: short endpoint label (``ingest``, ``nodes``, ``bot-version`` ...).
    - ``reported_node_num_body_field``: body field to read the reported number from when the
      header is absent (bot-version only).
    - ``reported_firmware_body_field``: the same for the reported firmware version.
    """

    feeder_api: Optional[str] = None
    feeder_endpoint: str = "unknown"
    reported_node_num_body_field: Optional[str] = None
    reported_firmware_body_field: Optional[str] = None

    def get_feeder_api(self, request) -> str:
        if self.feeder_api:
            return self.feeder_api
        resolver_match = getattr(request, "resolver_match", None)
        url_name = getattr(resolver_match, "url_name", None) or ""
        return API_V3 if url_name.endswith("-v3") else API_V2

    def get_feeder_protocol_label(self, request) -> str:
        node = self._resolved_feeder(request)
        if node is not None:
            return protocol_label(node.protocol)
        declared = getattr(self, "feeder_protocol", None)
        if declared is not None:
            return protocol_label(declared)
        api = self.get_feeder_api(request)
        if api in (API_V2, API_V3):
            return "meshtastic"
        if api == API_MC_PREFIX:
            return "meshcore"
        return "unknown"

    def _resolved_feeder(self, request) -> Optional[ManagedNode]:
        # ``_auth`` avoids re-running authentication when it failed or never ran.
        auth = getattr(request, "_auth", None)
        return getattr(auth, "node", None) if auth is not None else None

    def _reported_node_num(self, request) -> Optional[int]:
        num = parse_reported_node_num(request.META.get(REPORTED_NODE_NUM_HEADER))
        if num is None and self.reported_node_num_body_field:
            try:
                data = request.data
                value = data.get(self.reported_node_num_body_field) if hasattr(data, "get") else None
            except Exception:
                value = None
            num = parse_reported_node_num(value)
        return num

    def _reported_firmware(self, request) -> Optional[str]:
        firmware = parse_reported_firmware(request.META.get(REPORTED_FIRMWARE_HEADER))
        if firmware is None and self.reported_firmware_body_field:
            try:
                data = request.data
                value = data.get(self.reported_firmware_body_field) if hasattr(data, "get") else None
            except Exception:
                value = None
            firmware = parse_reported_firmware(value)
        return firmware

    def record_feeder_usage(self, request) -> None:
        """Record usage for this request once (views may call it early, e.g. ``identity/``)."""
        if getattr(request, "_feeder_usage_recorded", False):
            return
        node = self._resolved_feeder(request)
        if node is None:
            return
        request._feeder_usage_recorded = True
        try:
            record_feeder_usage(
                node,
                api=self.get_feeder_api(request),
                reported_node_num=self._reported_node_num(request),
                reported_firmware=self._reported_firmware(request),
            )
        except Exception:
            logger.exception("Failed to record feeder API usage for %s", node.pk)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        self.record_feeder_usage(request)
        try:
            record_feeder_request(
                api=self.get_feeder_api(request),
                protocol=self.get_feeder_protocol_label(request),
                endpoint=self.feeder_endpoint,
                status_code=response.status_code,
            )
        except Exception:
            pass
        return response
