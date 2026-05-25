"""Shared logic for accepting node ownership claims from mesh text/DM proof."""

import logging
import re

from django.utils import timezone

from nodes.models import NodeOwnerClaim, ObservedNode
from packets.signals import node_claim_authorized

logger = logging.getLogger(__name__)

# Claim key: 2–3 words and 2–3 digits (same as legacy TextMessagePacketService).
CLAIM_KEY_REGEX = r"^\s*(\w+\s+){2,3}\d{2,3}\s*$"


def normalize_claim_key(message_text: str) -> str:
    return " ".join(message_text.strip().split()).lower()


def try_accept_node_claim(*, sender: ObservedNode, message_text: str, observer, sender_service) -> bool:
    """
    If message_text matches a pending NodeOwnerClaim for sender, accept ownership.

    Emits node_claim_authorized on success. Returns True when a claim was accepted.
    """
    if not re.match(CLAIM_KEY_REGEX, message_text):
        return False

    claim_key = normalize_claim_key(message_text)
    logger.info("Checking node claim for %s: %s", sender.node_id_str, claim_key)

    claim = NodeOwnerClaim.objects.filter(
        node=sender,
        claim_key=claim_key,
        accepted_at__isnull=True,
    ).first()
    if claim is None:
        return False

    logger.info(
        "Authorizing node claim for %s by %s",
        sender.node_id_str,
        claim.user.username,
    )

    sender.claimed_by = claim.user
    sender.save(update_fields=["claimed_by"])

    claim.accepted_at = timezone.now()
    claim.save(update_fields=["accepted_at"])

    node_claim_authorized.send(
        sender=sender_service,
        node=sender,
        claim=claim,
        observer=observer,
    )
    return True
