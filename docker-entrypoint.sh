#!/bin/sh
# Fail closed: refuse to start the API or a worker while any migration is unapplied.
# This never applies migrations; only the dedicated migrations container does that.
set -e

if [ "${SKIP_MIGRATION_CHECK:-}" = "true" ]; then
    echo "WARNING: SKIP_MIGRATION_CHECK=true - NOT checking for unapplied migrations. This process may run against the wrong schema." >&2
else
    python manage.py wait_for_migrations
fi

exec "$@"
