"""Send Discord DMs using a bot token (separate from OAuth client used for login)."""

from __future__ import annotations

import logging

from django.conf import settings

import requests

logger = logging.getLogger(__name__)

DISCORD_API_BASE = "https://discord.com/api/v10"


class DiscordSendError(Exception):
    """Raised when the Discord API rejects a request or the bot token is missing."""


def _bot_headers() -> dict[str, str]:
    token = getattr(settings, "DISCORD_BOT_TOKEN", "") or ""
    if not token.strip():
        raise DiscordSendError("DISCORD_BOT_TOKEN is not configured")
    return {
        "Authorization": f"Bot {token.strip()}",
        "Content-Type": "application/json",
    }


def send_dm(recipient_discord_user_id: str, content: str) -> None:
    """
    Open (or reuse) a DM channel with the recipient and post a message.

    The recipient must be a verified Discord user id (snowflake string).
    """
    rid = (recipient_discord_user_id or "").strip()
    if not rid:
        raise DiscordSendError("recipient_discord_user_id is empty")
    text = (content or "").strip()
    if not text:
        raise DiscordSendError("message content is empty")
    if len(text) > 2000:
        raise DiscordSendError("message content exceeds Discord 2000 character limit")

    headers = _bot_headers()
    channel_resp = requests.post(
        f"{DISCORD_API_BASE}/users/@me/channels",
        json={"recipient_id": rid},
        headers=headers,
        timeout=30,
    )
    if not channel_resp.ok:
        logger.warning(
            "Discord create DM failed status=%s body=%s",
            channel_resp.status_code,
            channel_resp.text[:500],
        )
        raise DiscordSendError(f"Discord create DM failed (HTTP {channel_resp.status_code})")

    channel_id = channel_resp.json().get("id")
    if not channel_id:
        raise DiscordSendError("Discord create DM response missing channel id")

    msg_resp = requests.post(
        f"{DISCORD_API_BASE}/channels/{channel_id}/messages",
        json={"content": text},
        headers=headers,
        timeout=30,
    )
    if not msg_resp.ok:
        logger.warning(
            "Discord send message failed status=%s body=%s",
            msg_resp.status_code,
            msg_resp.text[:500],
        )
        raise DiscordSendError(f"Discord send message failed (HTTP {msg_resp.status_code})")
