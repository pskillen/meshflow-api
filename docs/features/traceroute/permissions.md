# Traceroute Permissions

Delta on the global model in **[permissions/README.md](../../permissions/README.md)**.
If this file or OpenAPI drifts from code, update until they agree.

## Principles

1. **Visibility is public (guest read).** Anyone may browse the traceroute list,
   detail, and heatmap endpoints without login.
2. **Triggering requires feeder or admin.** A user must be in the **`feeder`**
   group or be Django staff. They may trigger from any **eligible** `ManagedNode`
   (not only nodes they own).
3. **A source node must be capable of sourcing a traceroute.** It must have
   `allow_auto_traceroute=True` and must have been recently seen reporting
   packets (i.e. the bot behind it is online). Nodes that are offline or have
   opted out are excluded from the triggerable set.
4. **Rate limits are enforced at the API, not at the UI.** The Meshtastic radio
   firmware only tolerates one traceroute every ~30 seconds. The API enforces
   the same minimum interval per source node and returns a 429 when exceeded.
5. **The API is always authoritative.** UI clients may hide affordances when the
   user cannot trigger, but a client-side check is never a substitute for the
   server's answer. Any trigger request is re-validated end-to-end.

## Roles and who may trigger

| Role | Read | Trigger |
|------|------|---------|
| Guest | yes | no |
| User (JWT, not feeder) | yes | no |
| Feeder | yes | yes, from any eligible source |
| Admin (`is_staff`) | yes | yes, from any eligible source |

"Eligibility" for a source node means:

- `allow_auto_traceroute=True`, and
- `ManagedNodeStatus.is_sending_data` is true (feeder snapshot; refreshed from packet observations) — see
  `eligible_auto_traceroute_sources_queryset` in
  [`Meshflow/traceroute/source_eligibility.py`](../../../Meshflow/traceroute/source_eligibility.py)
  and its canonical definition in `nodes.managed_node_liveness`.

## Endpoints

| Endpoint                              | Method | Permission                                                                                                                             |
| ------------------------------------- | ------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| `/api/traceroutes/`                   | GET    | Guest or authenticated.                                                                                                                |
| `/api/traceroutes/<pk>/`              | GET    | Guest or authenticated.                                                                                                                |
| `/api/traceroutes/trigger/`           | POST   | Feeder or admin; passes `CanTriggerTraceroute` and per-node checks (see below).                                                        |
| `/api/traceroutes/can_trigger/`       | GET    | Authenticated. `true` for feeder/admin when eligible sources exist.                                                                    |
| `/api/traceroutes/triggerable-nodes/` | GET    | Authenticated feeder/admin only (empty for plain users).                                                                               |
| `/api/traceroutes/heatmap-edges/`     | GET    | Guest or authenticated.                                                                                                                |

### Payload: `POST /api/traceroutes/trigger/`

```json
{
  "managed_node_id": 123456789,
  "target_node_id": 987654321
}
```

- `managed_node_id` (required): `ManagedNode.node_id` of the source.
- `target_node_id` (optional): `ObservedNode.node_id` of the target. When
  omitted, the server picks a target via
  `pick_traceroute_target(source_node)`.

### Checks performed on POST (in order)

1. **Authentication** – `IsAuthenticated`.
2. **`CanTriggerTraceroute` (DRF permission)** – the user must have at least
   one `ManagedNode` with `allow_auto_traceroute=True` that they own or are
   admin/editor on. Recent-ingestion is deliberately not checked here, so
   clients get a clearer error in step 4 rather than a generic 403.
3. **Source node exists** – otherwise `404`.
4. **`allow_auto_traceroute`** on the chosen node – otherwise `400`.
5. **Eligibility** – the source must have recent ingestion via
   `is_managed_node_eligible_traceroute_source`. Otherwise `400` with a message
   pointing the user at the offline monitor.
6. **Rate limit** – enforced with `MANUAL_TRIGGER_MIN_INTERVAL_SEC`. Returns
   `429` with a `Try again in Ns` hint.
7. **Per-node permission** – `user_can_trigger_from_node(user, source_node)`
   re-validates the user/constellation relationship. Otherwise `403`.
8. **Target** – if `target_node_id` is given, it must resolve to an
   `ObservedNode`; otherwise `pick_traceroute_target` chooses one, and if it
   cannot, the API returns `400` asking for `target_node_id`.

## Triggerable nodes endpoint

`GET /api/traceroutes/triggerable-nodes/` is the canonical data source for UI
clients. The response is the intersection of:

- **Eligible sources** (`allow_auto_traceroute=True` and recently heard), and
- **Permission** (staff, owner, or constellation admin/editor).

When this list is empty, the UI should hide all trigger affordances. The
payload includes `short_name` / `long_name` (from the node's `ObservedNode`
counterpart) and a `position` object so the UI can label and place each source
on a map without a second round trip. `position` uses the latest observed
`NodeLatestStatus` if available, otherwise falls back to the `ManagedNode`'s
configured `default_location_*`; either coordinate may be `null` if no
location has ever been recorded.

## Client expectations

- Any client may hide trigger buttons when
  `GET /api/traceroutes/triggerable-nodes/` returns an empty array (or when
  `GET /api/traceroutes/can_trigger/` returns `false`).
- No client should assume a successful trigger based only on the UI state: the
  API owns the final answer (ownership, rate limit, eligibility, target
  resolution) and any of these checks can fail.
- For pages that "trigger to a fixed target" (e.g. Node Details), only the
  source picker needs to be shown; the `target_node_id` is set to the node
  being viewed. Permissions and rate limits are unchanged.

## Related code

- [`Meshflow/traceroute/views.py`](../../../Meshflow/traceroute/views.py) –
  `traceroute_list`, `traceroute_trigger`, `traceroute_can_trigger`,
  `traceroute_triggerable_nodes`.
- [`Meshflow/traceroute/permissions.py`](../../../Meshflow/traceroute/permissions.py) –
  `CanTriggerTraceroute` DRF permission.
- [`Meshflow/traceroute/permission_helpers.py`](../../../Meshflow/traceroute/permission_helpers.py) –
  `user_can_trigger_from_node`, `get_nodes_permitted_for_trigger_queryset`,
  `get_triggerable_nodes_queryset`.
- [`Meshflow/traceroute/source_eligibility.py`](../../../Meshflow/traceroute/source_eligibility.py) –
  eligibility helper (re-exports the canonical
  `nodes.managed_node_liveness` functions).
- [`Meshflow/traceroute/trigger_intervals.py`](../../../Meshflow/traceroute/trigger_intervals.py) –
  `MANUAL_TRIGGER_MIN_INTERVAL_SEC`.
