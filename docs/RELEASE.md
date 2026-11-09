# Release Process

This document describes how Docker images are built and pushed to GitHub Container Registry (ghcr.io) for the Meshflow API.

## Docker Image Tags

Each build produces two images (API and docs) in the same package with distinct tags:

| Tag pattern | Purpose |
| ----------- | ------- |
| `:latest`, `:latest-dev`, `:1.2.3` | Main API application |
| `:latest-docs`, `:latest-dev-docs`, `:1.2.3-docs` | Redocly API documentation |

Migrations run via the API image with a command override (`python manage.py migrate && python manage.py run_deploy_tasks`); 
no separate migrations image. The API and workers refuse to start until migrations are applied; see [DEPLOY.md](DEPLOY.md).

## Release Triggers

### 1. Push to `main`

**Workflow:** [main.yaml](../.github/workflows/main.yaml)

**Trigger:** Push to `origin/main`

**Tags pushed:**

- `latest-dev`, `latest-dev-docs` (overwrite each time)
- Baked version: `main-{short-sha}`

---

### 2. Pre-release (Release Candidate)

**Workflow:** [pre-release.yaml](../.github/workflows/pre-release.yaml)

**Trigger:** Create a GitHub Release marked as "Pre-release" with a semver tag (e.g. `1.2.3-rc.4`)

**Tags pushed:**

- `latest-rc`, `latest-rc-docs`
- `{semver}`, `{semver}-docs` (e.g. `1.2.3-rc.4`)

---

### 3. Production Release

**Workflow:** [release.yaml](../.github/workflows/release.yaml)

**Trigger:** A GitHub Release is released (`released` event: publishing a full release, or promoting a pre-release; pre-releases alone do not fire it) with a semver tag (e.g. `1.2.3`)

**Tags pushed:**

- `latest`, `latest-docs`
- `{semver}`, `{semver}-docs` (e.g. `1.2.3`)
- Semver components: `1`, `1.2`, `1-docs`, `1.2-docs`

---

## Summary Table

| Trigger | Rolling tags | Version tags |
| ------- | ------------ | ------------ |
| Push to `main` | `latest-dev`, `latest-dev-docs` | (baked: main-{sha}) |
| Pre-release | `latest-rc`, `latest-rc-docs` | `1.2.3-rc.4`, `1.2.3-rc.4-docs` |
| Release | `latest`, `latest-docs` | `1`, `1.2`, `1.2.3` and `*-docs` variants |

## Pulling Images

```bash
# Latest production API
docker pull ghcr.io/pskillen/meshflow-api:latest

# Specific version
docker pull ghcr.io/pskillen/meshflow-api:1.2.3

# Latest dev build
docker pull ghcr.io/pskillen/meshflow-api:latest-dev

# Latest release candidate
docker pull ghcr.io/pskillen/meshflow-api:latest-rc

# Docs (same package, -docs suffix)
docker pull ghcr.io/pskillen/meshflow-api:latest-docs
```

## PR Builds

PR builds do **not** push images to the registry. The workflow builds locally and runs smoke + integration tests in a single job.

In the `build-and-smoke` job the API image is built once with buildx (`load: true`, `push: false`) as `meshflow-api:ci`, reading the layer cache that main builds write (GHA cache scope `meshflow-api`; PRs never write it). `docker-compose.test.yaml` tags its API services `${MESHFLOW_API_IMAGE:-meshflow-api:ci}`, so CI runs `up -d --no-build` and reuses that image; a local `docker compose build` still works. The job runs in parallel with `verify` and the bot contract check.

The `VERSION` build arg is declared late in the `Dockerfile` so a new version only invalidates the last layers, not apt/pip.

## GHCR Cleanup

Untagged package versions are removed by [ghcr-cleanup.yaml](../.github/workflows/ghcr-cleanup.yaml), weekly (Sunday 04:41 UTC) or on demand (`workflow_dispatch`). It is not part of the build workflows: the action inspects every version one at a time and takes 6-10 minutes. Runs are serialised (concurrency group `ghcr-cleanup-meshflow-api`, never cancelled mid-delete). Untagged multi-platform manifests (provenance attestations referenced by tagged images) are kept.
