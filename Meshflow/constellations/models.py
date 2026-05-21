from django.db import models
from django.utils.translation import gettext_lazy as _

from common.protocol import Protocol
from users.models import User


class Constellation(models.Model):
    """Regional grouping; single protocol per constellation (Meshtastic today)."""

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="created_constellations")
    map_color = models.CharField(max_length=7, default="#000000")
    bot_default_ignore_meshtastic_portnums = models.CharField(max_length=255, blank=True)
    bot_default_meshtastic_hop_limit = models.PositiveSmallIntegerField(null=True, blank=True)
    protocol = models.PositiveSmallIntegerField(
        choices=Protocol.choices,
        default=Protocol.MESHTASTIC,
        db_index=True,
        help_text=_("Mesh protocol for this constellation and its channels."),
    )

    class Meta:
        verbose_name = _("Constellation")
        verbose_name_plural = _("Constellations")

    def __str__(self):
        return self.name


class ConstellationUserMembership(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    constellation = models.ForeignKey(Constellation, on_delete=models.CASCADE)
    role = models.CharField(
        max_length=32,
        choices=[
            ("admin", "Admin"),
            ("editor", "Editor"),
            ("viewer", "Viewer"),
        ],
    )

    class Meta:
        unique_together = ("user", "constellation")
        verbose_name = _("Constellation membership")
        verbose_name_plural = _("Constellation memberships")

    def __str__(self):
        return f"{self.user.username} - {self.constellation.name}"


class MeshCoreChannelType(models.IntegerChoices):
    """MeshCore companion channel type (device config; not on wire)."""

    PUBLIC = 1, _("PUBLIC")
    HASHTAG = 2, _("HASHTAG")


class MessageChannel(models.Model):
    """Message channel within a constellation (protocol-specific PSK/name; see ADR-0002)."""

    name = models.CharField(max_length=100)
    constellation = models.ForeignKey(Constellation, on_delete=models.CASCADE)
    protocol = models.PositiveSmallIntegerField(
        choices=Protocol.choices,
        default=Protocol.MESHTASTIC,
        db_index=True,
        help_text=_("Mesh protocol for this channel row."),
    )
    mc_channel_idx = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text=_("MeshCore channel index when protocol is MeshCore; null for Meshtastic."),
    )
    mc_channel_type = models.PositiveSmallIntegerField(
        choices=MeshCoreChannelType.choices,
        null=True,
        blank=True,
        help_text=_("MeshCore channel type when protocol is MeshCore."),
    )
    mc_hashtag = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text=_("Hashtag string when mc_channel_type is HASHTAG (no leading #)."),
    )

    class Meta:
        verbose_name = _("Message channel")
        verbose_name_plural = _("Message channels")
        constraints = [
            models.UniqueConstraint(
                fields=["constellation", "protocol", "mc_channel_idx"],
                condition=models.Q(protocol=Protocol.MESHCORE, mc_channel_idx__isnull=False),
                name="messagechannel_mc_idx_constellation_unique",
            ),
        ]

    def __str__(self):
        return self.name


class MeshCoreMessageChannel(MessageChannel):
    """Proxy for Django admin: MeshCore channel rows only."""

    class Meta:
        proxy = True
        verbose_name = _("MeshCore channel")
        verbose_name_plural = _("MeshCore channels")
