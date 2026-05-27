"""MeshCore wire packet storage (separate from Meshtastic ``packets`` app)."""

import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from constellations.models import MessageChannel
from nodes.models import ManagedNode


class MeshCorePayloadType(models.IntegerChoices):
    """Payload classification for ingested MeshCore frames."""

    ADVERT = 1, "advert"
    CHANNEL_TEXT = 2, "channel_text"
    CONTACT_TEXT = 3, "contact_text"
    RAW = 99, "raw"


class MeshCoreRawPacket(models.Model):
    """MeshCore raw packet row (common metadata; MTI parent for text subclass)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    observer = models.ForeignKey(
        ManagedNode,
        on_delete=models.CASCADE,
        related_name="meshcore_packets_observed",
    )
    payload_type = models.PositiveSmallIntegerField(choices=MeshCorePayloadType.choices, db_index=True)
    event_type = models.CharField(max_length=64, db_index=True)
    from_pubkey = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    from_pubkey_prefix = models.CharField(max_length=12, null=True, blank=True, db_index=True)
    pkt_hash = models.BigIntegerField(null=True, blank=True, db_index=True)
    rx_time = models.DateTimeField(db_index=True)
    rx_rssi = models.FloatField(null=True, blank=True)
    rx_snr = models.FloatField(null=True, blank=True)
    route_typename = models.CharField(max_length=32, null=True, blank=True)
    raw_json = models.JSONField()
    first_reported_time = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "meshcore_packets_raw"
        indexes = [
            models.Index(fields=["from_pubkey_prefix", "pkt_hash"]),
            models.Index(fields=["-rx_time"]),
        ]
        verbose_name = _("MeshCore raw packet")
        verbose_name_plural = _("MeshCore raw packets")


class MeshCoreTextPacket(MeshCoreRawPacket):
    """MeshCore text payload (channel or contact/DM)."""

    to_pubkey_prefix = models.CharField(max_length=12, null=True, blank=True)
    channel = models.ForeignKey(
        MessageChannel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meshcore_text_packets",
    )
    text = models.TextField()

    class Meta:
        verbose_name = _("MeshCore text packet")
        verbose_name_plural = _("MeshCore text packets")


class MeshCorePacketObservation(models.Model):
    """One observer (feeder) reporting a MeshCore packet."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    packet = models.ForeignKey(
        MeshCoreRawPacket,
        on_delete=models.CASCADE,
        related_name="observations",
    )
    observer = models.ForeignKey(
        ManagedNode,
        on_delete=models.CASCADE,
        related_name="meshcore_packet_observations",
    )
    channel = models.ForeignKey(
        MessageChannel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meshcore_observations",
    )
    rx_time = models.DateTimeField()
    rx_rssi = models.FloatField(null=True, blank=True)
    rx_snr = models.FloatField(null=True, blank=True)
    path_hashes = models.JSONField(null=True, blank=True)
    upload_time = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["packet", "observer"], name="meshcore_obs_packet_observer_unique"),
        ]
        verbose_name = _("MeshCore packet observation")
        verbose_name_plural = _("MeshCore packet observations")
