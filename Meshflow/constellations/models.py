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
    mc_channel_type = models.PositiveSmallIntegerField(
        choices=MeshCoreChannelType.choices,
        null=True,
        blank=True,
        help_text=_("MeshCore channel type when protocol is MeshCore."),
    )
    region_scope = models.CharField(
        max_length=29,
        null=True,
        blank=True,
        help_text=_(
            "MeshCore region scope when protocol is MeshCore (lowercase alphanumeric + hyphen; "
            "null = legacy / no scope)."
        ),
    )

    class Meta:
        verbose_name = _("Message channel")
        verbose_name_plural = _("Message channels")
        constraints = [
            models.UniqueConstraint(
                fields=["constellation", "protocol", "name", "mc_channel_type"],
                condition=models.Q(
                    protocol=Protocol.MESHCORE,
                    region_scope__isnull=True,
                ),
                name="messagechannel_mc_null_scope_unique",
            ),
            models.UniqueConstraint(
                fields=["constellation", "protocol", "name", "mc_channel_type", "region_scope"],
                condition=models.Q(
                    protocol=Protocol.MESHCORE,
                    region_scope__isnull=False,
                ),
                name="messagechannel_mc_region_scope_unique",
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
