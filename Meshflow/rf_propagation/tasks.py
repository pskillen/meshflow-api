"""Celery task that drives a single RF propagation render.

Flow (see plan 2 ``docs/features/rf_propagation/README.md``):

1. Load the render row + RF profile.
2. Build the payload + compute the input hash.
3. Cache hit: if a sibling render with the same hash is ``ready`` and its
   PNG still exists on disk, mirror its fields onto this row and return.
4. Engine roundtrip: ``submit`` → poll ``status`` with backoff → ``result``.
5. GeoTIFF → PNG → atomic write to ``RF_PROPAGATION_ASSET_DIR``.
6. Bounds from ``(lat, lng, radius_m)``.
7. Mark the row ``ready``; run light retention GC.

Transient HTTP / engine errors bubble up as :class:`EngineTransientError`
so Celery's ``autoretry_for`` can retry with jitter. Fatal errors and a
final retry-exhaust both land the row in ``failed`` with a useful message.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

import httpx
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError, SoftTimeLimitExceeded

from .bounds import bbox_from_center
from .client import EngineFatalError, EngineTransientError, SitePlannerClient
from .hashing import compute_input_hash
from .image import TiffDecodeError, geotiff_to_render_image
from .payload import InvalidProfileError, build_request, hash_extras_from_payload

logger = logging.getLogger(__name__)

# Exponential-ish backoff; capped cumulatively by RF_PROPAGATION_POLL_MAX_SECONDS.
_POLL_SCHEDULE_SECONDS: tuple[float, ...] = (1.0, 2.0, 5.0, 10.0, 10.0, 15.0, 15.0, 20.0, 30.0)


def _poll_until_done(client: SitePlannerClient, task_id: str, max_seconds: int) -> None:
    """Block until the engine reports ``done``/``ready`` or raise.

    Raises :class:`EngineFatalError` if the engine reports ``failed`` or if
    the cumulative wait exceeds ``max_seconds``.
    """

    elapsed = 0.0
    step = 0
    while True:
        state = client.status(task_id).lower()
        if state in {"done", "ready", "complete", "completed", "success"}:
            return
        if state in {"failed", "error"}:
            raise EngineFatalError(f"engine task {task_id} reported status={state}")
        if elapsed >= max_seconds:
            raise EngineFatalError(
                f"engine task {task_id} did not complete within {max_seconds}s (last status={state})"
            )
        delay = _POLL_SCHEDULE_SECONDS[min(step, len(_POLL_SCHEDULE_SECONDS) - 1)]
        time.sleep(delay)
        elapsed += delay
        step += 1


def _asset_dir() -> Path:
    path = Path(settings.RF_PROPAGATION_ASSET_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _find_cache_hit(model_cls, render_id: int, input_hash: str) -> object | None:
    """Return a sibling ``ready`` render with the same hash whose PNG still exists."""

    base_dir = _asset_dir()
    candidate = (
        model_cls.objects.filter(status=model_cls.Status.READY, input_hash=input_hash)
        .exclude(pk=render_id)
        .order_by("-created_at")
        .first()
    )
    if candidate is None:
        return None
    if not candidate.asset_filename:
        return None
    if not (base_dir / candidate.asset_filename).is_file():
        return None
    return candidate


def _run_retention(model_cls, observed_node, *, keep: int) -> None:
    """Keep at most ``keep`` ready renders per node; delete orphan PNGs."""

    base_dir = _asset_dir()
    ready_renders = list(
        model_cls.objects.filter(observed_node=observed_node, status=model_cls.Status.READY).order_by("-created_at")
    )
    victims = ready_renders[keep:]
    surviving = ready_renders[:keep]
    surviving_filenames = {r.asset_filename for r in surviving if r.asset_filename}

    for victim in victims:
        filename = victim.asset_filename
        victim.delete()
        if filename and filename not in surviving_filenames:
            _safe_unlink(base_dir / filename)

    cutoff = timezone.now() - timedelta(days=7)
    model_cls.objects.filter(
        observed_node=observed_node,
        status=model_cls.Status.FAILED,
        created_at__lt=cutoff,
    ).delete()


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:  # pragma: no cover — best-effort GC
        logger.warning("rf_propagation.tasks: could not remove %s: %s", path, exc)


@shared_task(
    bind=True,
    name="nodes.tasks.render_rf_propagation",
    autoretry_for=(httpx.TransportError, EngineTransientError),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
    max_retries=3,
    soft_time_limit=600,
    time_limit=660,
)
def render_rf_propagation(self, render_id: int) -> dict:
    """Generate the PNG overlay for a single :class:`NodeRfPropagationRender` row."""

    # Local import avoids the Celery autodiscover import-time circular.
    from nodes.models import NodeRfProfile, NodeRfPropagationRender

    try:
        render = NodeRfPropagationRender.objects.select_related("observed_node").get(pk=render_id)
    except NodeRfPropagationRender.DoesNotExist:
        logger.warning("render_rf_propagation: render_id=%s vanished", render_id)
        return {"status": "missing"}

    # If the row was already cancelled / completed (e.g. user hit cancel before
    # the worker picked it up, or the task was re-dispatched after completion),
    # don't do any of the expensive engine work.
    terminal_statuses = {
        NodeRfPropagationRender.Status.READY,
        NodeRfPropagationRender.Status.FAILED,
    }
    if render.status in terminal_statuses:
        logger.info(
            "render_rf_propagation.skip_terminal render_id=%s status=%s",
            render_id,
            render.status,
        )
        return {"status": str(render.status), "render_id": render_id, "skipped": True}

    observed_node = render.observed_node
    logger.info("render_rf_propagation.render_start render_id=%s node_id=%s", render_id, observed_node.node_id)

    try:
        profile = observed_node.rf_profile
    except NodeRfProfile.DoesNotExist:
        return _mark_failed(render, "observed node has no RF profile")

    try:
        payload = build_request(profile)
    except InvalidProfileError as exc:
        return _mark_failed(render, str(exc))

    input_hash = compute_input_hash(profile, extras=hash_extras_from_payload(payload))

    cache_hit = _find_cache_hit(NodeRfPropagationRender, render_id, input_hash)
    if cache_hit is not None:
        logger.info(
            "render_rf_propagation.cache_hit render_id=%s source_id=%s hash=%s",
            render_id,
            cache_hit.pk,
            input_hash,
        )
        return _mirror_ready(render, cache_hit, input_hash)

    # One final cancellation check before committing to the engine roundtrip.
    # The row may have been cancelled (status flipped) or dismissed (deleted)
    # by the operator; both mean "don't do the work".
    try:
        render.refresh_from_db(fields=["status"])
    except NodeRfPropagationRender.DoesNotExist:
        logger.info("render_rf_propagation.dismissed_before_engine render_id=%s", render_id)
        return {"status": "missing", "render_id": render_id, "skipped": True}
    if render.status in terminal_statuses:
        logger.info(
            "render_rf_propagation.cancelled_before_engine render_id=%s status=%s",
            render_id,
            render.status,
        )
        return {"status": str(render.status), "render_id": render_id, "skipped": True}

    # Engine roundtrip ----------------------------------------------------
    render.status = NodeRfPropagationRender.Status.RUNNING
    render.save(update_fields=["status"])

    engine_url = settings.RF_PROPAGATION_ENGINE_URL
    if not engine_url:
        return _mark_failed(render, "RF_PROPAGATION_ENGINE_URL is not configured")

    try:
        with SitePlannerClient(engine_url) as client:
            submission = client.submit(payload)
            logger.info(
                "render_rf_propagation.engine_submitted render_id=%s task_id=%s",
                render_id,
                submission.task_id,
            )
            _poll_until_done(client, submission.task_id, settings.RF_PROPAGATION_POLL_MAX_SECONDS)
            logger.info("render_rf_propagation.engine_ready render_id=%s", render_id)
            tiff_bytes = client.result(submission.task_id)
    except EngineTransientError:
        raise
    except EngineFatalError as exc:
        return _mark_failed(render, str(exc))
    except SoftTimeLimitExceeded:
        return _mark_failed(render, "render exceeded soft_time_limit")
    except MaxRetriesExceededError as exc:
        return _mark_failed(render, f"max retries exceeded: {exc}")

    try:
        render_image = geotiff_to_render_image(tiff_bytes)
    except TiffDecodeError as exc:
        return _mark_failed(render, f"could not decode engine GeoTIFF: {exc}")

    png_bytes = render_image.png_bytes
    # Prefer bounds recovered from the GeoTIFF's own georeferencing tags;
    # SPLAT! emits an extent snapped to SRTM tile boundaries so our request
    # ``radius`` is only a hint. Fall back to the request bbox if the engine
    # somehow omits the tags so we still produce *some* overlay.
    if render_image.bounds is not None:
        bbox = render_image.bounds
    else:
        logger.warning(
            "render_rf_propagation.bounds_fallback render_id=%s (GeoTIFF lacked georef tags)",
            render_id,
        )
        bbox = bbox_from_center(
            float(profile.rf_latitude),
            float(profile.rf_longitude),
            float(payload["radius"]),
        )

    asset_filename = f"{input_hash}.png"
    asset_path = _asset_dir() / asset_filename
    _atomic_write(asset_path, png_bytes)
    logger.info(
        "render_rf_propagation.png_written render_id=%s path=%s bytes=%s",
        render_id,
        asset_path,
        len(png_bytes),
    )

    # If the operator cancelled or dismissed while the engine was running, the
    # row is now ``failed`` or gone — don't resurrect it. The PNG is content-
    # addressed by hash, so it's safe to leave on disk; retention on a future
    # render will reap it if it's orphaned.
    try:
        render.refresh_from_db(fields=["status"])
    except NodeRfPropagationRender.DoesNotExist:
        logger.info("render_rf_propagation.dismissed_after_engine render_id=%s", render_id)
        return {"status": "missing", "render_id": render_id, "skipped": True}
    if render.status in terminal_statuses:
        logger.info(
            "render_rf_propagation.cancelled_after_engine render_id=%s status=%s",
            render_id,
            render.status,
        )
        return {"status": str(render.status), "render_id": render_id, "skipped": True}

    render.status = NodeRfPropagationRender.Status.READY
    render.input_hash = input_hash
    render.asset_filename = asset_filename
    render.bounds_west = bbox.west
    render.bounds_south = bbox.south
    render.bounds_east = bbox.east
    render.bounds_north = bbox.north
    render.error_message = ""
    render.completed_at = timezone.now()
    render.save()

    _run_retention(
        NodeRfPropagationRender,
        observed_node,
        keep=settings.RF_PROPAGATION_READY_RETENTION,
    )

    logger.info("render_rf_propagation.render_complete render_id=%s", render_id)
    return {"status": "ready", "render_id": render_id, "asset_filename": asset_filename}


def _mirror_ready(render, cache_hit, input_hash: str) -> dict:
    """Copy a cache-hit's asset metadata onto ``render`` and mark it ready."""

    render.status = render.Status.READY
    render.input_hash = input_hash
    render.asset_filename = cache_hit.asset_filename
    render.bounds_west = cache_hit.bounds_west
    render.bounds_south = cache_hit.bounds_south
    render.bounds_east = cache_hit.bounds_east
    render.bounds_north = cache_hit.bounds_north
    render.error_message = ""
    render.completed_at = timezone.now()
    render.save()
    return {"status": "ready", "render_id": render.pk, "asset_filename": render.asset_filename, "cache": True}


def _mark_failed(render, message: str) -> dict:
    render.status = render.Status.FAILED
    render.error_message = message[:4000]
    render.completed_at = timezone.now()
    render.save(update_fields=["status", "error_message", "completed_at"])
    logger.warning("render_rf_propagation.render_failed render_id=%s reason=%s", render.pk, message)
    return {"status": "failed", "render_id": render.pk, "error": message}
