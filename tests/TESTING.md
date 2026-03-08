# Running Tests Locally

This document explains how to run unit and integration tests for the Meshflow API.

## Unit tests

Unit tests live in `Meshflow/` and use Django's test database. No external services are required.

```bash
cd Meshflow
pip install -r requirements.txt
pip install pytest pytest-django pytest-cov  # if not already installed
python -m pytest -v
```

With coverage:

```bash
python -m pytest -v --cov
```

## Integration tests

Integration tests live in `tests/integration/` and call the API over HTTP. They require:

1. The API running (with database migrated)
2. Seed data (`seed_integration_tests`)
3. Environment variables for the test runner

### Option A: Docker Compose (recommended)

Use the test compose file to start the API stack, then run the tests on your host. Run from the repository root.

```bash
# Start the API stack (db, migrations, api)
# First run will build images; migrations run automatically before api starts
docker compose -f docker-compose.test.yaml up -d

# Wait for the API to be ready (migrations run first; may take 30–60s)
until curl -s -f http://localhost:8000/api/status/ > /dev/null; do sleep 2; done

# Seed integration test data
docker compose -f docker-compose.test.yaml run --rm api python manage.py seed_integration_tests

# Activate venv as required
python3.14 -m venv venv-tests
source venv-tests/bin/activate

# Run integration tests
pip install -r tests/requirements-integration.txt
MESHFLOW_API_URL=http://localhost:8000 \
MESHFLOW_NODE_API_KEY=integration-test-key-a1b2c3d4e5f6 \
pytest tests/integration/ -v

# Stop the stack when done
docker compose -f docker-compose.test.yaml down
```

### Option B: Local Django + PostgreSQL

If you run the API locally (e.g. `python manage.py runserver`):

```bash
# In one terminal: start Django (ensure DB is migrated and reachable)
cd Meshflow
python manage.py migrate
python manage.py runserver

# Seed integration test data (run once)
python manage.py seed_integration_tests

# In another terminal: run integration tests
pip install -r tests/requirements-integration.txt
MESHFLOW_API_URL=http://localhost:8000 \
MESHFLOW_NODE_API_KEY=integration-test-key-a1b2c3d4e5f6 \
pytest tests/integration/ -v
```

### Option C: Main docker-compose

If you use the main `docker-compose.yaml` for development:

```bash
docker compose up -d postgres
docker compose run --rm migrations
docker compose up -d api

# Seed (use the api service)
docker compose run --rm api python manage.py seed_integration_tests

# Run tests
MESHFLOW_API_URL=http://localhost:8000 \
MESHFLOW_NODE_API_KEY=integration-test-key-a1b2c3d4e5f6 \
pytest tests/integration/ -v
```

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MESHFLOW_API_URL` | `http://localhost:8000` | Base URL of the API |
| `MESHFLOW_NODE_API_KEY` | `integration-test-key-a1b2c3d4e5f6` | API key from seed (fixed value) |
| `MESHFLOW_TEST_USERNAME` | `integration-test@example.com` | JWT user for assertions |
| `MESHFLOW_TEST_PASSWORD` | `integration-test-password` | JWT password |

### Running a subset of tests

```bash
# Only packet ingest tests
pytest tests/integration/test_packet_ingest.py -v

# Only downstream position tests
pytest tests/integration/test_downstream_positions.py -v

# By keyword
pytest tests/integration/ -v -k "dedup"
```
