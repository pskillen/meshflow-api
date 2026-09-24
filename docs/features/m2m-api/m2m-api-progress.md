# M2M API — progress

**Tracking:** https://github.com/pskillen/meshflow-api/issues/416
**Plan:** `scratch/plans/m2m-api.plan.md` (local) and the Cursor plan `m2m_api_delivery`
**Branch:** `api-416/paddy/m2m-api`

---

## Overall status

**Status:** In progress

---

## Design docs

**Status:** Complete
**Delivered:** Cherry-picked design commits onto this branch (`docs/features/m2m-api/README.md`, UTC-day note in packet-stats).

---

## Guest throttling

**Status:** In progress

**Delivered**

- `common/throttling.py` with CF-aware `client_ip`, guest burst, guest expensive, and user backstop.
- Attached on guest-readable views only. Ingest has no throttle classes.
- Guest `stats/global` range clamped to 30 days and cached 60s.

**Verify**

- [x] `Meshflow/common/tests/test_throttling.py`

---

## Next

- M2M keys, terms, withdraw.
