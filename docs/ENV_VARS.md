# Meshflow Environment Variables

This document describes all environment variables used by the Meshflow Django project, grouped by functional area. For each variable, the default value, description, and allowable values (where applicable) are provided.

---

## 1. General Application

| Variable         | Default         | Description                                      | Allowable Values         |
|------------------|----------------|--------------------------------------------------|-------------------------|
| `APP_VERSION`    | `development`  | Application version string.                      | Any string              |
| `DEBUG`          | `false`        | Enable Django debug mode.                        | `true`, `false`, `1`, `0`, `True`, `False` |
| `SECRET_KEY`     | (dev key)      | Django secret key. **Set in production!**        | Any string              |
| `ALLOWED_HOSTS`  | `meshcontrol.local` | Comma-separated list of allowed hosts.      | Comma-separated hostnames or IPs |

---

## 2. Database

| Variable         | Default             | Description                                      | Allowable Values         |
|------------------|--------------------|--------------------------------------------------|-------------------------|
| `POSTGRES_DB`    | `meshflow_preprod` | PostgreSQL database name.                        | Any string              |
| `POSTGRES_USER`  | `meshflow_preprod` | PostgreSQL username.                             | Any string              |
| `POSTGRES_PASSWORD` | `meshflow_preprod` | PostgreSQL password.                         | Any string              |
| `POSTGRES_HOST`  | `localhost`        | PostgreSQL host.                                 | Hostname or IP          |
| `POSTGRES_PORT`  | `5432`             | PostgreSQL port.                                 | Integer (string)        |

---

## 3. JWT / Authentication

| Variable                        | Default   | Description                                              | Allowable Values         |
|----------------------------------|-----------|----------------------------------------------------------|-------------------------|
| `JWT_ACCESS_TOKEN_LIFETIME_MINUTES` | `1440`  | JWT access token lifetime in minutes (default 24h).      | Integer (string)        |
| `JWT_REFRESH_TOKEN_LIFETIME_DAYS`   | `30`    | JWT refresh token lifetime in days (default 30d).        | Integer (string)        |

---

## 4. Django Allauth / Social Auth

| Variable                | Default | Description                                  | Allowable Values         |
|-------------------------|---------|----------------------------------------------|-------------------------|
| `SITE_ID`               | `1`     | Django site ID for django-allauth.           | Integer (string)        |
| `GOOGLE_CLIENT_ID`      | (empty) | Google OAuth client ID.                      | Any string              |
| `GOOGLE_CLIENT_SECRET`  | (empty) | Google OAuth client secret.                  | Any string              |
| `GITHUB_CLIENT_ID`      | (empty) | GitHub OAuth client ID.                      | Any string              |
| `GITHUB_CLIENT_SECRET`  | (empty) | GitHub OAuth client secret.                  | Any string              |
| `DISCORD_CLIENT_ID`     | (empty) | Discord OAuth client ID.                      | Any string              |
| `DISCORD_CLIENT_SECRET` | (empty) | Discord OAuth client secret.                  | Any string              |

