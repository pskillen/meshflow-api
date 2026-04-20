# Redis usage in Meshflow API

Meshflow runs a **single** Redis instance (see `docker-compose.yaml`). Different logical consumers use **different Redis logical databases** (`/0`, `/1`, `/2`, …) so workloads stay isolated: you can flush or inspect one concern without touching others, and `redis-cli -n <db>` maps cleanly to “what is this key for?”.

Configuration lives in [`Meshflow/Meshflow/settings/base.py`](../Meshflow/Meshflow/settings/base.py) (`CHANNEL_LAYERS`, `CELERY_BROKER_URL`, `CACHES`).

---

## Database map

- **DB 0 — Django Channels layer (`channels_redis`)**  
  - **Purpose:** Pub/sub and group membership for WebSocket delivery (`channel_layer.group_send` / `group_add`).  
  - **Code:** [`Meshflow/ws/consumers.py`](../Meshflow/ws/consumers.py).  
  - **Consumers / groups:**
    - **`NodeConsumer`** (`ws/nodes/?api_key=…`) — bots join group `node_{node_id}`; receives **`node_command`** events (e.g. traceroute commands). Emitters include traceroute views/tasks and management commands (see grep for `group_send` under `Meshflow/`).
    - **`TextMessageConsumer`** — authenticated UI clients join group **`text_messages`**; receives **`text_message`** events for mesh text broadcasts ([`Meshflow/ws/services/text_message.py`](../Meshflow/ws/services/text_message.py)).
    - **`TracerouteConsumer`** (`ws/traceroutes/?token=…`) — clients join group **`traceroutes`**; receives **`traceroute_update`** events ([`Meshflow/traceroute/ws_notify.py`](../Meshflow/traceroute/ws_notify.py)).
  - **TTL:** Connection/session lifetime; Channels manages internal keys.

- **DB 1 — Celery broker + result backend**  
  - **Purpose:** Message broker and (same URL) **result backend** for Celery (`CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`).  
  - **Override:** Set `CELERY_BROKER_URL` in the environment (see [`Meshflow/.env.example`](../Meshflow/.env.example)). Default URL uses DB **1** so DB 0 stays dedicated to Channels.  
  - **App:** [`Meshflow/Meshflow/celery.py`](../Meshflow/Meshflow/celery.py) — `app.autodiscover_tasks(...)` loads task modules from listed Django apps.  
  - **Planned:** A dedicated **`rf_renders`** queue for RF propagation renders (documented in the RF propagation pipeline plan); workers can subscribe only to that queue without touching the default queue name.

- **DB 2 — Django cache (`django_redis`)**  
  - **Purpose:** Default Django cache backend (`CACHES["default"]`). Anything using `django.core.cache` lands here.  
  - **Known key patterns:**
    - **`tr:strategy:last:{feeder_pk}:{strategy}`** — traceroute target-strategy LRU rotation ([`Meshflow/traceroute/strategy_rotation.py`](../Meshflow/traceroute/strategy_rotation.py)); TTL **`STRATEGY_LRU_TTL_SECONDS`** (30 days).
    - **`tr:envelope:v1:{constellation_pk}`** — cached constellation envelope for strategy / perimeter logic ([`Meshflow/constellations/geometry.py`](../Meshflow/constellations/geometry.py)); TTL **`ENVELOPE_TTL_SECONDS`** (600 s).
    - **`discord_connect_oauth:{nonce}`** — one-time Discord OAuth link nonces ([`Meshflow/users/discord_connect_oauth.py`](../Meshflow/users/discord_connect_oauth.py)); TTL **900 s** (`STATE_MAX_AGE`).
  - Prefer **feature prefixes** (`tr:`, `discord_connect_oauth:`) so keys are identifiable in `KEYS`/monitoring.

- **DB 3 — Meshtastic Site Planner engine**
  - **Purpose:** Consumed by the **`rf-propagation`** (a.k.a. `site-planner` in Portainer) sibling container running the Meshtastic Site Planner image. The engine uses Redis for its **own** async prediction task state (task IDs, status); Meshflow API code does **not** read this DB directly — only HTTP calls to the engine (see [docs/features/rf_propagation/README.md](features/rf_propagation/README.md)).
  - **Important:** DB **2** must **not** be reused for Site Planner: it is already Django cache (see above). Configure the engine with `REDIS_URL=redis://redis:6379/3` locally, or `redis://:${REDIS_PASSWORD}@redis:6379/3` in Portainer where Redis runs with `--requirepass`.

---

## Conventions for new Redis usage

1. Pick the **next free DB index** (after documenting existing ones in this file).
2. Use a **stable key prefix** per feature (`tr:…`, etc.).
3. Set a **TTL** on cache keys unless there is a strong reason not to (avoid unbounded growth).
4. Update **this document** in the same PR when adding a consumer or changing DB assignment.

---

## Environment variables

See **[docs/ENV_VARS.md](./ENV_VARS.md)** for general env documentation.

Redis-related variables used by Meshflow settings:

| Variable | Role |
|----------|------|
| `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD` | Build URLs for Channels (DB 0), Celery (DB 1), cache (DB 2) in `settings/base.py`. |
| `CELERY_BROKER_URL` | Optional override for Celery broker + result backend (defaults to `redis://…/1`). |

RF propagation engine: **`RF_PROPAGATION_ENGINE_URL`** is consumed by the Celery render task (`rf_propagation.tasks.render_rf_propagation`); the engine container uses **`REDIS_URL`** pointing at DB **3** so it does not collide with Django cache on DB 2.

---

## Debugging cheatsheet

From the Compose project root (service name `redis`):

```bash
# Django cache keys (strategy LRU, envelopes, Discord nonces, …)
docker compose exec redis redis-cli -n 2 KEYS 'tr:*'
docker compose exec redis redis-cli -n 2 KEYS 'discord_connect_oauth:*'

# Celery broker DB — list length of default queue (name may vary with config; often "celery")
docker compose exec redis redis-cli -n 1 LLEN celery

# Channels layer — internal keys (channels_redis); patterns vary by version
docker compose exec redis redis-cli -n 0 KEYS '*'

# Optional: pub/sub activity (Channels may use other structures too)
docker compose exec redis redis-cli -n 0 PUBSUB CHANNELS '*'
```

Do **not** run `FLUSHDB` on shared DBs in production without understanding every consumer on that index.

---

## Audit notes (codebase)

- No raw `redis.Redis()` usage in app code; no `django-redis-sessions` found.
- No `rediss://` in-repo (TLS would be an ops-level URL change).
- Test settings use in-memory Channels (`Meshflow/Meshflow/settings/test.py`) — not production Redis layout.

---

## Future considerations

If isolation or eviction policies become insufficient (e.g. heavy cache vs. Celery load), consider **separate Redis instances** per concern instead of only DB indices on one server.
