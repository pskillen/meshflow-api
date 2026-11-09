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

## Bot contract test

`Meshflow/packets/tests/contract/test_bot_contract.py` (marker `contract`) checks that what the meshflow-bot sends is
what this API's goldens (`docs/packets/meshtastic-2.8/`) expect. For every key in the golden manifest it:

1. runs the bot's own serialiser (`MeshtasticPacketSerializer().serialise_raw_packet`) over the bot's capture subset and
   compares the body with `wire/<key>.json` (and the bot's `replayed: true` flag body with `wire/<key>+flag.json`);
2. checks the bot's replay classifier (`is_replayed`) agrees with the golden's `observation.replayed`;
3. posts the bot-produced body through the real ingest and compares with `golden/<key>.json`;
4. uploads five x28 NodeDB entries through the bot's node serialiser and checks a zeroed MAC and a 24-byte-cut long
   name do not overwrite stored values.

It needs a bot checkout (the bot's code used is standard library only, so none of its dependencies are installed):

```bash
cd Meshflow
MESHFLOW_BOT_PATH=/path/to/meshflow-bot pytest --no-cov -q --create-db -m contract packets/tests/contract
```

To test against the ref CI uses, clone the bot and check out the pin (from the API repo root):

```bash
git clone https://github.com/pskillen/meshflow-bot.git /path/to/meshflow-bot
git -C /path/to/meshflow-bot checkout "$(cat .github/contract/bot-ref)"
```

Without `MESHFLOW_BOT_PATH` the module is skipped, so the ordinary suite is unaffected.

CI runs it as `.github/workflows/contract.yaml`: on every PR and push to `main` against the bot ref pinned in
`.github/contract/bot-ref` (a release tag, or a full commit SHA until a bot release contains the fixtures), nightly with
API `main` against bot `main` (a drift signal), by hand with `workflow_dispatch` (`bot_ref` input), and, once the bot's PR job lands (not merged yet), from every
meshflow-bot PR (bot head against API `main`).

**Bumping the pin.** When a bot release ships or the bot's fixture data changes, open a PR that changes
`.github/contract/bot-ref` (one line, no comments) and carries any golden updates the new bot needs. A change needing
both sides lands API first (accepting old and new), then the bot, then the pin bump.

| Failure | Meaning |
| --- | --- |
| `bot output changed: update the api goldens and bump .github/contract/bot-ref` | The bot's serialiser produces a different body from `wire/<key>.json`. The diff is printed. Either the bot change is a regression, or regenerate and bump the pin: `python packets/tests/gen_meshtastic_wire.py --bot <bot>` for `wire/` and `manifest.json`, then `MESHFLOW_REGEN_GOLDENS=1 pytest packets/tests/test_meshtastic_goldens.py` for `golden/` (see `docs/packets/meshtastic-2.8/README.md`). |
| `api manifest keys missing from the bot's subset.json` | A golden exists for a capture the bot no longer ships. |
| `new bot fixture: add a golden for ...` | The bot added a capture with no API golden; add it so it cannot go untested. |
| `bot is_replayed=... but the api golden has replayed=...` | The bot's and the API's replay rules disagree. |
| An ingest mismatch | The API's behaviour for the same body changed; update the golden only if that is intended. |
| `has no docs/meshtastic_packets/2.8/subset.json`, `bot captures.json has no capture`, `has no nodedb.json`, `bot API changed: ...` | `MESHFLOW_BOT_PATH` is wrong, or the bot moved a fixture or module the test uses; update the lookup or imports in `test_bot_contract.py`. |
| `the API now has a top-level 'src' / 'tools' package` | Name clash with the bot's import path; change how the test imports the bot. |

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
python manage.py run_deploy_tasks
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
