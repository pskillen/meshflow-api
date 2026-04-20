"""Integration tests for the Celery render task, running eagerly."""

from __future__ import annotations

import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from common.mesh_node_helpers import meshtastic_id_to_hex
from nodes.models import AntennaPattern, NodeRfProfile, NodeRfPropagationRender
from rf_propagation.client import EngineFatalError, EngineTransientError


def _tiff_bytes(size: tuple[int, int] = (8, 8)) -> bytes:
    img = Image.new("RGBA", size, color=(255, 128, 64, 200))
    buf = BytesIO()
    img.save(buf, format="TIFF")
    return buf.getvalue()


def _make_profile(node):
    return NodeRfProfile.objects.create(
        observed_node=node,
        rf_latitude=55.861,
        rf_longitude=-4.251,
        rf_altitude_m=80.0,
        antenna_height_m=6.0,
        antenna_gain_dbi=3.0,
        tx_power_dbm=27.0,
        rf_frequency_mhz=869.525,
        antenna_pattern=AntennaPattern.OMNI,
    )


class _FakeSubmit:
    def __init__(self, task_id: str) -> None:
        self.task_id = task_id


class _FakeClient:
    """Stand-in for ``SitePlannerClient`` used as a context manager."""

    def __init__(
        self,
        *,
        task_id: str = "engine-task-1",
        status: str = "done",
        result: bytes | None = None,
        submit_error: Exception | None = None,
        result_error: Exception | None = None,
    ) -> None:
        self._task_id = task_id
        self._status = status
        self._result = result if result is not None else _tiff_bytes()
        self._submit_error = submit_error
        self._result_error = result_error
        self.submit_calls = 0
        self.status_calls = 0
        self.result_calls = 0

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def submit(self, _payload):
        self.submit_calls += 1
        if self._submit_error is not None:
            raise self._submit_error
        return _FakeSubmit(self._task_id)

    def status(self, _task_id: str) -> str:
        self.status_calls += 1
        return self._status

    def result(self, _task_id: str) -> bytes:
        self.result_calls += 1
        if self._result_error is not None:
            raise self._result_error
        return self._result


@pytest.fixture
def asset_dir(settings):
    with tempfile.TemporaryDirectory() as tmp:
        settings.RF_PROPAGATION_ASSET_DIR = Path(tmp)
        settings.RF_PROPAGATION_ENGINE_URL = "http://engine.test:8080"
        settings.RF_PROPAGATION_POLL_MAX_SECONDS = 5
        yield Path(tmp)


@pytest.mark.django_db
def test_task_happy_path_writes_png_and_marks_ready(asset_dir, create_observed_node):
    from rf_propagation import tasks as task_mod

    node = create_observed_node(
        node_id=820_820_820,
        node_id_str=meshtastic_id_to_hex(820_820_820),
    )
    _make_profile(node)
    render = NodeRfPropagationRender.objects.create(observed_node=node)

    fake = _FakeClient()
    with patch.object(task_mod, "SitePlannerClient", return_value=fake):
        task_mod.render_rf_propagation.apply(args=[render.pk]).get()

    render.refresh_from_db()
    assert render.status == NodeRfPropagationRender.Status.READY
    assert render.asset_filename
    assert (asset_dir / render.asset_filename).is_file()
    assert render.bounds_west is not None and render.bounds_east > render.bounds_west
    assert render.bounds_north > render.bounds_south
    assert fake.submit_calls == 1
    assert fake.result_calls == 1


@pytest.mark.django_db
def test_task_engine_fatal_marks_failed(asset_dir, create_observed_node):
    from rf_propagation import tasks as task_mod

    node = create_observed_node(
        node_id=820_820_821,
        node_id_str=meshtastic_id_to_hex(820_820_821),
    )
    _make_profile(node)
    render = NodeRfPropagationRender.objects.create(observed_node=node)

    fake = _FakeClient(submit_error=EngineFatalError("bad payload"))
    with patch.object(task_mod, "SitePlannerClient", return_value=fake):
        task_mod.render_rf_propagation.apply(args=[render.pk]).get()

    render.refresh_from_db()
    assert render.status == NodeRfPropagationRender.Status.FAILED
    assert "bad payload" in render.error_message


