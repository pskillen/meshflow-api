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
