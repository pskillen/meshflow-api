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


def notify_verification_start_enabled() -> bool:
    """True when MESH_MONITORING_NOTIFY_VERIFICATION_START is truthy (1, true, yes, on). Default on."""
    raw = os.environ.get("MESH_MONITORING_NOTIFY_VERIFICATION_START", "true").strip().lower()
    return raw in ("1", "true", "yes", "on")


def verification_notify_cooldown_seconds() -> int:
    """Cooldown between verification-start Discord DMs for the same node (default 1 hour)."""
    raw = os.environ.get("MESH_MONITORING_VERIFICATION_NOTIFY_COOLDOWN_SECONDS", "3600")
    return int(raw)
