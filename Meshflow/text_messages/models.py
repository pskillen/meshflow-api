from django.db import models
from django.utils.translation import gettext_lazy as _

from nodes.models import ObservedNode


class Message(models.Model):
    """Model representing a text message sent to a node."""

    sender = models.ForeignKey(ObservedNode, on_delete=models.CASCADE)
    recipient_node_id = models.BigIntegerField(null=True, blank=True)

    sent_at = models.DateTimeField(auto_now_add=True)

    message_text = models.TextField(null=False, blank=False)
    is_emoji = models.BooleanField(null=False, default=False)
    reply_to_message_id = models.BigIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = _("Text message")
        verbose_name_plural = _("Text messages")

    def __str__(self):
        return f"{self.sender.node_id_str} -> {self.recipient_node_id or '^all'}: {self.message_text[:10]}..."