In the [Discord Developer Portal](https://discord.com/developers/applications), under OAuth2 → Redirects, register **both**:

- `{CALLBACK_URL_BASE}/api/auth/social/discord/callback/` — “Login with Discord” and code→token SPA flow.
- `{CALLBACK_URL_BASE}/api/auth/social/discord/connect/callback/` — link Discord to an **already signed-in** Meshflow user (JWT).

Discord **login** uses the OAuth pair above. **DM notifications** (test message and future alerts) use a separate bot application:

| Variable               | Default | Description                                                                 | Allowable values |
|------------------------|---------|-----------------------------------------------------------------------------|------------------|
| `DISCORD_BOT_TOKEN`    | (empty) | Bot token for `POST /users/@me/channels` and sending DMs. Not the OAuth secret. | Bot token string |

---

## 5. URLs & Frontend

| Variable                    | Default                   | Description                                      | Allowable Values         |
|-----------------------------|---------------------------|--------------------------------------------------|-------------------------|
| `CALLBACK_URL_BASE`         | `http://localhost:8000`   | Base URL for backend OAuth callback endpoints.    | Any valid URL           |
| `FRONTEND_URL`              | `http://localhost:5173`   | Base URL for the frontend app.                    | Any valid URL           |
| `FRONTEND_OAUTH_CALLBACK_PATH` | `/auth/callback`       | Path for frontend OAuth callback.                 | Any path string         |

---

## 6. CORS

| Variable                | Default | Description                                      | Allowable Values         |
|-------------------------|---------|--------------------------------------------------|-------------------------|
| `CORS_ALLOWED_ORIGINS`  | (empty) | Comma-separated list of additional allowed CORS origins. | Comma-separated URLs    |

---

## 7. Packet Ingestion

| Variable                      | Default | Description                                                       | Allowable Values         |
|-------------------------------|---------|-------------------------------------------------------------------|-------------------------|
| `PACKET_DEDUP_WINDOW_MINUTES` | `10`    | Time window (minutes) within which same sender+packet_id is treated as duplicate. | Integer (string)        |

---

## 8. Mesh monitoring

| Variable                               | Default | Description                                                                 | Allowable Values         |
|----------------------------------------|---------|-----------------------------------------------------------------------------|-------------------------|
| `MESH_MONITORING_VERIFICATION_SECONDS` | `180`   | After silence triggers verification, max seconds to wait for `last_heard` or a successful monitoring traceroute before confirming offline. | Integer (string)        |
| `MESH_MONITORING_NOTIFY_VERIFICATION_START` | (unset = **on**) | When unset, mesh monitoring sends a Discord DM when verification (monitor TR) **starts** for a watched node. Set to `0`, `false`, `no`, `off`, or empty to disable; `1` / `true` / `yes` / `on` to enable explicitly. | Boolean-ish string      |
| `MESH_MONITORING_VERIFICATION_NOTIFY_COOLDOWN_SECONDS` | `3600` | Minimum seconds between verification-start DMs for the same node (repeat episode starts). | Integer (string)        |

---

## 9. Monitoring / Prometheus

| Variable                | Default | Description                                      | Allowable Values         |
|-------------------------|---------|--------------------------------------------------|-------------------------|
| `PROMETHEUS_PASSWORD`   | (empty) | If set, enables Prometheus metrics endpoints and protection. | Any string              |

---

## 10. RF propagation

| Variable | Default | Description | Allowable Values |
|----------|---------|-------------|------------------|
| `RF_PROPAGATION_ENGINE_URL` | _(empty)_ | Base URL of the Meshtastic Site Planner engine (`POST /predict`). | HTTP(S) URL |
| `RF_PROPAGATION_ASSET_DIR` | `/var/meshflow/generated-assets/rf-propagation` | On-disk PNG cache directory (shared by API + RF worker). | Absolute path |
| `RF_PROPAGATION_RENDER_VERSION` | `4` | Bump to invalidate cached renders after pipeline changes. | Integer string |
| `RF_PROPAGATION_DEFAULT_RADIUS_M` | `50000` | Coverage radius hint (metres) passed to the engine. | Positive integer |
| `RF_PROPAGATION_COLORMAP` | `plasma` | Matplotlib colormap name for SPLAT output (validated in code). | Known cmap name |
| `RF_PROPAGATION_HIGH_RESOLUTION` | `false` | Site Planner high-resolution SRTM (~1 arc-sec vs ~3 arc-sec). | Boolean-ish |
| `RF_PROPAGATION_MIN_DBM` | `-130` | Lower bound of the rendered dBm colour scale. | Float |
| `RF_PROPAGATION_MAX_DBM` | `-50` | Upper bound of the rendered dBm colour scale. | Float |
| `RF_PROPAGATION_SIGNAL_THRESHOLD_DBM` | `-110` | SPLAT coverage threshold (dBm). | Float |
| `RF_PROPAGATION_NODATA_RGB` | `0,0,0` | RGB treated as transparent in PNG overlay. | `R,G,B` |
| `RF_PROPAGATION_NODATA_TOLERANCE` | `8` | Max per-channel distance from nodata RGB to clear alpha. | `0`–`255` |
| `RF_PROPAGATION_POLL_MAX_SECONDS` | `300` | Worker poll budget for engine job completion. | Integer seconds |
| `RF_PROPAGATION_READY_RETENTION` | `3` | Max `ready` renders kept per node. | Integer |

See **[docs/features/rf_propagation/README.md](features/rf_propagation/README.md)** for architecture.

---

## 11. Traceroute target reliability (auto selection)

Tunables for [automatic target selection reliability](../features/traceroute/algorithms.md#automatic-reliability). Only `trigger_type=3` (Monitoring) completed/failed `AutoTraceRoute` rows in the lookback window are used.

| Variable | Default | Description | Allowable Values |
|----------|---------|-------------|------------------|
| `TR_RELIABILITY_ENABLED` | `true` (on) | When false, disables soft penalty and hard cooldown. | `1`, `0`, `true`, `false`, `yes`, `no`, `on`, `off` (empty = default) |
| `TR_RELIABILITY_WINDOW_DAYS` | `14` | Lookback for reliability evidence and ordering of attempts. | Integer (string) |
| `TR_RELIABILITY_CONSECUTIVE_FAILS` | `4` | Minimum **consecutive** recent automatic failures (newest first) to hard-cooldown a (source, target) pair. Set to `0` to disable hard cooldown. | Integer (string) |
| `TR_RELIABILITY_SOFT_MAX` | `100` | Maximum soft penalty (same scale as distance/recency demerit) applied as this times `(failed/attempts)` when enough attempts exist. Set to `0` to disable soft penalty. | Float (string) |
| `TR_RELIABILITY_MIN_ATTEMPTS_SOFT` | `3` | Minimum completed or failed auto attempts in the window before applying the soft ratio penalty. | Integer (string) |

---

# Details

## 1. General Application

- **APP_VERSION**: Used to set the application version string, e.g., for display or logging.
- **DEBUG**: Controls Django's debug mode. Should be `false` in production.
- **SECRET_KEY**: The cryptographic key for Django. Must be set to a secure value in production.
- **ALLOWED_HOSTS**: Comma-separated list of hosts/domains the app will serve. Always includes `127.0.0.1` and `localhost` by default.

## 2. Database

- **POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT**: Standard PostgreSQL connection settings.

## 3. JWT / Authentication

- **JWT_ACCESS_TOKEN_LIFETIME_MINUTES**: How long (in minutes) JWT access tokens are valid.
- **JWT_REFRESH_TOKEN_LIFETIME_DAYS**: How long (in days) JWT refresh tokens are valid.

## 4. Django Allauth / Social Auth

- **SITE_ID**: Used by django-allauth for multi-site support.
- **GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET**: Credentials for Google OAuth.
- **GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET**: Credentials for GitHub OAuth.
- **DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET**: Credentials for Discord OAuth. Create an app at [Discord Developer Portal](https://discord.com/developers/applications) and add redirect URI `{CALLBACK_URL_BASE}/api/auth/social/discord/callback/`.

## 5. URLs & Frontend

- **CALLBACK_URL_BASE**: Used for constructing OAuth callback URLs.
- **FRONTEND_URL**: Used for CORS and OAuth redirects.
- **FRONTEND_OAUTH_CALLBACK_PATH**: Path on the frontend for OAuth callback.

## 6. CORS

- **CORS_ALLOWED_ORIGINS**: Additional allowed origins for CORS, comma-separated.

## 7. Packet Ingestion

- **PACKET_DEDUP_WINDOW_MINUTES**: Time window (minutes) within which the same sender+packet_id is treated as a duplicate. See `docs/packets/DEDUPLICATION.md`.

## 8. Mesh monitoring

- **MESH_MONITORING_VERIFICATION_SECONDS**: Verification window (seconds) after `NodePresence.verification_started_at` before marking offline and notifying watchers.
- **MESH_MONITORING_NOTIFY_VERIFICATION_START**: Discord when monitoring verification starts; unset means enabled, `false` / `0` / `off` / empty disables.
- **MESH_MONITORING_VERIFICATION_NOTIFY_COOLDOWN_SECONDS**: Cooldown (seconds) between verification-start DMs for the same node (default one hour).

## 9. Monitoring / Prometheus

- **PROMETHEUS_PASSWORD**: If set, enables Prometheus metrics and adds authentication.

## 10. RF propagation

- **RF_PROPAGATION_ENGINE_URL**, **RF_PROPAGATION_ASSET_DIR**, **RF_PROPAGATION_RENDER_VERSION**: Core wiring for Site Planner renders and PNG caching (see feature README).
- **RF_PROPAGATION_DEFAULT_RADIUS_M**, **RF_PROPAGATION_COLORMAP**, **RF_PROPAGATION_HIGH_RESOLUTION**, **RF_PROPAGATION_MIN_DBM**, **RF_PROPAGATION_MAX_DBM**, **RF_PROPAGATION_SIGNAL_THRESHOLD_DBM**: Tunables folded into `build_request` and the render input hash.
- **RF_PROPAGATION_NODATA_RGB** / **RF_PROPAGATION_NODATA_TOLERANCE**: PNG post-processing for Leaflet overlays.
- **RF_PROPAGATION_POLL_MAX_SECONDS**, **RF_PROPAGATION_READY_RETENTION**: Worker behaviour.

## 11. Traceroute target reliability

- **TR_RELIABILITY_ENABLED**: Master switch for automatic target reliability in `traceroute.target_selection`.
- **TR_RELIABILITY_WINDOW_DAYS**: How far back to read `AutoTraceRoute` rows for a given managed source.
- **TR_RELIABILITY_CONSECUTIVE_FAILS**: Streak of automatic failures (after the most recent attempt) required to exclude the target for that source. `0` disables exclusion.
- **TR_RELIABILITY_SOFT_MAX** / **TR_RELIABILITY_MIN_ATTEMPTS_SOFT**: Soft deprioritisation of targets with a poor success ratio without excluding them.

---

# Example `.env` file

```
APP_VERSION=1.0.0
DEBUG=false
SECRET_KEY=your-production-secret-key
ALLOWED_HOSTS=yourdomain.com,api.yourdomain.com

POSTGRES_DB=meshflow
POSTGRES_USER=meshflow
POSTGRES_PASSWORD=supersecret
POSTGRES_HOST=db
POSTGRES_PORT=5432

JWT_ACCESS_TOKEN_LIFETIME_MINUTES=1440
JWT_REFRESH_TOKEN_LIFETIME_DAYS=30

SITE_ID=1

GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-client-secret
DISCORD_CLIENT_ID=your-discord-client-id
DISCORD_CLIENT_SECRET=your-discord-client-secret

CALLBACK_URL_BASE=https://api.yourdomain.com
FRONTEND_URL=https://yourdomain.com
FRONTEND_OAUTH_CALLBACK_PATH=/auth/callback

CORS_ALLOWED_ORIGINS=https://yourdomain.com,https://admin.yourdomain.com

PACKET_DEDUP_WINDOW_MINUTES=10

PROMETHEUS_PASSWORD=your-prometheus-password
``` 