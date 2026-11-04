#!/bin/sh
# Fail closed: refuse to start the API or a worker while any migration is unapplied.
# This never applies migrations; only the dedicated migrations container does that.
set -e

# First line of every container's log: which build is this? (APP_VERSION is the image's VERSION build arg, the same
# string /health reports.) Goes to stderr so it never pollutes a command's stdout. Never fails the boot.
printf 'Meshflow API %s starting: %s\n' "${APP_VERSION:-unknown}" "$*" >&2

# The migrations container runs `manage.py migrate` (directly or via `sh -c`); it must not wait on itself.
# Matches the word `migrate` exactly after `manage.py`, so showmigrations/makemigrations do not count.
case " $* " in
    *"manage.py migrate "*)
        echo "INFO: command is 'manage.py migrate'; skipping the migration check." >&2
        exec "$@"
        ;;
esac

if [ "${SKIP_MIGRATION_CHECK:-}" = "true" ]; then
    echo "WARNING: SKIP_MIGRATION_CHECK=true - NOT checking for unapplied migrations. This process may run against the wrong schema." >&2
else
    python manage.py wait_for_migrations
fi

exec "$@"
