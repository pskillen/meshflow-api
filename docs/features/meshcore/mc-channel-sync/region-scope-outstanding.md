# MeshCore region scope — outstanding

Items **skipped**, **incomplete**, or **discovered during execution** for [#391](https://github.com/pskillen/meshflow-api/issues/391) — not the plan backlog.

**Tracking:** [region-scope-progress.md](./region-scope-progress.md)

---

## Protocol / device

- [ ] **Active investigation:** [bug-channel-scope-read-write.md](./bug-channel-scope-read-write.md) — bot apply does not leave per-channel scopes on device ([meshflow-bot#129](https://github.com/pskillen/meshflow-bot/issues/129))
- [ ] Per-channel `region_scope` in companion `CHANNEL_INFO` — not on wire today; bot may sync `null` until meshcore_py/firmware expose it
- [ ] Apply path: confirm whether `set_flood_scope` is per-channel or global on hardware (spike on real feeder) — see bug log verification checklist
- [x] Bot merges `region_scope` from apply payload into post-apply sync (CHANNEL_INFO does not return scope)
- [ ] Per-channel scope in `CHANNEL_INFO` / extended `SET_CHANNEL` — firmware still name+secret only; active scope is `set_flood_scope` (global) per slot during apply
