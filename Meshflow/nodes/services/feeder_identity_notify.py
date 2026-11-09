"""Tell a feeder's owner by Discord DM that its node number changed, or needs review (ID-4).

Copies the pattern in ``mesh_monitoring.services.notify_watchers_node_offline``: skip with an audit row when the
owner has no verified Discord target, and never raise, so a failed DM can't affect the re-key.
``manual`` and ``key_changed`` events are never sent: the owner did the first, the second is audit only.

The DM goes through Celery after commit (``queue_owner_notification``), never on the feeder's request. Flagged DMs are
limited per feeder by ``FLAGGED_DM_COOLDOWN``; the events themselves are always written.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.core.cache import cache
from django.db import transaction

from common.mesh_node_helpers import meshtastic_id_to_hex
from nodes.models import ManagedNodeIdentityEvent
from push_notifications.constants import DiscordNotificationFeature, DiscordNotificationKind
from push_notifications.discord import DiscordSendError
from push_notifications.discord_audit import record_discord_notification_skip, send_discord_dm_with_audit
from users.discord_sync import user_has_verified_discord_dm_target

logger = logging.getLogger(__name__)

Outcome = ManagedNodeIdentityEvent.Outcome
Reason = ManagedNodeIdentityEvent.Reason

# At most one flagged DM per feeder in this window, so a feeder flapping between numbers can't DM on every report.
FLAGGED_DM_COOLDOWN = timedelta(hours=24)

_REASON_TEXT = {
    Reason.KEY_NOT_REPORTED: "it did not report a public key",
    Reason.CRC_MISMATCH: "the reported public key does not match the new number",
    Reason.KEY_MISMATCH: "the reported public key differs from the stored one",
    Reason.SHARED_KEY: "another node uses the same public key",
    Reason.NUMBER_COLLISION: "another feeder already has that number",
    Reason.AUTO_REKEY_DISABLED: "automatic updates are off on this server",
}


def _kind_for(event):
    if event.outcome == Outcome.AUTO_UPDATED:
        return DiscordNotificationKind.FEEDER_IDENTITY_CHANGED
    if event.outcome == Outcome.FLAGGED:
        return DiscordNotificationKind.FEEDER_IDENTITY_FLAGGED
    return None


def build_message(event) -> str:
    name = event.managed_node.name
    old = meshtastic_id_to_hex(event.old_meshtastic_node_id)
    new = meshtastic_id_to_hex(event.new_meshtastic_node_id)
    if event.outcome == Outcome.AUTO_UPDATED:
        return (
            f"Your feeder {name} changed node number: {old} is now {new}. "
            "It keeps its history and API key. Nothing to do."
        )
    reason = _REASON_TEXT.get(event.reason, "the change could not be verified")
    return (
        f"Your feeder {name} reported node number {new} but is stored as {old}, and it could not be updated "
        f"automatically ({reason}). Ingest continues. Open My Nodes to review it."
    )


def _flagged_dm_cooldown_key(event) -> str:
    return f"feeder-identity-flagged-dm:{event.managed_node.internal_id}"


def _in_flagged_dm_cooldown(event) -> bool:
    """True when this feeder had a flagged DM in the window; otherwise starts the window (``add`` is atomic)."""
    return not cache.add(_flagged_dm_cooldown_key(event), 1, timeout=int(FLAGGED_DM_COOLDOWN.total_seconds()))


def queue_owner_notification(event) -> None:
    """Queue the DM for ``event`` once the current transaction commits. Never raises."""
    from nodes.tasks import notify_feeder_identity_event

    event_id = event.pk

    def enqueue():
        try:
            notify_feeder_identity_event.delay(event_id)
        except Exception:
            logger.exception("feeder identity: could not queue notification for event=%s", event_id)

    transaction.on_commit(enqueue)


def notify_owner(event) -> bool:
    """DM the owner about ``event``; return True when a DM was sent. Never raises."""
    try:
        kind = _kind_for(event)
        if kind is None:
            return False
        if event.outcome == Outcome.FLAGGED and _in_flagged_dm_cooldown(event):
            logger.info("feeder identity: flagged DM in cooldown, skipped event=%s", event.pk)
            return False
        user = event.managed_node.owner
        text = build_message(event)
        related = {
            "related_app_label": "nodes",
            "related_model_name": "ManagedNodeIdentityEvent",
            "related_object_id": str(event.pk),
            "related_context": {
                "managed_node_id": str(event.managed_node.internal_id),
                "event_id": event.pk,
                "outcome": event.outcome,
            },
        }
        if not user_has_verified_discord_dm_target(user):
            record_discord_notification_skip(
                feature=DiscordNotificationFeature.FEEDER_IDENTITY,
                kind=kind,
                user=user,
                reason="Discord DM target not verified (missing or stale notification settings).",
                message_preview_text=text,
                discord_recipient_id=getattr(user, "discord_notify_user_id", "") or "",
                **related,
            )
            return False
        send_discord_dm_with_audit(
            feature=DiscordNotificationFeature.FEEDER_IDENTITY,
            kind=kind,
            user=user,
            discord_user_id=user.discord_notify_user_id,
            content=text,
            **related,
        )
        return True
    except DiscordSendError as e:
        logger.warning("feeder identity: Discord notify failed event=%s: %s", getattr(event, "pk", None), e)
    except Exception:
        logger.exception("feeder identity: notify_owner failed event=%s", getattr(event, "pk", None))
    return False
