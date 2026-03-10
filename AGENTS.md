# Meshflow API – Agent Context

Django REST Framework backend for a distributed Meshtastic mesh network monitoring system. Monitors a country-wide mesh of nodes; various MonitorNodes listen for packets from ObservedNodes and report to this API.

## Project Structure

```
Meshflow/
├── manage.py                 # Django entry point
├── Meshflow/                 # Project settings, urls, asgi
├── nodes/                    # Node management (ObservedNode, ManagedNode)
├── constellations/           # Regional groupings (Constellation, MessageChannel)
├── packets/                  # Packet ingestion, processing, services
├── text_messages/            # Text message handling
├── stats/                    # Packet statistics
├── users/                    # Auth, JWT, social auth
├── common/                   # Shared utilities (mesh_node_helpers, etc.)
└── ws/                       # WebSocket consumers
```

## Key Concepts

- **ObservedNode**: Meshtastic radio node seen on the mesh (from packet observations). Has `last_heard`, `node_id_str`, position/metrics via `NodeLatestStatus`.
- **ManagedNode**: User-owned node linked to a Constellation. Part of system infrastucture. Matched to ObservedNode by `node_id`.
- **Constellation**: Subset of nodes representing a region. Has `ConstellationUserMembership` (admin/editor/viewer).
- **NodeAPIKey**: API keys for node authentication, scoped to a Constellation.

## API Layout

All endpoints under `/api/`:

- `api/nodes/observed-nodes/` – List, retrieve, search observed nodes
- `api/nodes/observed-nodes/recent_counts/` – Node counts by time window (2h, 24h, 7d, 30d, 90d, all)
- `api/nodes/observed-nodes/mine/` – User's claimed nodes
- `api/nodes/managed-nodes/` – Managed nodes
- `api/constellations/` – Constellations, memberships, channels
- `api/packets/` – Packet ingestion
- `api/stats/` – Packet statistics
- `api/messages/` – Text messages
- `api/token/` – JWT obtain, refresh, verify
- `api/auth/` – Social auth (OAuth)

## Development

```bash
cd Meshflow
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
# or: uvicorn Meshflow.asgi:application --reload --port 8000
```

## Testing

When making changes, **add or update unit and integration tests** as needed. New behaviour should be covered by tests; changes to existing behaviour should update the corresponding tests.

- **Unit tests**: `Meshflow/` – Django TestCase/pytest, run with `python -m pytest Meshflow/ -v`
- **Integration tests**: `tests/integration/` – HTTP client tests against live API, run with `pytest tests/integration/ -v` (requires API running and `seed_integration_tests`)

Make sure to activate the venv `venv/bin/activate`

See **tests/TESTING.md** for detailed instructions (unit tests, integration tests via Docker Compose or local Django).

## Code Style

- **Linting**: black, isort, flake8
- **Python**: 3.12+
- **Django**: 4.x / 5.x
- **DRF**: ViewSets, serializers, JWT auth

## Conventions

- When catching multiple exception types, do not use parentheses (e.g. `except ValueError, TypeError`). The project linter prefers this style.
- Add or update unit and integration tests when changing behaviour.
- Use `timezone.now()` for timestamps; keep `last_heard` timezone-aware.
- Node IDs: `node_id` (BigInteger), `node_id_str` (hex, e.g. `!12345678`). Use `common.mesh_node_helpers` for conversion.
- Pagination: `PageSizePagination` (default 100, max 1000). Use `page_size` query param.
- ObservedNode list: supports `last_heard_after` (ISO 8601) for time-based filtering; ordered by `-last_heard`.

## Migrations

Always create migrations for model changes:

```bash
python manage.py makemigrations
python manage.py migrate
```

## Documentation

Always update openapi.yaml when modifying API contract. openapi.yaml is the contract shared between API and clients;
where the code deviates from openapi.yaml, the OpenAPI spec is often correct. Check for what to do if this happens.

## Source control

When asked to create a pull request description, follow the template at
.github/pull_request_template.md, and output a markdown file named `tmp/PR.md`
