# Mesh monitoring — models and fields

Django app: **`meshflow.Meshflow.mesh_monitoring`**. These models support **silence detection**, **verification traceroutes**, **confirmed offline**, optional **battery alerts**, and **Discord** notifications. Runtime behaviour is driven mainly by Celery **`process_node_watch_presence`**, the **`device_metrics_recorded`** signal path from **`packets`**, and hooks from **`packets`** / **`traceroute`**; see [flow.md](flow.md) for sequences.

---

## `NodeWatch`

A user opt-in to monitor one **`ObservedNode`**. Several watches can point at the same node; silence timing and battery alert **settings** are **not** per watch — see **`NodeMonitoringConfig`**. Per-watch flags control **which Discord notifications** this user wants.

| Field | Type | Meaning |
|-------|------|---------|
| **`user`** | FK → `users.User` | Watcher who receives notifications when eligible. |
| **`observed_node`** | FK → `nodes.ObservedNode` | Node being monitored. Unique per `(user, observed_node)`. |
| **`enabled`** | bool | When `False`, this watch does not contribute to monitoring ticks or notifications. |
| **`offline_notifications_enabled`** | bool | When `True` with **`enabled`**, user receives offline / verification-start Discord notifications (subject to Discord verification). |
| **`battery_notifications_enabled`** | bool | When `True` with **`enabled`**, user receives low-battery Discord notifications when a battery episode is confirmed (subject to **`NodeMonitoringConfig`** and Discord verification). |
| **`created_at`** | datetime | Auto-set when the row is created. |

**Validation:** On save, **`clean()`** ensures the user may watch that node (**claimed** node or **infrastructure** role); see `mesh_monitoring.eligibility.user_can_watch`.

---

## `NodeMonitoringConfig`

One row per observed node (**primary key = `observed_node`**). Durable **settings** only: silence threshold and battery alert parameters. Created lazily when a watch is created or when the config API is used.

| Field | Type | Meaning |
|-------|------|---------|
| **`observed_node`** | OneToOne → `ObservedNode` (PK) | The node this config describes. |
| **`last_heard_offline_after_seconds`** | positive int | How long **`ObservedNode.last_heard`** may be stale before verification may start. Default **21600** (6 hours). |
| **`battery_alert_enabled`** | bool | When `False`, battery evaluation is a no-op for this node (default). |
| **`battery_alert_threshold_percent`** | int | Low-battery threshold (5–80). |
| **`battery_alert_report_count`** | int | Consecutive below-threshold reports required to confirm an episode (1–10). |
| **`created_at` / `updated_at`** | datetime | Book-keeping. |

**Who may PATCH:** staff or claim owner; see [permissions.md](permissions.md).

---

## `NodePresence`

One row per observed node that participates in mesh monitoring (created lazily when a watched node is processed, or when the config API is used). Primary key is **`observed_node_id`** (same UUID as **`ObservedNode.internal_id`**); reverse relation: **`observed_node.mesh_presence`**.

State is **runtime only**: verification / offline episode, operator summary flags, and **battery alert episode** counters.

### Offline / verification core

| Field | Type | Meaning |
|-------|------|---------|
| **`observed_node`** | OneToOne → `ObservedNode` (PK) | The node this row describes. |
| **`verification_started_at`** | datetime, null | When the **current** verification window started (monitoring TR round). Null when not verifying. |
| **`offline_confirmed_at`** | datetime, null | When the node was **confirmed offline** after the verification window passed without reachability proof. Cleared when the node is heard again. |

### Episode observability (current verification only)

These fields describe the **active** silence → TR episode. They are cleared when verification **succeeds** (reachability) or when the node is **not silent** (fresh `last_heard`), or via **`clear_presence_on_packet_from_node`**.

| Field | Type | Meaning |
|-------|------|---------|
| **`suspected_offline_at`** | datetime, null | When the current episode began: first tick where silence triggered a new verification round (typically equals **`verification_started_at`** for that episode). |
| **`last_tr_sent`** | datetime, null | Last time a **monitoring** traceroute command was sent to the mesh for this target (Celery after **`AutoTraceRoute`** → SENT). |
| **`tr_sent_count`** | int | Number of monitoring TR sends in the **current** episode; reset with the other episode fields. |
| **`last_zero_sources_at`** | datetime, null | Last time **`select_monitoring_sources`** returned no eligible managed sources, so no TR could be dispatched for that round. |

### Operator-friendly summary (offline)

| Field | Type | Meaning |
|-------|------|---------|
| **`is_offline`** | bool | **`True`** when mesh monitoring has **confirmed** the node offline (set together with **`offline_confirmed_at`**). **`False`** when idle, verifying, or after recovery. |
| **`observed_online_at`** | datetime, null | Last time monitoring recorded the node as **online** for this purpose: **(1)** row **created** while the node was **not silent**, or **(2)** recovery after **confirmed** offline. |
| **`last_verification_notify_at`** | datetime, null | When a **verification-start** Discord DM was last attempted (see [discord.md](discord.md)). Cleared with other presence state when the node is heard again. |

### Battery alert episode (runtime)

| Field | Type | Meaning |
|-------|------|---------|
| **`battery_below_threshold_report_count`** | int | Consecutive below-threshold **`DeviceMetrics`** readings in the current streak. |
| **`battery_alerting_since`** | datetime, null | First below-threshold reading time in the current streak. |
| **`battery_alert_confirmed_at`** | datetime, null | When the episode reached **N** consecutive low readings; used for UI and one-shot Discord notify. |
| **`last_battery_alert_notify_at`** | datetime, null | When the low-battery Discord DM was last recorded for this episode. |
| **`last_battery_recovered_at`** | datetime, null | When battery last recovered above threshold. |

---

## How fields move together (short)

- **Silence → new episode:** `verification_started_at`, `suspected_offline_at` set; episode counters reset; monitoring **`AutoTraceRoute`** rows created; **`send_monitoring_traceroute_command`** updates **`last_tr_sent`** / **`tr_sent_count`**.
- **Verification succeeds:** `verification_started_at` cleared; episode fields cleared; **`is_offline`** / **`offline_confirmed_at`** unchanged (still false / null).
- **Verification deadline fails:** `offline_confirmed_at` set, **`is_offline=True`**, `verification_started_at` cleared; Discord notify (offline channel opt-in).
- **Node heard again (not silent or packet hook):** verification and offline timestamps cleared; episode fields cleared; **`is_offline=False`**; **`observed_online_at`** set if recovering from confirmed offline.
- **Battery low streak → episode:** increments **`battery_below_threshold_report_count`**; on reaching **N**, sets **`battery_alert_confirmed_at`** and sends battery DM once (battery channel opt-in); recovery above threshold clears streak and episode timestamps.

For diagrams and component names, see [flow.md](flow.md) and [README.md](README.md).
