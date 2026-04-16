"""Mesh monitoring runtime constants (env-overridable where noted)."""

import os

# Align with STALE_TR_TIMEOUT_SECONDS / verification window in epic (~3 minutes).
DEFAULT_VERIFICATION_WINDOW_SECONDS = 180


def verification_window_seconds() -> int:
    raw = os.environ.get(
        "MESH_MONITORING_VERIFICATION_SECONDS",
        str(DEFAULT_VERIFICATION_WINDOW_SECONDS),
    )
    return int(raw)


_NOTIFY_VERIFICATION_START_KEY = "MESH_MONITORING_NOTIFY_VERIFICATION_START"


def notify_verification_start_enabled() -> bool:
    """
    Whether to DM watchers when a new monitoring verification episode starts.

    Default **on** when the env var is unset. Set to ``0``, ``false``, ``no``, ``off``, or empty to disable.
    """
    if _NOTIFY_VERIFICATION_START_KEY not in os.environ:
        return True
    raw = os.environ.get(_NOTIFY_VERIFICATION_START_KEY, "").strip().lower()
    if raw in ("0", "false", "no", "off", ""):
        return False
    return raw in ("1", "true", "yes", "on")


def verification_notify_cooldown_seconds() -> int:
    """Cooldown between verification-start Discord DMs for the same node (default 1 hour)."""
    raw = os.environ.get("MESH_MONITORING_VERIFICATION_NOTIFY_COOLDOWN_SECONDS", "3600")
    return int(raw)
