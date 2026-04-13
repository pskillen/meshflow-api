"""Signed OAuth state + Discord account attachment for linking Discord to an existing Meshflow user."""

from __future__ import annotations

import secrets

from django.core.cache import cache
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

import requests

CONNECT_SALT = "meshflow-discord-connect-v1"
STATE_MAX_AGE = 900  # seconds (15 minutes)


class DiscordConnectError(Exception):
    """Base error for Discord connect flow."""


class DiscordAccountAlreadyLinkedError(DiscordConnectError):
    """This Discord user id is already linked to another Meshflow account."""


def _signer() -> TimestampSigner:
    return TimestampSigner(salt=CONNECT_SALT)


def create_discord_connect_state(user_id: int) -> str:
    """
    Build a signed OAuth state value and register a one-time nonce in cache.
    """
    nonce = secrets.token_hex(16)
    cache_key = _nonce_cache_key(nonce)
    cache.set(cache_key, user_id, timeout=STATE_MAX_AGE)
    payload = f"{user_id}:{nonce}"
    return _signer().sign(payload)


def _nonce_cache_key(nonce: str) -> str:
    return f"discord_connect_oauth:{nonce}"


def consume_discord_connect_state(state: str) -> int:
    """
    Validate signed state and consume the one-time nonce. Returns Meshflow user id.
    Raises ValueError on any validation failure.
    """
    try:
        payload = _signer().unsign(state, max_age=STATE_MAX_AGE)
    except BadSignature:
        raise ValueError("invalid_signature") from None
    except SignatureExpired:
        raise ValueError("state_expired") from None

    parts = payload.split(":", 1)
    if len(parts) != 2:
        raise ValueError("invalid_payload")
    user_id_s, nonce = parts
    user_id = int(user_id_s)
    cache_key = _nonce_cache_key(nonce)
    cached = cache.get(cache_key)
    if cached is None:
        raise ValueError("nonce_missing_or_reused")
    if int(cached) != user_id:
        raise ValueError("nonce_user_mismatch")
    cache.delete(cache_key)
    return user_id


def fetch_discord_me(access_token: str) -> dict:
    """GET /users/@me from Discord API."""
    response = requests.get(
        "https://discord.com/api/v10/users/@me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def attach_discord_to_user(user, discord_user: dict) -> None:
    """
    Create or update django-allauth SocialAccount for Discord on this user.
    Raises DiscordAccountAlreadyLinkedError if the Discord uid belongs to another user.
    """
    from allauth.socialaccount.models import SocialAccount

    uid = str(discord_user["id"])
    extra_data = {k: discord_user.get(k) for k in ("username", "discriminator", "global_name", "avatar", "email")}

    existing = SocialAccount.objects.filter(provider="discord", uid=uid).exclude(user=user).first()
    if existing:
        raise DiscordAccountAlreadyLinkedError()

    SocialAccount.objects.update_or_create(
        user=user,
        provider="discord",
        defaults={
            "uid": uid,
            "extra_data": {k: v for k, v in extra_data.items() if v is not None},
        },
    )
