# MeshCore region scope — progress

**Tracking:** [meshflow-api#391](https://github.com/pskillen/meshflow-api/issues/391)  
**Plan:** `.cursor/plans/meshcore_region_scopes_db255499.plan.md`  
**Repos:** meshflow-api, meshflow-bot, meshflow-ui

---

## Overall status

**Status:** Ready for PRs

**Branch (API):** `api-391/pskillen/region-scope` (from `api-391/pskillen/mc-channel-sync-docs`)

---

## Documentation

**Status:** Done

- `region-scope.md`, progress/outstanding pair, hub doc map
- `data-model.md`, `flow.md`, ADR-0002 amended

---

## API — schema and identity

**Status:** Done

- Migration `0015_messagechannel_region_scope`, `region_scope` field, drop `mc_hashtag`
- `channel_identity`, `mc_region_scope`, labels, tests

---

## API — contract and timeless docs

**Status:** Done

- Serializers, `openapi.yaml`, admin

---

## meshflow-bot

**Status:** Done (branch `bot-391/pskillen/region-scope`)

- `channels.py` read/apply `region_scope`; tests updated

---

## meshflow-ui

**Status:** Done (branch `ui-391/pskillen/region-scope`)

- Editor, message labels, models, tests

---

## Next

- Atomic commits + PRs (api, bot, ui) via github-personal MCP
