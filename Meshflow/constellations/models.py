import binascii
import os
import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from users.models import User


class Constellation(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="created_constellations"
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


class NodeAPIKey(models.Model):
    """Model for API keys that authenticate nodes to the API."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=100)
    constellation = models.ForeignKey(
        Constellation, on_delete=models.CASCADE, related_name="api_keys"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="created_api_keys"
    )
    last_used = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Node API Key"
        verbose_name_plural = "Node API Keys"

    def __str__(self):
        return f"{self.name} ({self.constellation.name})"

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self.generate_key()
        return super().save(*args, **kwargs)

    @classmethod
    def generate_key(cls):
        return binascii.hexlify(os.urandom(20)).decode()


class NodeAuth(models.Model):
    """Model linking API keys to specific nodes they can authenticate."""

    api_key = models.ForeignKey(
        NodeAPIKey, on_delete=models.CASCADE, related_name="node_links"
    )
    node = models.ForeignKey(
        "nodes.MeshtasticNode", on_delete=models.CASCADE, related_name="api_key_links"
    )

    class Meta:
        unique_together = ("api_key", "node")
        verbose_name = _("Node authentication")
        verbose_name_plural = _("Node authentications")

    def __str__(self):
        return f"{self.api_key.name} - {self.node}"
