from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    display_name = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.username


class Constellation(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="created_constellations")

    def __str__(self):
        return self.name


class ConstellationMembership(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    constellation = models.ForeignKey(Constellation, on_delete=models.CASCADE)
    role = models.CharField(max_length=32, choices=[
        ("admin", "Admin"),
        ("editor", "Editor"),
        ("viewer", "Viewer"),
    ])

    class Meta:
        unique_together = ("user", "constellation")
