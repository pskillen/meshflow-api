from django.contrib.auth import get_user_model
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils import timezone

from m2m_api.models import M2MApiKey

User = get_user_model()


@receiver(pre_save, sender=User)
def revoke_m2m_keys_when_user_disabled(sender, instance, **kwargs):
    if not instance.pk:
        return
    previous = User.objects.filter(pk=instance.pk).values_list("is_active", flat=True).first()
    if previous is True and instance.is_active is False:
        M2MApiKey.objects.filter(owner_id=instance.pk, revoked_at__isnull=True).update(
            revoked_at=timezone.now(),
            revoked_reason="owner_disabled",
        )
