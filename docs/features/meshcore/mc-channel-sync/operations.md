# mc-channel-sync — operations

Purpose: authentication, multi-API deployments, scaling, and common failure modes. Timeless reference for operators and developers.

---

## Authentication

| Direction | Auth | Feeder identity |
|-----------|------|-----------------|
| Device → API (`mc-channel-sync`) | Node API key (`NodeAuth`) | URL `{feeder_pubkey_prefix}` + optional `X-MeshCore-Feeder-Pubkey` |
| UI → API (`apply-mc-channel-config`) | User JWT | Managed node `owner` |
| API → bot (WebSocket) | Bot connected with same API key / feeder group | `node_mc_{internal_id}` |

Shared constellation API keys are supported: each `ManagedNode` must have a distinct `mc_pubkey`; the URL prefix disambiguates the observer.

See [feeder-bootstrap.md](../feeder-bootstrap.md) for bootstrap and 403 JSON codes.

---

## meshflow-bot environment

| Variable | Role |
|----------|------|
| `RADIO_PROTOCOL=meshcore` | MeshCore radio + channel sync |
| `MESHCORE_UPLOAD_ENABLED=true` | POST sync (and packets); otherwise capture-only |
| `STORAGE_API_ROOT` / `STORAGE_API_TOKEN` | Primary API; WebSocket unless `MESHFLOW_WS_URL` set |
| `STORAGE_API_2_ROOT` / `STORAGE_API_2_TOKEN` | Optional second POST target for sync + ingest |
| `MESHCORE_SERIAL_DEVICE` or `MESHCORE_BLE_ADDRESS` | Companion transport |

Full list: [meshflow-bot `docs/MESHCORE.md`](https://github.com/pskillen/meshflow-bot/blob/main/docs/MESHCORE.md).

---

## Dual API (`STORAGE_API_2_*`)

When the bot uploads to two API bases:

| Traffic | Primary (`STORAGE_API_ROOT`) | Secondary (`STORAGE_API_2_ROOT`) |
|---------|------------------------------|----------------------------------|
| `mc-channel-sync` | Yes | Yes (same snapshot after connect / apply) |
| WebSocket / `apply_mc_channel_config` | Yes | No (unless `MESHFLOW_WS_URL` points at secondary) |
| UI apply against secondary only | — | **503** — bot not on that deployment’s WS groups |

Operators should use one deployment for UI + bot WS, or accept mirror-only updates on the secondary.

---

## Horizontal scaling (API + bot)

| Component | Requirement |
|-----------|-------------|
| API workers | `channels_redis` on Redis DB 0 ([`docs/REDIS.md`](../../../REDIS.md)) |
| Bot | Single WebSocket per feeder; any ASGI instance that shares Redis |
| Presence check | `feeder_ws_group_has_subscribers` probes Redis ZSET for `asgi:group:node_mc_{uuid}` |

In-memory channel layer (tests only) breaks apply from real workers.

---

## Troubleshooting

### Apply returns 503 `feeder_bot_not_connected`

| Cause | What to check |
|-------|----------------|
| Bot not running or WS down | Bot logs: `MeshflowWSClient: connected` |
| UI and bot on different API hosts | Align `MESHFLOW_API_URL` (UI) with bot `STORAGE_API_ROOT` |
| Redis mismatch | Same `REDIS_HOST` / DB 0 as pre-prod when mixing local + remote |
| Wrong feeder | `mc_pubkey` on `ManagedNode` matches device; WS URL includes correct 12-hex prefix |

### Apply returns 503 `command_dispatch_unavailable`

Channel layer or Redis error during `group_send`. Check API logs and Redis connectivity.

### Sync succeeds but UI mirror empty

| Cause | What to check |
|-------|----------------|
| Device has no named channels | Bot warning: zero channels from `get_channel` scan |
| Wrong feeder prefix | 403 on sync if prefix does not match `mc_pubkey` |
| Empty snapshot accepted | Reconcile with `channels: []` clears all links |

### API catalog differs from radio

Expected until next successful sync from device. **Device wins** on sync. Edit via apply-to-radio, not by changing canonical rows alone in admin (admin catalog edits do not push automatically).

### Placeholder `MC channel N` in messages

Ingest arrived before first sync for that slot. Run bot connect or fix device config and re-sync.

---

## Verification checklist

1. Bot log: `POST /api/meshcore/feeders/{prefix}/mc-channel-sync/` with channel count.
2. `ManagedNode.mc_channels_synced_at` updated in admin or `GET /api/nodes/managed-nodes/mine/`.
3. Nested `mc_channels` on managed node matches device slot order and names.
4. After apply: bot log shows `set_channel` then second sync POST.
5. `channel_message` ingest: `MeshCoreTextPacket.channel` FK resolves to expected canonical row.

---

## Known gaps

| Gap | Notes |
|-----|--------|
| Per-channel **region scope** in sync payload | Planned [#391](https://github.com/pskillen/meshflow-api/issues/391); companion `GET_CHANNEL` does not return scope today |
| API-only mirror edits | No REST to patch mirror without device; use apply or wait for connect sync |
| Empty device channel table | Ops: configure channels on companion or via MeshCore app first |
| `region_scope` / transport code on ingest | Out of scope for channel sync; wire observation ≠ feeder config |

Track execution debt in phase/outstanding docs only when discovered during delivery — not duplicated here.

---

## Related

- [flow.md](flow.md)
- [feeder-bootstrap.md](../feeder-bootstrap.md)
- [API keys & WebSocket](../../../API_KEYS.md)
