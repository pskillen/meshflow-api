# Release Process

This document describes how Docker images are built and pushed to GitHub Container Registry (ghcr.io) for the Meshflow API.

## Docker Image Tags

Each build produces two images (API and docs) in the same package with distinct tags:

| Tag pattern | Purpose |
| ----------- | ------- |
| `:latest`, `:latest-dev`, `:1.2.3` | Main API application |
| `:latest-docs`, `:latest-dev-docs`, `:1.2.3-docs` | Redocly API documentation |

Migrations run via the API image with a command override (`python manage.py migrate`); no separate migrations image.

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

**Trigger:** Publish a GitHub Release (not a pre-release) with a semver tag (e.g. `1.2.3`)

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
