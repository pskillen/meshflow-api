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

---

## 9. Monitoring / Prometheus

| Variable                | Default | Description                                      | Allowable Values         |
|-------------------------|---------|--------------------------------------------------|-------------------------|
| `PROMETHEUS_PASSWORD`   | (empty) | If set, enables Prometheus metrics endpoints and protection. | Any string              |

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

## 9. Monitoring / Prometheus

- **PROMETHEUS_PASSWORD**: If set, enables Prometheus metrics and adds authentication.

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