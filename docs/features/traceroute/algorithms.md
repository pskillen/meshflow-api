# Traceroute selection algorithms

This document describes the design of Meshflow automatic traceroute **source** selection, **strategy** rotation, and **target** selection, including automatic reliability signals. Implementation lives under `Meshflow/traceroute/`.

See also [Environment variables](../../ENV_VARS.md) §11 for tunables.

---

## Scheduler flow

On each automatic scheduling tick the system:

1. Orders **eligible managed sources** (feeders) with a pluggable policy.
2. For each source in order, tries **target strategies** from least-recently-used to oldest.
3. For the first strategy that yields a target, creates an `AutoTraceRoute` and sends the command.
4. If no hypothesis strategy finds a target, falls back to **legacy** target selection.

Manual, **node watch**, external, and **DX watch** traceroutes are out of scope for automatic reliability: only `trigger_type=3` (**Monitoring**) terminal rows inform cooldowns and soft penalties.

---

## Source selection

**Intent:** choose which managed node should originate the next automatic traceroute.

**Inputs:** `allow_auto_traceroute`, managed-node liveness (recent ingestion), usable position, and `AutoTraceRoute` history for ordering.

### Shared eligibility

A source must be live, allowed for auto traceroute, and have coordinates (default location or linked observed position) so geographic target strategies can run.

### Algorithms

| Name | Behaviour | Trade-off |
|------|-----------|-----------|
| **Random** | Shuffle eligible sources. | Simple; no fairness. |
| **Least recently used (LRU)** | Prefer the source whose last `AutoTraceRoute` is oldest; never-used first. | Fair across feeders; dense constellations with many feeders get more total share. |
| **Stratified LRU** | Order constellations by oldest cluster-wide activity, then LRU within each. | Fairer across regions; more complex. |

Environment: `AUTO_TR_SOURCE_SELECTION_ALGO` (`least_recently_used`, `random`, `stratified_lru`).

---

## Strategy rotation

**Intent:** rotate which geographic “question” each feeder tests: intra-zone, DX across, DX same side.

**Mechanism:** Redis-backed least-recently-used per `(feeder, strategy)` with a stable tie order. A strategy is recorded as run only when a traceroute is actually created.

**Applicable strategies:** `intra_zone` requires a constellation envelope. Without it, only `dx_across` and `dx_same_side` apply. `legacy` is not part of rotation; it is a fallback from `pick_traceroute_target`.

---

## Target selection

**Intent:** pick an `ObservedNode` target that matches the strategy’s geometry and is not a poor use of scheduler budget given recent automatic outcomes.

**Shared pipeline:**

1. Build the **base pool:** recently heard, positioned, not the source, not any managed infrastructure `node_id`, not mesh-monitoring suppressed.
2. Apply **strategy geometry** (legacy distance bias, intra envelope, DX bearing window).
3. Compute **strategy score** (e.g. distance for legacy, median distance for intra).
4. Subtract **recency demerit** (same source→target traced recently).
5. Subtract **reliability soft penalty** from recent automatic completed/failed history.
6. **Hard-exclude** targets in automatic cooldown (consecutive automatic failures).
7. Sort, take the top *N*, then **deterministic pick** from that shortlist (stable, avoids always picking rank 1).

### Strategies

- **Legacy:** Prefer more distant candidates (periphery bias), minus recency and reliability.
- **Intra zone:** Only targets inside the constellation envelope; prefer distances near the **median** distance from the source to in-envelope nodes (avoids always picking the hub or a single outlier).
- **DX across / same side:** Only outside the envelope; filter by **bearing** from the constellation centroid (opposite side vs same side as the source). **Widens** the bearing window in steps until some candidates exist. If geometry is unavailable, falls back to legacy-style scoring for that attempt.

### Automatic reliability

**Evidence:** `AutoTraceRoute` rows with `trigger_type=3` (Monitoring) and `status` in `completed` or `failed` within a configurable lookback window. User, node watch, external, and DX watch triggers are ignored for suppression.

**Per source–target pair:**

- **Soft penalty:** `TR_RELIABILITY_SOFT_MAX * (failed / attempts)` when `attempts >= TR_RELIABILITY_MIN_ATTEMPTS_SOFT`, using the same ordered history. Reduces score without removing the target.
- **Hard cooldown:** if the most recent automatic attempts, newest first, are **consecutive failures** and the run length is at least `TR_RELIABILITY_CONSECUTIVE_FAILS`, the target is excluded for this source until a success occurs or the window/attempt pattern changes. A more recent `completed` row in the same window breaks the streak (only trailing failures count).

Tunables: `TR_RELIABILITY_ENABLED`, `TR_RELIABILITY_WINDOW_DAYS`, `TR_RELIABILITY_CONSECUTIVE_FAILS`, `TR_RELIABILITY_SOFT_MAX`, `TR_RELIABILITY_MIN_ATTEMPTS_SOFT` (see [ENV_VARS.md](../../ENV_VARS.md)).

**Design note:** the first version scopes signals to the **source–target** pair. A global per-target penalty across all feeders is reserved for a future iteration if needed.

---

## Non-goals

- Replacing **manual** target choice.
- Suppressing **monitoring** / watch-list verification traceroutes via the same automatic reliability rules.
- Using coverage API aggregates as the scheduler’s primary state; selection reads `AutoTraceRoute` directly.
