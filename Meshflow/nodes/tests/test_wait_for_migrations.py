from types import SimpleNamespace
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.utils import OperationalError

import pytest

CMD = "nodes.management.commands.wait_for_migrations"


def _plan(*names):
    return [(SimpleNamespace(app_label="nodes", name=n), False) for n in names]


@pytest.fixture(autouse=True)
def no_db_connection():
    with mock.patch(f"{CMD}.connection"):
        yield


@pytest.fixture
def no_sleep():
    with mock.patch(f"{CMD}.time.sleep") as sleep:
        yield sleep


@pytest.fixture
def mock_executor():
    with mock.patch(f"{CMD}.MigrationExecutor") as cls:
        yield cls.return_value


def test_no_unapplied_migrations_exits_zero_at_once(mock_executor, no_sleep):
    mock_executor.migration_plan.return_value = []
    call_command("wait_for_migrations", timeout=30, interval=1)
    no_sleep.assert_not_called()


def test_unapplied_migrations_retry_then_fail(mock_executor, no_sleep):
    mock_executor.migration_plan.return_value = _plan("0042_new", "0043_newer")
    with mock.patch(f"{CMD}.time.monotonic", side_effect=[0, 0, 5, 10, 20]):
        with pytest.raises(CommandError, match=r"2 unapplied migrations; run the migrations container"):
            call_command("wait_for_migrations", timeout=10, interval=5)
    assert no_sleep.call_count >= 1
    assert mock_executor.migration_plan.call_count >= 2


def test_unapplied_migrations_applied_while_waiting(mock_executor, no_sleep):
    mock_executor.migration_plan.side_effect = [_plan("0042_new"), []]
    call_command("wait_for_migrations", timeout=60, interval=1)
    no_sleep.assert_called_once_with(1)


def test_timeout_zero_checks_once(mock_executor, no_sleep):
    mock_executor.migration_plan.return_value = _plan("0042_new")
    with pytest.raises(CommandError, match="1 unapplied migrations"):
        call_command("wait_for_migrations", timeout=0)
    no_sleep.assert_not_called()
    assert mock_executor.migration_plan.call_count == 1


def test_database_unavailable_retries_then_fails(no_sleep):
    with mock.patch(f"{CMD}.MigrationExecutor", side_effect=OperationalError("connection refused")) as cls:
        with mock.patch(f"{CMD}.time.monotonic", side_effect=[0, 0, 5, 10]):
            with pytest.raises(CommandError, match="database"):
                call_command("wait_for_migrations", timeout=10, interval=5)
    assert cls.call_count == 3
    assert no_sleep.call_count == 2


def test_env_defaults_for_timeout_and_interval(mock_executor, no_sleep, monkeypatch):
    monkeypatch.setenv("MIGRATION_WAIT_TIMEOUT_SECONDS", "0")
    monkeypatch.setenv("MIGRATION_WAIT_INTERVAL_SECONDS", "3")
    mock_executor.migration_plan.return_value = _plan("0042_new")
    with pytest.raises(CommandError):
        call_command("wait_for_migrations")
    no_sleep.assert_not_called()


def test_never_applies_migrations(mock_executor, no_sleep):
    mock_executor.migration_plan.return_value = _plan("0042_new")
    with mock.patch("django.core.management.commands.migrate.Command.handle") as migrate:
        with pytest.raises(CommandError):
            call_command("wait_for_migrations", timeout=0)
    migrate.assert_not_called()
    mock_executor.migrate.assert_not_called()
