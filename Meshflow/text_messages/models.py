import uuid

from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from common.protocol import Protocol
from nodes.models import ObservedNode
from packets.models import MessagePacket


class TextMessage(models.Model):
    """Text message on the mesh (Meshtastic or MeshCore provenance)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    protocol = models.PositiveSmallIntegerField(
        choices=Protocol.choices,
        default=Protocol.MESHTASTIC,
        db_index=True,
        help_text=_("Mesh protocol for this message row."),
    )
    original_packet = models.ForeignKey(
        MessagePacket,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="text_messages",
        help_text=_("Provenance: Meshtastic MessagePacket."),
    )
    original_mc_packet = models.ForeignKey(
        "meshcore_packets.MeshCoreTextPacket",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="text_messages",
        help_text=_("Provenance: MeshCore text packet."),
    )

    sender = models.ForeignKey(ObservedNode, on_delete=models.CASCADE, null=True, blank=True)
    recipient_meshtastic_node_id = models.BigIntegerField(null=True, blank=True)
    channel = models.ForeignKey("constellations.MessageChannel", on_delete=models.CASCADE, null=True, blank=True)

    sent_at = models.DateTimeField()

    message_text = models.TextField(null=False, blank=False)
    is_emoji = models.BooleanField(null=False, default=False)
    reply_to_meshtastic_packet_id = models.BigIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = _("Text message")
        verbose_name_plural = _("Text messages")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(original_packet__isnull=False, original_mc_packet__isnull=True)
                    | Q(original_packet__isnull=True, original_mc_packet__isnull=False)
                    | Q(original_packet__isnull=True, original_mc_packet__isnull=True)
                ),
                name="textmessage_single_provenance",
            ),
        ]

    def __str__(self):
        sender_label = self.sender.node_id_str if self.sender_id else "?"
        recipient = self.recipient_meshtastic_node_id or "^all"
        return f"{sender_label} -> {recipient}: {self.message_text[:10]}..."