@pytest.mark.django_db
def test_task_transient_error_retries(asset_dir, create_observed_node, settings):
    from rf_propagation import tasks as task_mod

    node = create_observed_node(
        node_id=820_820_822,
        node_id_str=meshtastic_id_to_hex(820_820_822),
    )
    _make_profile(node)
    render = NodeRfPropagationRender.objects.create(observed_node=node)

    fake = _FakeClient(submit_error=EngineTransientError("engine 503"))
    # Run the task eagerly — Celery's eager mode raises on retry.
    with patch.object(task_mod, "SitePlannerClient", return_value=fake):
        with pytest.raises((EngineTransientError, Exception)):
            task_mod.render_rf_propagation.apply(args=[render.pk], throw=True).get()


@pytest.mark.django_db
def test_task_cache_hit_reuses_existing_asset(asset_dir, create_observed_node):
    from rf_propagation import tasks as task_mod
    from rf_propagation.hashing import compute_input_hash
    from rf_propagation.payload import build_request

    node = create_observed_node(
        node_id=820_820_823,
        node_id_str=meshtastic_id_to_hex(820_820_823),
    )
    profile = _make_profile(node)

    payload = build_request(profile)
    input_hash = compute_input_hash(profile, extras={"radius_m": int(payload["radius"])})
    asset_filename = f"{input_hash}.png"
    (asset_dir / asset_filename).write_bytes(b"\x89PNG\r\n\x1a\n")

    NodeRfPropagationRender.objects.create(
        observed_node=node,
        status=NodeRfPropagationRender.Status.READY,
        input_hash=input_hash,
        asset_filename=asset_filename,
        bounds_west=-5.0,
        bounds_south=55.0,
        bounds_east=-3.5,
        bounds_north=56.5,
    )
    render = NodeRfPropagationRender.objects.create(observed_node=node)

    fake = _FakeClient()
    with patch.object(task_mod, "SitePlannerClient", return_value=fake):
        task_mod.render_rf_propagation.apply(args=[render.pk]).get()

    render.refresh_from_db()
    assert render.status == NodeRfPropagationRender.Status.READY
    assert render.asset_filename == asset_filename
    assert fake.submit_calls == 0, "cache hit must not call the engine"


@pytest.mark.django_db
def test_task_retention_keeps_only_n_ready_per_node(asset_dir, create_observed_node, settings):
    from rf_propagation import tasks as task_mod

    settings.RF_PROPAGATION_READY_RETENTION = 2

    node = create_observed_node(
        node_id=820_820_824,
        node_id_str=meshtastic_id_to_hex(820_820_824),
    )
    _make_profile(node)

    for idx in range(3):
        filename = f"cached-{idx}.png"
        (asset_dir / filename).write_bytes(b"stub")
        NodeRfPropagationRender.objects.create(
            observed_node=node,
            status=NodeRfPropagationRender.Status.READY,
            input_hash=f"stub-{idx}",
            asset_filename=filename,
            bounds_west=-5.0,
            bounds_south=55.0,
            bounds_east=-3.5,
            bounds_north=56.5,
        )

    new_render = NodeRfPropagationRender.objects.create(observed_node=node)

    fake = _FakeClient()
    with patch.object(task_mod, "SitePlannerClient", return_value=fake):
        task_mod.render_rf_propagation.apply(args=[new_render.pk]).get()

    ready_count = NodeRfPropagationRender.objects.filter(
        observed_node=node,
        status=NodeRfPropagationRender.Status.READY,
    ).count()
    assert ready_count == settings.RF_PROPAGATION_READY_RETENTION


@pytest.mark.django_db
def test_task_missing_profile_fails_gracefully(asset_dir, create_observed_node):
    from rf_propagation import tasks as task_mod

    node = create_observed_node(
        node_id=820_820_825,
        node_id_str=meshtastic_id_to_hex(820_820_825),
    )
    render = NodeRfPropagationRender.objects.create(observed_node=node)

    task_mod.render_rf_propagation.apply(args=[render.pk]).get()

    render.refresh_from_db()
    assert render.status == NodeRfPropagationRender.Status.FAILED
    assert "RF profile" in render.error_message


@pytest.mark.django_db
def test_task_missing_engine_url_fails(asset_dir, create_observed_node, settings):
    from rf_propagation import tasks as task_mod

    settings.RF_PROPAGATION_ENGINE_URL = ""

    node = create_observed_node(
        node_id=820_820_826,
        node_id_str=meshtastic_id_to_hex(820_820_826),
    )
    _make_profile(node)
    render = NodeRfPropagationRender.objects.create(observed_node=node)

    task_mod.render_rf_propagation.apply(args=[render.pk]).get()

    render.refresh_from_db()
    assert render.status == NodeRfPropagationRender.Status.FAILED
    assert "RF_PROPAGATION_ENGINE_URL" in render.error_message
