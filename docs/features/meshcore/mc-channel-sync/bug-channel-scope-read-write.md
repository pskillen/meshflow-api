# Bug: Scoped MC channels not persisted on physical radio

**Status:** Investigating  
**Tracking:** [meshflow-bot#129](https://github.com/pskillen/meshflow-bot/issues/129)  
**Related:** [region-scope.md](./region-scope.md), [region-scope-outstanding.md](./region-scope-outstanding.md), [#391](https://github.com/pskillen/meshflow-api/issues/391)

## Symptom

Operator configures **multiple MeshCore channels with distinct `region_scope` values** in Meshflow (UI or admin), pushes config to the feeder via the bot (**apply to radio** / admin **Push MC channel config**).

After apply:

1. Disconnect the radio from the bot (USB).
2. Connect the same device to the **MeshCore Android companion** over USB.
3. In companion channel settings, the radio shows **only one scope** configured (e.g. `sco`, default) and **every channel slot uses that default scope** — not the per-channel scopes from Meshflow.

Meshflow API / UI mirror may still show the intended scopes (bot merges scope from apply payload into `mc-channel-sync` when `CHANNEL_INFO` omits scope). **The failure is on the device**, not only in API bookkeeping.

## Expected vs observed

| Layer | Expected (operator) | Observed |
| --- | --- | --- |
| Meshflow catalog / mirror | Each canonical channel has its `region_scope` | OK (when apply + sync path runs) |
| Companion per-channel scope | Each slot has the scope assigned in Meshflow | All slots show **default** scope |
| Companion global / flood scope list | Scopes used on device exist | Only **one** scope (e.g. default) |
| Bot connect sync (`get_channel`) | Readback reflects per-slot scope where Android shows it | **Names only**; all `region_scope` null on wire → API mirror loses scope |

## Current bot apply path (code)

**Entry:** WebSocket `apply_mc_channel_config` → `MeshflowBot.on_apply_mc_channel_config` → `apply_device_channels` (`meshflow-bot/src/meshcore/channels.py`).

For each snapshot row:

1. **`set_channel(mc_channel_idx, name)`** — writes **channel name only** (hashtag gets `#` prefix). **No `region_scope` argument** on this call.
2. **`set_flood_scope(scope_arg)`** — called immediately after each successful `set_channel`. `scope_arg` is the row’s `region_scope` or `"*"` when null (`_apply_active_flood_scope`).

Documented limitation ([region-scope.md](./region-scope.md)): `set_flood_scope` sets the companion **active flood scope** (global operator scope for sending), **not** a per-slot field returned by `CHANNEL_INFO`. The apply loop therefore calls `set_flood_scope` once per row; **only the last row’s scope remains active** on the radio until the operator changes channel in the app.

**Read path:** `get_channel` / `CHANNEL_INFO` returns **name + secret only** (no per-channel scope). Post-apply sync uses `merge_channel_region_scopes(..., scope_hints=applied_channels)` so the **API** snapshot includes intent scopes without reading them from firmware.

## Hypotheses (ranked)

| # | Hypothesis | If true |
| --- | --- | --- |
| H1 | **No wire API used for per-channel scope on SET_CHANNEL** — bot only sets names; firmware stores per-slot scope via a different command we do not call | Android per-slot UI stays default; fix needs meshcore_py + bot change |
| H2 | **`set_flood_scope` is global only** — it does not write per-channel scope into NVS; Android “per channel scope” is a separate setting | Explains one global scope + all channels default in slot UI |
| H3 | **`set_flood_scope` missing or failing** on feeder (`meshcore.commands.set_flood_scope` absent or ERROR) | Bot logs WARNING; device never leaves default scope |
| H4 | **Wrong scope value on wire** — normalization, `*` for null, or ordering (scope before `set_channel`) | Check apply logs and payload hex |
| H5 | **Firmware / companion version** — older build ignores scope writes | Repro depends on device firmware; compare with manual scope set in Android |
| H6 | **Scopes must exist in companion region list before per-channel bind** — `set_flood_scope` only sets active TX key; Android lists regions separately | `ioi`/`gla` never registered; all slots show default `sco` |
| H7 | **Apply is partial** — only listed slots written; stale slots 4–8 remain | Duplicate `#glasgow` in slots 3 and 6 after 5-channel push → [meshflow-bot#130](https://github.com/pskillen/meshflow-bot/issues/130) |

## Verification checklist

- [x] **Bot logs during apply** (docker / local): search for  
  `set_flood_scope unavailable`, `set_flood_scope(%r) failed`, `active flood scope=`, `set_channel(%s) failed`
- [ ] **Apply payload** — confirm each WS/API entry includes `region_scope` (`message_channel_to_apply_entry` in `Meshflow/common/mc_channel_labels.py`)
- [ ] **`meshcore` package version** on feeder (`requirements.txt` currently `>=2.3.7,<3.0.0`) and whether `Commands.set_flood_scope` exists
- [ ] **meshcore_py / firmware docs** — command to set **per-channel** region scope vs `CMD_SET_FLOOD_SCOPE`
- [x] **After apply, before unplug** — bot `log_device_channels` lines (scope from **scope_hints**, not device truth)
- [x] **Android companion** — manual slot scope on device; bot read does not see it (see investigation log 2026-06-04 connect read)
- [x] **API mirror after connect sync** — Admin UI: channels created, **no** `region_scope` (confirms read path → reconcile gap)
- [ ] **Optional:** serial trace or meshcore_py REPL `get_channel(i)` raw payload after apply

## Investigation log

| Date | Who | Action / result |
| --- | --- | --- |
| 2026-06-04 | Operator | Reported repro: apply scoped channels via bot → unplug → Android USB → one scope (`sco`/default), all channels default scope. |
| 2026-06-04 | Agent | Documented apply path (`set_channel` + `set_flood_scope` only); aligned with [region-scope-outstanding.md](./region-scope-outstanding.md) open item “confirm per-channel vs global on hardware”. **No device trace yet.** |
| 2026-06-04 | Agent | Filed [meshflow-bot#129](https://github.com/pskillen/meshflow-bot/issues/129). |
| 2026-06-04 | Operator | **Android 1.44.0, firmware 1.15.0.** Apply 5 channels: Public→`sco`, #scotland→`sco`, #norniron→`ioi`, #glasgow→`gla`, #test→null. Bot logs: `set_flood_scope` OK for slots 0–3 (no INFO line for null scope on #test). Post-apply sync shows scopes 0–3 from **scope_hints** only; slots 4–8 unchanged on device (`test` at 4, duplicate `#glasgow` at 3+6). Android after storage clear: **no scopes in node list**; **all channels default `sco`**. Confirms H2/H3 rejected (commands succeed); supports H6 (regions `ioi`/`gla` not on device list; `set_flood_scope` ≠ per-channel bind). |
| 2026-06-04 | Operator | **Connect read (no apply).** Configured on Android only: `#test-gla` (explicit **gla**), `#test-sco` and `#test-unset` (both unset in UI → default **sco**). USB to bot → connect sync logged 3 channels, **all** `region_scope=(none)`. **Admin UI:** three canonical channels created correctly, **none** have `region_scope`. Confirms `CHANNEL_INFO` / `get_channel` cannot read per-slot scope; connect sync cannot distinguish gla vs default-sco; API mirror is misled unless `enrich_snapshot_region_scope` matches prior links by name only. Strengthens H1/H2. |

## Fixes to apply

Tracked work to reduce confusion while the protocol gap ([#129](https://github.com/pskillen/meshflow-bot/issues/129)) is resolved.

| Item | Repo | Description |
| --- | --- | --- |
| [meshflow-bot#130](https://github.com/pskillen/meshflow-bot/issues/130) | meshflow-bot | **Clear unlisted channel slots** when applying MC channel config so stale slots (duplicate hashtags, old names) are removed from the device. |
| Apply verify logging | meshflow-bot | On **apply** (`apply_device_channels` or caller): (1) log **desired** config from the apply payload (per `mc_channel_idx`: name, type, `region_scope`). (2) **Read back** from device via `read_device_channels` **without** `scope_hints`. (3) log **readback** config with clear labels (`DESIRED` vs `READBACK`). (4) **WARNING** on mismatch (slot index, name, and `region_scope` when present on read path). Expect scope mismatches until firmware exposes scope in `CHANNEL_INFO`; names/indices should match after #130 + scope fix. |

## Next steps

1. ~~Capture **one full apply** log line set~~ — done (see investigation log 2026-06-04 operator).
2. Spike **meshcore_py + firmware 1.15**: `set_default_flood_scope` (registers default + auto-creates region per [default-scope blog](https://blog.meshcore.io/2026/04/17/default-scope)) vs command for **per-channel** scope bind (Android issue [#1575](https://github.com/meshcore-dev/MeshCore/issues/1575): region must be created then activated per channel in app).
3. ~~Decide whether apply should **clear unlisted slots**~~ → [meshflow-bot#130](https://github.com/pskillen/meshflow-bot/issues/130).
4. If only global scope exists today, update [region-scope.md](./region-scope.md) operator docs and UI copy so we do not imply per-slot persistence until firmware supports it.
5. ~~File tracking issue~~ → [meshflow-bot#129](https://github.com/pskillen/meshflow-bot/issues/129).
6. Implement **apply verify logging** (see [Fixes to apply](#fixes-to-apply)) to stop treating post-apply `scope_hints` merge as device truth.

## Related code

| Repo | Path |
| --- | --- |
| meshflow-bot | `src/meshcore/channels.py` — `apply_device_channels`, `_apply_active_flood_scope`, `read_device_channels` |
| meshflow-bot | `src/bot.py` — `on_apply_mc_channel_config`, `scope_hints` on post-apply sync |
| meshflow-api | `Meshflow/meshcore_packets/services/channel_apply.py` — `build_apply_channels_for_managed_node` |
| meshflow-api | `Meshflow/common/mc_channel_labels.py` — `message_channel_to_apply_entry` (`region_scope` in payload) |

**External:** [Region filtering](https://blog.meshcore.io/2026/01/20/region-filtering) · [Default scope](https://blog.meshcore.io/2026/04/17/default-scope)
