"""Shell-level tests of docker-entrypoint.sh with `python` stubbed out."""

import stat
import subprocess
from pathlib import Path

import pytest

ENTRYPOINT = Path(__file__).resolve().parents[3] / "docker-entrypoint.sh"

pytestmark = pytest.mark.skipif(not ENTRYPOINT.exists(), reason="entrypoint not present in this checkout layout")


def _stub_python(tmp_path, body):
    fake = tmp_path / "python"
    fake.write_text(f"#!/bin/sh\n{body}\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def run_entrypoint(tmp_path):
    log = tmp_path / "python.log"
    _stub_python(tmp_path, f'echo "$@" >> {log}')

    def run(*cmd, **env):
        full_env = {"PATH": f"{tmp_path}:/usr/bin:/bin", **env}
        result = subprocess.run(["sh", str(ENTRYPOINT), *cmd], env=full_env, capture_output=True, text=True)
        calls = log.read_text().splitlines() if log.exists() else []
        return result, "wait_for_migrations" in " ".join(calls)

    return run


def test_runs_check_then_command(run_entrypoint):
    result, checked = run_entrypoint("echo", "started")
    assert result.returncode == 0
    assert "started" in result.stdout
    assert checked


@pytest.mark.parametrize(
    "cmd",
    [
        ("sh", "-c", "python manage.py migrate && python manage.py run_deploy_tasks"),
        ("python", "manage.py", "migrate"),
        ("python", "manage.py", "migrate", "--noinput"),
    ],
)
def test_migrate_command_skips_check(run_entrypoint, cmd):
    result, checked = run_entrypoint(*cmd)
    assert "skipping the migration check" in result.stderr
    assert not checked


@pytest.mark.parametrize("sub", ["showmigrations", "makemigrations", "migrate_schemas"])
def test_similar_commands_still_checked(run_entrypoint, sub):
    result, checked = run_entrypoint("echo", "python", "manage.py", sub)
    assert checked


def test_skip_env_var(run_entrypoint):
    result, checked = run_entrypoint("echo", "x", SKIP_MIGRATION_CHECK="true")
    assert "WARNING: SKIP_MIGRATION_CHECK=true" in result.stderr
    assert not checked


def test_failed_check_blocks_command(tmp_path):
    _stub_python(tmp_path, "exit 1")
    result = subprocess.run(
        ["sh", str(ENTRYPOINT), "echo", "started"],
        env={"PATH": f"{tmp_path}:/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "started" not in result.stdout


def test_logs_version_first(run_entrypoint):
    result, _ = run_entrypoint("echo", "started", APP_VERSION="main-abc1234")
    assert result.returncode == 0
    assert result.stderr.splitlines()[0] == "Meshflow API main-abc1234 starting: echo started"


def test_logs_unknown_version_without_failing(run_entrypoint):
    result, _ = run_entrypoint("echo", "started")
    assert result.returncode == 0
    assert result.stderr.splitlines()[0] == "Meshflow API unknown starting: echo started"


def test_version_logged_before_migrate_skip(run_entrypoint):
    result, _ = run_entrypoint("python", "manage.py", "migrate", APP_VERSION="2.2.2")
    lines = result.stderr.splitlines()
    assert lines[0].startswith("Meshflow API 2.2.2 starting:")
    assert "skipping the migration check" in lines[1]
