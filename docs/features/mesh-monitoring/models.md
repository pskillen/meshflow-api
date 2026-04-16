# Mesh monitoring — models and fields

Django app: **`meshflow.Meshflow.mesh_monitoring`**. These models support **silence detection**, **verification traceroutes**, **confirmed offline**, and **Discord** notifications. Runtime behaviour is driven mainly by Celery **`process_node_watch_presence`** and hooks from **`packets`** / **`traceroute`**; see [flow.md](flow.md) for sequences.

---

## `NodeWatch`

A user opt-in to monitor one **`ObservedNode`**. Several watches can point at the same node; the periodic task uses the **minimum** `offline_after` among enabled watches as the effective silence threshold.

| Field | Type | Meaning |
|-------|------|---------|
| **`user`** | FK → `users.User` | Watcher who receives notifications when eligible. |
| **`observed_node`** | FK → `nodes.ObservedNode` | Node being monitored. Unique per `(user, observed_node)`. |
| **`offline_after`** | positive int (seconds) | How long **`ObservedNode.last_heard`** may be stale before verification may start. Default **7200** (2 hours). |
| **`enabled`** | bool | When `False`, this watch does not contribute to thresholds or notifications. |
| **`created_at`** | datetime | Auto-set when the row is created. |

**Validation:** On save, **`clean()`** ensures the user may watch that node (**claimed** node or **infrastructure** role); see `mesh_monitoring.eligibility.user_can_watch`.

---

## `NodePresence`

One row per observed node that participates in mesh monitoring (created lazily when a watched node is processed). Primary key is **`observed_node_id`** (same UUID as **`ObservedNode.internal_id`**); reverse relation from observed node: **`observed_node.mesh_presence`**.

State is split into: **episode / observability** (current verification round), **confirmed offline** (deadline expired), and **summary flags** for operators.

### Core state

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

### Operator-friendly summary

| Field | Type | Meaning |
|-------|------|---------|
| **`is_offline`** | bool | **`True`** when mesh monitoring has **confirmed** the node offline (set together with **`offline_confirmed_at`**). **`False`** when idle, verifying, or after recovery. Mirrors “are we in the offline_confirmed state?” for simple admin and queries. |
| **`observed_online_at`** | datetime, null | Last time monitoring recorded the node as **online** for this purpose: **(1)** row **created** while the node was **not silent**, or **(2)** recovery after **confirmed** offline (periodic task sees fresh `last_heard`, or packet path clears presence after offline). Not updated on every successful verification alone if the node was never confirmed offline. |

---

## How fields move together (short)

- **Silence → new episode:** `verification_started_at`, `suspected_offline_at` set; episode counters reset; monitoring **`AutoTraceRoute`** rows created; **`send_monitoring_traceroute_command`** updates **`last_tr_sent`** / **`tr_sent_count`**.
- **Verification succeeds:** `verification_started_at` cleared; episode fields (`suspected_offline_at`, `last_tr_sent`, `last_zero_sources_at`, `tr_sent_count`) cleared; **`is_offline`** / **`offline_confirmed_at`** unchanged (still false / null).
- **Verification deadline fails:** `offline_confirmed_at` set, **`is_offline=True`**, `verification_started_at` cleared; Discord notify.
- **Node heard again (not silent or packet hook):** verification and offline timestamps cleared; episode fields cleared; **`is_offline=False`**; **`observed_online_at`** set if recovering from confirmed offline.

For diagrams and component names, see [flow.md](flow.md) and [README.md](README.md).
