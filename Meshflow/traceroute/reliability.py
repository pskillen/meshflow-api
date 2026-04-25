"""
Per-source target reliability for automatic traceroute selection.

Only ``trigger_type=monitoring`` (integer ``3``) and terminal statuses (completed, failed) are used.
User, node watch, external, and DX watch triggers do not affect exclusion or soft penalties.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from .models import AutoTraceRoute


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return int(str(raw).strip())


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return float(str(raw).strip())


@dataclass(frozen=True)
class ReliabilitySettings:
    """Tunables for automatic target reliability (see docs/ENV_VARS.md)."""

    enabled: bool
    window_days: int
    consecutive_fails_cooldown: int
    soft_max: float
    min_attempts_soft: int


def get_reliability_settings() -> ReliabilitySettings:
    return ReliabilitySettings(
        enabled=_env_bool("TR_RELIABILITY_ENABLED", True),
        window_days=_env_int("TR_RELIABILITY_WINDOW_DAYS", 14),
        consecutive_fails_cooldown=_env_int("TR_RELIABILITY_CONSECUTIVE_FAILS", 4),
        soft_max=_env_float("TR_RELIABILITY_SOFT_MAX", 100.0),
        min_attempts_soft=_env_int("TR_RELIABILITY_MIN_ATTEMPTS_SOFT", 3),
    )


def load_source_target_reliability(
    managed_node,
) -> tuple[set[int], dict[int, float]]:
    """
    Return (hard_cooldown_target_node_ids, soft_penalty_by_target_node_id).

    Hard cooldown: at least ``consecutive_fails_cooldown`` consecutive automatic
    failures for this (source, target) pair, with no more recent success in the
    reliability window (most-recent-first streak).

    Soft penalty: up to ``soft_max`` times (failed / attempts) in the window,
    when ``attempts >= min_attempts_soft``, using the same completed/failed auto
    rows (same order as for consecutive counting).
    """
    s = get_reliability_settings()
    if not s.enabled:
        return set(), {}
    if s.consecutive_fails_cooldown <= 0 and s.soft_max <= 0.0:
        return set(), {}

    cutoff = timezone.now() - timedelta(days=s.window_days)
    rows = list(
        AutoTraceRoute.objects.filter(
            source_node=managed_node,
            trigger_type=AutoTraceRoute.TRIGGER_TYPE_MONITORING,
            triggered_at__gte=cutoff,
            status__in=(AutoTraceRoute.STATUS_COMPLETED, AutoTraceRoute.STATUS_FAILED),
        )
        .order_by("target_node__node_id", "-triggered_at")
        .values("target_node__node_id", "status")
    )

    by_target: dict[int, list[str]] = defaultdict(list)
    for r in rows:
        by_target[r["target_node__node_id"]].append(r["status"])

    hard: set[int] = set()
    soft: dict[int, float] = {}

    for tid, statuses in by_target.items():
        consec = 0
        for st in statuses:
            if st == AutoTraceRoute.STATUS_FAILED:
                consec += 1
            else:
                break
        if s.consecutive_fails_cooldown > 0 and consec >= s.consecutive_fails_cooldown:
            hard.add(tid)
            continue

        n = len(statuses)
        if n < s.min_attempts_soft or s.soft_max <= 0.0:
            continue
        failed = sum(1 for x in statuses if x == AutoTraceRoute.STATUS_FAILED)
        if failed == 0:
            continue
        ratio = failed / float(n)
        soft[tid] = s.soft_max * ratio

    return hard, soft
