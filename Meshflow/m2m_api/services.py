"""Staff operation that removes M2M mint rights and revokes live keys."""

import logging

from django.contrib.auth.models import Group
from django.db import transaction
from django.utils import timezone

from common.access import M2M_API_GROUP_NAME

from .models import M2MApiKey

logger = logging.getLogger(__name__)


def withdraw_m2m_access(user, *, by) -> dict:
    with transaction.atomic():
        removed = False
        group = Group.objects.filter(name=M2M_API_GROUP_NAME).first()
        if group is not None and user.groups.filter(pk=group.pk).exists():
            user.groups.remove(group)
            removed = True
        now = timezone.now()
        revoked = M2MApiKey.objects.filter(owner=user, revoked_at__isnull=True).update(
            revoked_at=now,
            revoked_reason="access_withdrawn",
        )
    logger.info(
        "withdraw_m2m_access user=%s by=%s removed=%s revoked=%s", user.pk, getattr(by, "pk", None), removed, revoked
    )
    return {"removed_from_group": removed, "keys_revoked": revoked}
