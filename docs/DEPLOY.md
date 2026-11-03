# Deploying the API: migrations guard

The API (daphne) and the Celery processes (worker, rf-worker, beat) **refuse to start while any migration is
unapplied**. They run against the wrong schema otherwise: Watchtower updates running containers when a new image
appears, but the one-shot migrations container exits and is never updated or re-run.

## What the guard does

The image has an `ENTRYPOINT` (`docker-entrypoint.sh`) that runs `python manage.py wait_for_migrations`, then
`exec`s the container command. Because it is an `ENTRYPOINT`, it covers every container that reuses the image with a
command override (celery worker, rf-worker, beat).

`wait_for_migrations` builds the same plan as `migrate --check`. It exits 0 when nothing is unapplied. Otherwise it
logs the unapplied migrations (`app.name`), waits, and checks again. If they are still unapplied at the timeout it
exits non-zero ("N unapplied migrations; run the migrations container") and the container stops (and is restarted by
`restart: unless-stopped`, so it recovers once migrations have run). An unreachable database is treated the same way.
**It never applies migrations**; only the dedicated migrations container does (several replicas would race).

| Variable | Default | Description |
|---|---|---|
| `MIGRATION_WAIT_TIMEOUT_SECONDS` | `120` | How long to wait. `0` checks once. (Also `--timeout`.) |
| `MIGRATION_WAIT_INTERVAL_SECONDS` | `10` | Seconds between checks. (Also `--interval`.) |
| `SKIP_MIGRATION_CHECK` | unset | `true` skips the check and logs a loud warning. For local dev or emergencies only. |

The entrypoint itself skips the check (logging one INFO line) when the command it is about to run is a migrate: the
arguments contain `manage.py` followed by exactly `migrate` (so `sh -c "python manage.py migrate && ..."` as used by
the migrations container qualifies; `showmigrations` and `makemigrations` do not). No compose or Portainer
configuration is needed for the migrations container to work.

## Deploy order

1. Pull the new images.
2. Run the migrations container.
3. The API and workers start (or restart) once it has finished.

In Portainer an exited migrations container must be **recreated with a re-pulled image** (Recreate with "Re-pull
image"), not just started: starting it again reruns the old image and applies nothing new.

Downtime until migrations run is accepted; serving against the wrong schema is not.
