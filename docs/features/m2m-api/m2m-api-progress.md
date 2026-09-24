# M2M API — progress

**Tracking:** https://github.com/pskillen/meshflow-api/issues/416
**Plan:** `scratch/plans/m2m-api.plan.md` (local) and the Cursor plan `m2m_api_delivery`
**Branch:** `api-416/paddy/m2m-api`

---

## Overall status

**Status:** Complete (pending merge)

---

## Guest throttling

**Status:** Complete

---

## Keys, opt-out, Meshtastic and MeshCore data

**Status:** Complete

**Delivered**

- `m2m_api` app: hashed keys, terms grace, CRUD, withdraw, throttles, usage flush.
- `ObservedNode.m2m_opt_out`.
- `/api/m2m/v1/meshtastic/*` and `/api/m2m/v1/meshcore/*`. MeshCore `health` is null.
- `openapi-m2m.yaml` and `Dockerfile-redocly-m2m`.

**Verify**

- [x] `Meshflow/m2m_api/tests/test_m2m_api.py`
- [x] `Meshflow/common/tests/test_throttling.py`

---

## Next

- UI pull request on `ui-362/paddy/m2m-developer-access`.

