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

On **read**, the bot includes `region_scope` when `CHANNEL_INFO` exposes it. Today the response is **name + secret only**, so:

- After **apply**, the bot re-reads the device and **merges `region_scope` from the apply payload** by `mc_channel_idx` before posting `mc-channel-sync` (avoids duplicate unscoped canonical rows).
- On **connect** sync, the API may **preserve** scope from the feeder’s existing slot link when the snapshot omits scope but name/type still match.

On **apply**, after each `set_channel`, the bot calls `meshcore.commands.set_flood_scope` for that row’s scope (companion **active** flood scope; only the last slot’s scope remains active on the radio until the operator changes channel in the MeshCore app).

---

## Related

- [data-model.md](data-model.md) — canonical channel identity
- [ADR-0002](../../packet-ingestion/adr/0002-mc-channel-modelling.md) — normative modelling
