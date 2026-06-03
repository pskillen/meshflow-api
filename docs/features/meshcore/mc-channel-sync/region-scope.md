# MeshCore region scope

**Tracking:** [meshflow-api#391](https://github.com/pskillen/meshflow-api/issues/391)

MeshCore **region filtering** limits which flood traffic a node forwards. Operators assign a **scope name** per channel (or use null scope for legacy “hear everything” behaviour). Meshflow stores scope on the **canonical** `MessageChannel` row so the same hashtag in different regions is distinct for ingest, history, and UI.

**Background:** [Region filtering](https://blog.meshcore.io/2026/01/20/region-filtering) · [Default scope](https://blog.meshcore.io/2026/04/17/default-scope)

---

## Naming rules

| Rule | Detail |
|------|--------|
| Characters | Lowercase letters, digits, hyphen (`a-z`, `0-9`, `-`) |
| Length | Max **29 UTF-8 bytes** |
| Null scope | `*`, empty string, or `none` → stored as `NULL` (legacy / no scope) |
| Wire `#` | Do **not** store leading `#` on `region_scope`; hashtags use `name` without `#` |

---

## API field

On `MessageChannel` when `protocol=MESHCORE`:

- **`region_scope`** — optional `CharField(max_length=29)`, nullable
- **`name`** — for `HASHTAG`, the tag without `#`; for `PUBLIC`, the public channel name
- **Uniqueness** — `(constellation, protocol, name, mc_channel_type, region_scope)` with separate partial indexes for null vs non-null scope

Sync and apply payloads include `region_scope` on each entry ([flow.md](flow.md)). Normalization lives in `Meshflow/common/mc_region_scope.py`.

---

## UI and labels

Display helpers append scope when set, e.g. `#galloway · sample-west` (`Meshflow/common/mc_channel_labels.py`). Node Settings channel editor validates scope like MeshCore rules; Messages channel picker uses the same labels.

---

## Bot / device

On **read**, the bot includes `region_scope` in each snapshot entry when the companion protocol exposes it. Today `CMD_GET_CHANNEL` / `CHANNEL_INFO` returns **name + secret only** — v1 sync may send `region_scope: null` until firmware exposes per-channel scope ([region-scope-outstanding.md](region-scope-outstanding.md)).

On **apply**, after `set_channel`, the bot calls `meshcore.commands.set_flood_scope` when `region_scope` is set (best-effort; confirm per-channel vs global on hardware).

---

## Related

- [data-model.md](data-model.md) — canonical channel identity
- [ADR-0002](../../packet-ingestion/adr/0002-mc-channel-modelling.md) — normative modelling
