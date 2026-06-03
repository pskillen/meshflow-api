# MeshCore region scope — outstanding

Items **skipped**, **incomplete**, or **discovered during execution** for [#391](https://github.com/pskillen/meshflow-api/issues/391) — not the plan backlog.

**Tracking:** [region-scope-progress.md](./region-scope-progress.md)

---

## Protocol / device

- [ ] Per-channel `region_scope` in companion `CHANNEL_INFO` — not on wire today; bot may sync `null` until meshcore_py/firmware expose it
- [ ] Apply path: confirm whether `set_flood_scope` is per-channel or global on hardware (spike on real feeder)
- [x] `meshcore` 2.3.x in bot venv has no `commands.set_flood_scope` — apply logs DEBUG and skips until a newer meshcore_py release
