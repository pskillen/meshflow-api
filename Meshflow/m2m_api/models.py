"""Hashed machine-to-machine API keys."""

import hashlib
import hmac
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class M2MApiKey(models.Model):
    class RateTier(models.TextChoices):
        STANDARD = "standard", "Standard"
        ELEVATED = "elevated", "Elevated"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="m2m_api_keys")
    name = models.CharField(max_length=100)
    prefix = models.CharField(max_length=8, unique=True, db_index=True)
    hashed_key = models.CharField(max_length=64)
    intended_use = models.TextField()
    terms_version = models.CharField(max_length=32)
    terms_accepted_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(max_length=64, blank=True, default="")
    rate_tier = models.CharField(max_length=16, choices=RateTier.choices, default=RateTier.STANDARD)

    class Meta:
        verbose_name = _("M2M API key")
        verbose_name_plural = _("M2M API keys")

    def __str__(self):
        return f"{self.name} ({self.prefix})"

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def matches(self, raw_key: str) -> bool:
        digest = hashlib.sha256(raw_key.encode()).hexdigest()
        return hmac.compare_digest(self.hashed_key, digest)

    @classmethod
    def mint(cls, *, owner, name, intended_use):
        prefix = secrets.token_hex(4)
        secret = secrets.token_urlsafe(24)
        raw = f"mfk_{prefix}_{secret}"
        now = timezone.now()
        key = cls.objects.create(
            owner=owner,
            name=name,
            prefix=prefix,
            hashed_key=hashlib.sha256(raw.encode()).hexdigest(),
            intended_use=intended_use,
            terms_version=settings.M2M_TERMS_VERSION,
            terms_accepted_at=now,
        )
        return key, raw

    def terms_action_required(self) -> bool:
        return self.terms_version != settings.M2M_TERMS_VERSION

    def terms_expired(self) -> bool:
        if not self.terms_action_required():
            return False
        grace = timedelta(days=settings.M2M_TERMS_GRACE_DAYS)
        return timezone.now() > self.terms_accepted_at + grace


class M2MApiKeyUsageDaily(models.Model):
    key = models.ForeignKey(M2MApiKey, on_delete=models.CASCADE, related_name="usage_days")
    date = models.DateField()
    request_count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["key", "date"], name="m2m_usage_key_date_unique"),
        ]
