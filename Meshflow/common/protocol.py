"""Radio protocol discriminator shared across nodes and constellations."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class Protocol(models.IntegerChoices):
    """Which mesh protocol a row belongs to (one constellation / node row per protocol)."""

    MESHTASTIC = 1, _("Meshtastic")
    MESHCORE = 2, _("MeshCore")
