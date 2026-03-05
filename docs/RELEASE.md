# Release Process

This document describes how Docker images are built and pushed to GitHub Container Registry (ghcr.io) for the Meshflow API.

## Docker Image Tags

Each build produces three images:

| Image | Purpose |
| ----- | ------- |
| **API** | Main application |
| **Migrations** | Database migrations |
| **Docs** | Redocly API documentation |

## Release Triggers

### 1. Manual Release

**Workflow:** [manual-release.yaml](../.github/workflows/manual-release.yaml)

**Trigger:** Run manually via GitHub Actions → "Manual release" → "Run workflow"

**Tags pushed:**

- `latest-dev`, `latest-dev-migrations`, `latest-dev-docs`
- `{short-sha}`, `{short-sha}-migrations`, `{short-sha}-docs` (e.g. `abc1234`)

Use this to build and push from the current `main` branch without merging new commits.

---

### 2. Push to `main`

**Workflow:** [main.yaml](../.github/workflows/main.yaml)

**Trigger:** Push to `origin/main`

**Tags pushed:**

- `latest-dev`, `latest-dev-migrations`, `latest-dev-docs`
- `dev-{short-sha}`, `dev-{short-sha}-migrations`, `dev-{short-sha}-docs` (e.g. `dev-abc1234`)

---

### 3. Pre-release (Release Candidate)

**Workflow:** [pre-release.yaml](../.github/workflows/pre-release.yaml)

**Trigger:** Create a GitHub Release marked as "Pre-release" with a semver tag (e.g. `1.2.3-rc.4`)

**Tags pushed:**

- `latest-rc`, `latest-rc-migrations`, `latest-rc-docs`
- `{semver}`, `{semver}-migrations`, `{semver}-docs` (e.g. `1.2.3-rc.4`)

---

### 4. Production Release

**Workflow:** [release.yaml](../.github/workflows/release.yaml)

**Trigger:** Publish a GitHub Release (not a pre-release) with a semver tag (e.g. `1.2.3`)

**Tags pushed:**

- `latest`, `latest-migrations`, `latest-docs`
- `{semver}`, `{semver}-migrations`, `{semver}-docs` (e.g. `1.2.3`)

---

## Summary Table

| Trigger | Rolling tags | Version tags |
| ------- | ------------ | ------------ |
| Manual release | `latest-dev`, `latest-dev-migrations`, `latest-dev-docs` | `{sha}`, `{sha}-migrations`, `{sha}-docs` |
| Push to `main` | `latest-dev`, `latest-dev-migrations`, `latest-dev-docs` | `dev-{sha}`, `dev-{sha}-migrations`, `dev-{sha}-docs` |
| Pre-release | `latest-rc`, `latest-rc-migrations`, `latest-rc-docs` | `1.2.3-rc.4`, `1.2.3-rc.4-migrations`, `1.2.3-rc.4-docs` |
| Release | `latest`, `latest-migrations`, `latest-docs` | `1.2.3`, `1.2.3-migrations`, `1.2.3-docs` |

## Pulling Images

Replace `OWNER/REPO` with your GitHub org/repo (e.g. `myorg/meshflow-api`):

```bash
# Latest production
docker pull ghcr.io/OWNER/REPO:latest

# Specific version
docker pull ghcr.io/OWNER/REPO:1.2.3

# Latest dev build
docker pull ghcr.io/OWNER/REPO:latest-dev

# Latest release candidate
docker pull ghcr.io/OWNER/REPO:latest-rc
```
