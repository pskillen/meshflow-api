"""
Wait until every migration is applied, or fail. Never applies anything.

Run by docker-entrypoint.sh before the API and the Celery workers start, so a
new image never serves traffic against an old schema (fail closed). Only the
dedicated migrations container may run ``migrate``.
"""

import os
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.utils import OperationalError


def _env_number(name, default):
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        raise CommandError(f"{name} must be a number, got {raw!r}")


def get_unapplied_migrations():
    """Return ``["app.name", ...]`` for each unapplied migration (as ``migrate --check`` sees them)."""
    connection.close_if_unusable_or_obsolete()
    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    return [f"{migration.app_label}.{migration.name}" for migration, _backwards in plan]


class Command(BaseCommand):
    help = (
        "Exit 0 once all migrations are applied; exit non-zero if some are still unapplied "
        "(or the database is unreachable) after the timeout. Never runs migrate."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--timeout",
            type=float,
            default=None,
            help="Seconds to wait (env MIGRATION_WAIT_TIMEOUT_SECONDS, default 120). 0 checks once.",
        )
        parser.add_argument(
            "--interval",
            type=float,
            default=None,
            help="Seconds between checks (env MIGRATION_WAIT_INTERVAL_SECONDS, default 10).",
        )

    def handle(self, *args, **options):
        timeout = options["timeout"]
        if timeout is None:
            timeout = _env_number("MIGRATION_WAIT_TIMEOUT_SECONDS", 120)
        interval = options["interval"]
        if interval is None:
            interval = _env_number("MIGRATION_WAIT_INTERVAL_SECONDS", 10)

        deadline = time.monotonic() + timeout
        while True:
            unapplied = None
            try:
                unapplied = get_unapplied_migrations()
            except OperationalError as exc:
                problem = f"database unavailable: {exc}"
            else:
                if not unapplied:
                    self.stdout.write("All migrations applied.")
                    return
                problem = f"{len(unapplied)} unapplied migrations: {', '.join(unapplied)}"

            if time.monotonic() >= deadline:
                if unapplied:
                    raise CommandError(
                        f"{len(unapplied)} unapplied migrations; run the migrations container. "
                        f"({', '.join(unapplied)})"
                    )
                raise CommandError(f"Gave up waiting for the database ({problem}); run the migrations container.")

            self.stderr.write(f"Waiting for migrations ({problem}); retrying in {interval:g}s")
            time.sleep(interval)
