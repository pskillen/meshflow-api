"""Radio protocol discriminator shared across nodes and constellations."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class Protocol(models.IntegerChoices):
    """Which mesh protocol a row belongs to (one constellation / node row per protocol)."""

    MESHTASTIC = 1, _("Meshtastic")
    MESHCORE = 2, _("MeshCore")


_PROTOCOL_QUERY_ALIASES = {
    "meshtastic": Protocol.MESHTASTIC,
    "meshcore": Protocol.MESHCORE,
    "mt": Protocol.MESHTASTIC,
    "mc": Protocol.MESHCORE,
    "1": Protocol.MESHTASTIC,
    "2": Protocol.MESHCORE,
}


def protocol_from_query_param(value):
    """
    Parse ?protocol= from list endpoints (meshtastic, meshcore, mt, mc, 1, 2).
    Returns None when absent or unrecognized (no filter).
    """
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    return _PROTOCOL_QUERY_ALIASES.get(text)
