# MeshCore passive packet path — progress

**Tracking:** [meshflow-api#267](https://github.com/pskillen/meshflow-api/issues/267) (MeshCore Phase 3 path parity epic)
**Plan:** Cursor plan `MC passive path M1` (detailed M1) + `MC packet path milestones` (overview) + [ADR-0001](adr/0001-meshcore-packet-path-tracing-subsystem.md)
**Repos:** meshflow-api (primary), meshflow-bot, meshflow-ui

---

## Overall status

**Status:** M1 PRs open (pending merge / deploy). **Tier-1 message path twin** merged ([#390](https://github.com/pskillen/meshflow-api/pull/390)). **Tier-2 heard resolution** implemented in open PRs ([#395](https://github.com/pskillen/meshflow-api/pull/395), [ui#322](https://github.com/pskillen/meshflow-ui/pull/322)) — deploy API first, then UI.

**Branches (in flight):**

| Slice | meshflow-api | meshflow-bot | meshflow-ui |
| --- | --- | --- | --- |
| M1 passive path | `api-372/pskillen/meshcore-passive-path-m1` | (see bot PR) | (see ui PR) |
| Tier-2 heard map | `api-311/pskillen/mc-heard-path-resolution` | — | `ui-311/pskillen/mc-heard-path-map` |

**PRs:** [api#378](https://github.com/pskillen/meshflow-api/pull/378) · [bot#122](https://github.com/pskillen/meshflow-bot/pull/122) · [ui#310](https://github.com/pskillen/meshflow-ui/pull/310) (M1) · [api#390](https://github.com/pskillen/meshflow-api/pull/390) (tier-1, **merged**) · [api#395](https://github.com/pskillen/meshflow-api/pull/395) · [ui#322](https://github.com/pskillen/meshflow-ui/pull/322) (tier-2)

The display-only passive slice that precedes this subsystem has **shipped** (see Precursor below). M1 implementation is complete in branch; awaiting merge and deploy.

**Locked decisions (ADR-0001 open questions):**

- App name: `meshcore_packet_path`.
- Neo4j: new `PATH_OBSERVED` relationship type (separate from `ROUTED_TO`).
- Retention: 6 months; every persisting milestone ships a Celery eviction job.
- Open until M2 spike: meaning of `path_hash_mode`; centrality in Postgres vs Neo4j.

---

## Precursor — display-only passive slice (shipped)

**Status:** Complete

| Issue | Repo | Delivered |
| --- | --- | --- |
| [#369](https://github.com/pskillen/meshflow-api/issues/369) | api | `path_hashes` moved to `MeshCorePacketObservation` only; `update_or_create` per `(packet, observer)` |
| [#360](https://github.com/pskillen/meshflow-api/issues/360) | api | Message `heard[]` exposes `path_hashes`, display-only `resolved_path` (`status=unknown`), `path_known=false` |
| [#119](https://github.com/pskillen/meshflow-bot/issues/119) | bot | `_path_hashes()` forwards segments on ingest |
| [#304](https://github.com/pskillen/meshflow-ui/issues/304) | ui | `HeardPathMap` + heard dialog renders hops/feeders |

These provide the raw capture (`MeshCorePacketObservation.path_hashes`) and read-time formatter (`meshcore_packets/services/path_resolution.py`) the new subsystem builds on.

---

## Milestones

Tracked as sub-issues of [#267](https://github.com/pskillen/meshflow-api/issues/267); see [ADR-0001](adr/0001-meshcore-packet-path-tracing-subsystem.md) for scope. This file records what ships; do not duplicate milestone detail here.

| Milestone | Issue | Status |
| --- | --- | --- |
| M1 MVP (capture + resolution table + hourly rollup + eviction + edges/segments API + diagnostic UI) | [#372](https://github.com/pskillen/meshflow-api/issues/372) | Complete (pending deploy) |
| M2 resolution spike (decision gate) | [#373](https://github.com/pskillen/meshflow-api/issues/373) | Not started |
| M3 proactive resolver (conditional on M2) | [#374](https://github.com/pskillen/meshflow-api/issues/374) | Not started |
| M4 Neo4j `PATH_OBSERVED` export | [#375](https://github.com/pskillen/meshflow-api/issues/375) | Not started |
| M5 realtime WS + recent API | [#376](https://github.com/pskillen/meshflow-api/issues/376) | Not started |
| M6 history / centrality API | [#377](https://github.com/pskillen/meshflow-api/issues/377) | Not started |
| M7 UI realtime + history/topology | [meshflow-ui#309](https://github.com/pskillen/meshflow-ui/issues/309) | Not started |

**M1 scope note.** M1 was expanded to also ship a read/annotate API (`/meshcore/path-tracing/segments/` with staff manual annotation) and a **diagnostic UI MVP** (data tables, not the M7 map) so the user has enough visibility into captured passive data to make informed M2 decisions. M1 therefore spans all three repos. The full topology/realtime UI remains M7 (meshflow-ui#309).

---

## M1 — delivered (pending PR merge / deploy)

**PRs:** [api#378](https://github.com/pskillen/meshflow-api/pull/378) · [bot#122](https://github.com/pskillen/meshflow-bot/pull/122) · [ui#310](https://github.com/pskillen/meshflow-ui/pull/310)

**Branch:** `api-372/pskillen/meshcore-passive-path-m1`

**API**

- `meshcore_packet_path` app: segment resolution + edge bucket models, hourly rollup, 6-month eviction, backfill command.
- `GET /api/meshcore/path-tracing/edges/`, `GET/PATCH .../segments/`.
- `path_hash_size` / `path_hash_mode` on `MeshCorePacketObservation`.

**Bot**

- Forwards `path_hash_size` and `path_hash_mode` on ingest envelopes.

**UI**

- Diagnostic preview page (meshflow-ui; see ui PR).

**Deploy / verify**

- Run migrations and `run_deploy_tasks`; confirm Celery beat rows `collect_path_edge_buckets` and `evict_old_path_data`.
- `python manage.py backfill_path_edge_buckets --days 7`
- Hit edges/segments APIs; open Passive Path (preview) in UI.

---

## Tier-1 — message path twin (merged)

**PR:** [api#390](https://github.com/pskillen/meshflow-api/pull/390) · Design: [tier-1-message-path-twin.md](./tier-1-message-path-twin.md)

- Thin bot uploads TEXT_MSG/PATH `rx_log_data`; API `path_twin.py` copies `path_hashes` onto `channel_text` observations within `MESHCORE_DECODED_TWIN_WINDOW_SECONDS` (120s).
- Pre-prod: works when in-window twin exists; most channel texts still have empty path — see [bug-no-path-info.md](./bug-no-path-info.md).

---

## Tier-2 — heard map resolution (PRs open, Jun 2026)

**PRs:** [api#395](https://github.com/pskillen/meshflow-api/pull/395) · [ui#322](https://github.com/pskillen/meshflow-ui/pull/322) · UI issue [#311](https://github.com/pskillen/meshflow-ui/issues/311)  
**Design:** [tier-2-heard-resolution.md](./tier-2-heard-resolution.md) (behaviour); matcher addendum in [traceroute ADR-0001](../../traceroute/adr/0001-mc-path-hash-resolution.md).

**API (#395)**

- `heard[]` includes `path_hash_mode`, `path_hash_size`; `resolved_path` from `MeshCorePathSegmentResolution` + guarded pubkey-suffix auto-matcher (`candidates[]` on ambiguity).
- `bulk_format_path_hops` cache keyed by `(hash_mode, hash_size, segment_hash)`.
- Tests: `meshcore_packets/tests/test_path_resolution.py`, `text_messages/tests/test_heard_api.py`.

**UI (#322)**

- `HeardPathMap`: logical dashed hop chain per feeder ([#311](https://github.com/pskillen/meshflow-ui/issues/311)).
- `HeardPathGeoMap`: geographic polylines when hop positions exist; partial segments when only some hops resolve.
- `HopPositionIcon` / `PathHopBadge`: known vs unknown position; ambiguity tooltips.
- Component docs: `meshflow-ui` `HeardPathMap.md`, `HeardPathGeoMap.md`, `docs/meshcore/heard-path-dialog.md`.

**Pre-prod spot-check (2026-06-04):** `☘️GI7ULG☘️: Test` has `path_hashes` but segments stay `unknown`; sender shows as unknown in heard dialog while channel list links one candidate — no `NodeLatestStatus` on sender node. See [bug-no-path-info.md](./bug-no-path-info.md).

**Deploy / verify**

- Merge and deploy API #395 before UI #322.
- Open message heard dialog on a row with merged `path_hashes`; confirm hash chain, optional geo lines when positions exist.
- `pytest Meshflow/meshcore_packets/tests/test_path_resolution.py Meshflow/text_messages/tests/test_heard_api.py -v`

---

## Next

- Merge M1 PRs ([#378](https://github.com/pskillen/meshflow-api/pull/378), [#122](https://github.com/pskillen/meshflow-bot/pull/122), [#310](https://github.com/pskillen/meshflow-ui/pull/310)) and deploy.
- Merge tier-2 PRs ([#395](https://github.com/pskillen/meshflow-api/pull/395), [ui#322](https://github.com/pskillen/meshflow-ui/pull/322)); deploy API before UI.
- Re-run pre-prod path-on-text metrics after tier-1 is live on all feeders ([bug-no-path-info.md](./bug-no-path-info.md) checklist).
- Begin M2 resolution spike ([#373](https://github.com/pskillen/meshflow-api/issues/373)) using the diagnostic UI.
- Align heard-dialog sender with channel list when one `mc_sender_candidate` exists without position (outstanding).
