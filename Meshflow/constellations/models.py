from django.db import models
from django.utils.translation import gettext_lazy as _

from users.models import User


class Constellation(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="created_constellations")

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


class MessageChannel(models.Model):
    name = models.CharField(max_length=100)
    constellation = models.ForeignKey(Constellation, on_delete=models.CASCADE)

    class Meta:
        verbose_name = _("Message channel")
        verbose_name_plural = _("Message channels")

    def __str__(self):
        return self.name
