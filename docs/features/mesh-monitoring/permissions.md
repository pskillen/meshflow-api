# Mesh monitoring — permissions

Who may **subscribe** to alerts (create a **`NodeWatch`**) vs who may change the **node-level silence threshold** (**`NodePresence.offline_after`**) are different. Rules align with the [Mesh Monitoring epic](https://github.com/pskillen/meshflow-api/issues/147) and phase **04** watch APIs.

Implementation lives in:

- **`mesh_monitoring.eligibility.user_can_watch`** — create/update/delete watches (validated on **`NodeWatch.save()`** and in **`NodeWatchSerializer`**).
- **`mesh_monitoring.permission_helpers.user_can_edit_monitoring_offline_after`** — **`GET/PATCH …/offline-after/`** (PATCH returns **403** when not allowed).

---

## Who may create or keep a watch on an observed node?

A user may create a **`NodeWatch`** only if **either**:

1. **Claim owner:** the user is **`observed_node.claimed_by`** (they have claimed that observed node), or  
2. **Infrastructure node:** the observed node’s **`role`** is one of **`nodes.constants.INFRASTRUCTURE_ROLES`** (e.g. routers / repeaters — shared infrastructure on the map that anyone eligible to use the app may watch).

Everyone else gets validation errors on create (and **`NodeWatch.clean()`** rejects ineligible pairs).

**Notes**

- Watches are **per user × observed node** (unique constraint). Each user opts in individually.
- **Discord** delivery still requires a **verified** Discord binding for that user; that is separate from watch eligibility (see [Discord notifications](../discord/notifications.md)).

---

## Who may read or change the silence threshold (`offline_after`)?

**`offline_after`** is stored on **`NodePresence`** (one value per observed node). It controls how long **`last_heard`** may be stale before a **verification traceroute** round may start.

| Action | Who |
|--------|-----|
| **GET** `…/monitoring/nodes/{internal_id}/offline-after/` | Any **authenticated** user. Response includes **`offline_after`** and **`editable`** (whether this user may PATCH). |
| **PATCH** same URL | **Django staff** (`user.is_staff`, “system admin” / admin-site staff) **or** the **claim owner** (`observed_node.claimed_by == user`). **403** otherwise. |

**Not** eligible to PATCH:

- Users who only have a **watch** on an **infrastructure** node but are not staff (infrastructure nodes are often **unclaimed**; threshold is staff-only until product adds e.g. constellation-admin rules).
- Other authenticated users with no claim and not staff.

---

## Watch API vs offline-after API

| Endpoint | Auth | Extra rules |
|----------|------|----------------|
| **`/api/monitoring/watches/`** (CRUD) | Authenticated | Create: **`user_can_watch`**. List/detail/update/delete: only the **owning** user’s watches. |
| **`/api/monitoring/nodes/{id}/offline-after/`** | Authenticated | PATCH: **`user_can_edit_monitoring_offline_after`**. |

---

## UI expectations

- **Watch toggles** (add / enable / remove): only where the user is allowed to watch (same rules as API).
- **Silence threshold editing**: treat as an **admin-style** control — expose only to users who would receive **`editable: true`** from GET (claim owner or staff); others may still **see** the current value when useful for context.

For background on the wider epic (verification TRs, Discord), see the epic issue and [README.md](README.md).
