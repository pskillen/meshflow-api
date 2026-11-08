"""Detection of Meshtastic 2.8's connect-time replay packets.

After ``config_complete_id`` a 2.8 radio replays its stored per-node records (POSITION, TELEMETRY and NODE_STATUS,
one set per NodeDB entry) to every client that asks for full config. They look like received packets but are not
radio receptions. A replayed packet:

- has no ``rxRssi`` (every real LoRa reception sets it);
- carries ``transportMechanism`` ``TRANSPORT_LORA`` and ``priority`` ``BACKGROUND`` (live packets never carry a
  priority);
- is never the feeder's own packet.

MQTT-downlinked live packets also lack ``rxRssi`` but are ``TRANSPORT_MQTT``, so the transport check keeps them
out.

The bot (meshflow-bot, ``REPLAYED_PACKETS``) applies the same four-part rule before upload. Keep the two in step.
"""

from __future__ import annotations

from typing import Mapping, Optional

from django.conf import settings

from common.feeder_metrics import REPORTED_NODE_NUM_HEADER, parse_reported_node_num

_LORA_TRANSPORTS = ("TRANSPORT_LORA", 1)
_BACKGROUND_PRIORITIES = ("BACKGROUND", 10)


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _in(value, allowed) -> bool:
    # bool is an int subclass; True == 1 must not pass as TRANSPORT_LORA.
    return not isinstance(value, bool) and value in allowed


def is_replayed_shape(data: Mapping, feeder_nums: set[int]) -> bool:
    """True when ``data`` has the shape of a 2.8 connect-time replay.

    All of: ``from`` is an int and not one of the feeder's own node numbers; ``rxRssi`` absent or null;
    ``transportMechanism`` is TRANSPORT_LORA (or 1); ``priority`` is BACKGROUND (or 10). An empty ``feeder_nums``
    means the feeder's identity is unknown, so nothing is treated as a replay (fail towards live data).
    """
    if not feeder_nums:
        return False
    from_num = data.get("from")
    if not _is_int(from_num) or from_num in feeder_nums:
        return False
    if data.get("rxRssi") is not None:
        return False
    if not _in(data.get("transportMechanism"), _LORA_TRANSPORTS):
        return False
    return _in(data.get("priority"), _BACKGROUND_PRIORITIES)


def feeder_node_nums(observer, request=None) -> set[int]:
    """The feeder's own node numbers: configured, last reported, and the request header (new number after 2.8)."""
    nums: set[Optional[int]] = {
        getattr(observer, "meshtastic_node_id", None),
        getattr(observer, "reported_meshtastic_node_id", None),
    }
    if request is not None:
        nums.add(parse_reported_node_num(request.META.get(REPORTED_NODE_NUM_HEADER)))
    return {n for n in nums if n is not None}


def shape_detection_enabled() -> bool:
    return bool(getattr(settings, "MESHTASTIC_REPLAY_SHAPE_DETECTION", True))
