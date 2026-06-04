# Bug: MeshCore channel text often has no path in heard / DB

**Status:** Investigating (pre-prod verified 2026-06-03)  
**Tracking:** [meshflow-api#385](https://github.com/pskillen/meshflow-api/issues/385) (Tier 1 twin), epic [#267](https://github.com/pskillen/meshflow-api/issues/267)  
**Related:** [packet-path-tracing-outstanding.md](./packet-path-tracing-outstanding.md), [tier-1-message-path-twin.md](./tier-1-message-path-twin.md)

## Symptom

MeshCore public / hashtag **text messages are stored**, but **>90%** show **no hop path** in the UI “Heard” map and in API `heard[]` (`path_hashes` empty on the `original_mc_packet` observation).

Operators expect path hashes to ride with (or immediately follow) the same on-air message.

## Prior agent / design context

| Source | What we already knew |
| --- | --- |
| [packet-path-tracing-outstanding.md](./packet-path-tracing-outstanding.md) § Message path data chain | `channel_message` decode has `path_len` / mode but usually **no `path` hex**; path on wire is often on **`rx_log_data` PATH/TEXT_MSG**; bot historically uploaded **ADVERT only**. |
| [tier-1-message-path-twin.md](./tier-1-message-path-twin.md) | **Shipped approach:** thin bot uploads TEXT_MSG/PATH `rx_log_data`; API **twin-merge** copies `path_hashes` onto `channel_text` within **120s** (`MESHCORE_DECODED_TWIN_WINDOW_SECONDS`). |
| PR [#390](https://github.com/pskillen/meshflow-api/pull/390) (`api-388`) | Implemented `path_twin.py`, `path_hashes` ingest, heard tests — merged to `main`. |
| Agent [meta workspace consolidation](c074c495-8f39-4d1d-b755-e81567cd29ad) | Confirmed tier-1 docs on `main`; branch `api-388/pskillen/mc-path-twin-and-resolution`. |

**Conclusion from this session:** Tier-1 **code path works when a PATH/TEXT_MSG twin exists in-window**; pre-prod failure rate is dominated by **missing or mis-timed rx_log twins**, not broken heard assembly.

## Pre-prod sample messages (2026-06-03)

Compared four `TextMessage` rows (`protocol = MeshCore`) on the single feeder:

| Message text (substring) | `sent_at` (UTC) | `path_hashes` on text packet obs | `rx_log` twin in ±120s |
| --- | --- | --- | --- |
| `GM1DSV: Or is it Blazing Saddles??` | 07:59:12 | **Yes** `['e1317c','4cd741','f3bcf1']` | **PATH** @ 07:58:48 (−24s) |
| `Rogue Two: Beans 🤦‍♂️` | 07:59:59 | **Yes** (same path) | **PATH** @ 07:58:48 (−71s) |
| `Rogue Two: 😂` | 07:50:48 | **No** | **None** |
| `MCEK 4: @[Rogue Two]: Lol` | 07:50:58 | **No** | **None** |

**7-day aggregate (pre-prod):** 22 / 533 MeshCore `TextMessage` rows with `path_hashes` length ≥ 2 → **4.1%** success rate (hourly buckets 0–33%).

### Same 20-minute window (07:45–08:05 UTC)

| Ingest type | Count |
| --- | --- |
| `channel_text` packets | 8 |
| `rx_log_data` **PATH** or **TEXT_MSG** (`payload_type=raw`) | **2** (one TEXT_MSG @ 07:47:28, one PATH @ 07:58:48) |

So most channel messages **never get a correlatable PATH/TEXT_MSG upload** on that feeder in the twin window.

### Extra detail on the lone TEXT_MSG @ 07:47:28

- Observation has **8** path segments (path was captured on the raw row).
- Stored `raw_json` has **no `text`** and **no `channel_idx`** → API content-key match to `channel_text` **cannot run** (`_content_key_for_raw` returns `None`).
- `channel_text` for `Rogue Two: 😂` is **200s later** → **outside** the 120s twin window anyway.

## Root cause (current hypothesis)

```text
channel_message → channel_text → TextMessage.original_mc_packet
                                      ↓
heard[] reads obs.path_hashes on THAT packet only

PATH/TEXT_MSG rx_log_data (separate upload) ──twin merge (120s, same feeder)──► copy path onto channel_text obs
```

Failures are **not** because:

- Heard API ignores path (covered by `text_messages/tests/test_heard_api.py` + tier-1 tests).
- `channel_text` rows never arrive.

Failures **are** because:

1. **Sparse PATH/TEXT_MSG capture** — bot uploads those typenames, but pre-prod shows ~2 raw path frames vs 8 channel texts in 20 minutes (radio/library may not emit `rx_log_data` for every message, or frames are dropped before upload).
2. **Twin window** — default **120s**; PATH for the success pair arrived 24–71s **before** text; the 07:47 TEXT_MSG was **200s** before the 07:50 failures.
3. **Weak correlation keys on TEXT_MSG raw** — no text / channel_idx in uploaded envelope → merge falls back to time/channel heuristics or skips when ambiguous.

`channel_message` payloads still typically lack inline `path` hex (see outstanding doc); twin merge is the intended production path.

## Code pointers

| Layer | Location |
| --- | --- |
| Bot upload filter | `meshflow-bot` `src/meshcore/serializers.py` — `TEXT_MSG` / `PATH` → `payload_type: raw` |
| Twin merge | `Meshflow/meshcore_packets/services/path_twin.py` |
| Ingest hook | `Meshflow/meshcore_packets/serializers.py` `_run_path_twin_sync` |
| Heard output | `Meshflow/text_messages/serializers.py` |

## Open questions / next steps

- [ ] **Feeder / bot:** confirm MeshCore build emits `rx_log_data` PATH (or TEXT_MSG with path) for *every* channel message the feeder hears; compare with on-disk `data/meshcore_packets/` dumps for fail vs success times.
- [ ] **Correlation:** can `pkt_hash` (or wire dedup fields) link PATH to `channel_text` more reliably than time + optional text? (ADR-0004 / #276)
- [ ] **TEXT_MSG envelope:** ensure bot forwards `channel_idx` + decoded text (if present on wire) so content-key twin matching works when multiple messages fall in one window.
- [ ] **Window / ordering:** measure distribution of Δ(rx_time) between PATH and `channel_text` on pre-prod; consider bounded async merge (e.g. delayed job) if PATH often follows text by >120s.
- [ ] **Metrics:** add pre-prod-friendly counts: `channel_text` with/without merged path per day; `raw` PATH/TEXT_MSG per day — re-run queries after bot/deploy changes.

## Investigation log

| Date | Action | Result |
| --- | --- | --- |
| 2026-06-03 | Pre-prod DB via Django + `Meshflow/ai-env` | Sample table + 4.1% / 7d rate; fail cases = no in-window PATH twin |
| 2026-06-03 | This doc created | Baseline for continued debugging |
