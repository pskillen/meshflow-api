# Managed Nodes

A managed node is a user-operated Meshtastic radio that feeds packets into Meshflow through bot software. Managed nodes are tied to a constellation and are used for packet ingestion, maps, traceroutes, statistics, and monitoring workflows.

## Preconditions

Normal user onboarding requires:

- An authenticated Meshflow user.
- An `ObservedNode` for the radio.
- An accepted ownership claim on that observed node.
- A constellation where the managed node will operate.
- A `NodeAPIKey` associated with the managed node through `NodeAuth`.

## Convert Owned Node to Managed

The normal frontend flow is:

1. The user opens their claimed nodes.
2. The user chooses "Convert to managed" for an owned node.
3. The frontend calls `POST /api/nodes/managed-nodes/`.
4. The API creates a `ManagedNode` owned by the current user.
5. The user chooses or creates a `NodeAPIKey`.
6. The API key is associated with the managed node through `NodeAuth`.
7. The user configures the bot with that API key.
8. The bot starts sending packets to packet ingestion endpoints.

The managed-node row does not replace the observed-node row. Both records can exist for the same Meshtastic `node_id`. The observed node continues to represent what the mesh hears. The managed node represents Meshflow's administrative and ingestion relationship with a feeder.

## API Key Association

`NodeAPIKey` belongs to a user and can authorize one or more managed nodes through `NodeAuth` rows. Removing one managed node must not deactivate the API key if the key is still used by other managed nodes.

Packet ingestion uses:

- `NodeAPIKeyAuthentication` to authenticate the API key.
- `NodeAuthorizationPermission` to confirm the key is associated with the managed node named in the request path.

When soft-delete support is added, authorization must also reject deleted managed nodes as a defense-in-depth guard, even if a stale `NodeAuth` row exists.

## Permissions

Managed-node creation is a user action for owned nodes. Current onboarding has a known permission gap: claiming a node adds the user to the constellation as a viewer, but viewer membership is not enough for all managed-node setup steps, especially API-key creation and assignment. This is tracked separately in meshtastic-bot-ui issue #205.

Managed-node mutation and removal permissions are:

- The managed-node owner can update or remove their managed node.
- Django staff can remove a managed node to protect the system.
- Constellation admins are not system admins for managed-node removal.
- Removing managed-node status does not unclaim the observed node.

## Node number changes (2.8)

A Meshtastic 2.8 feeder's node number is the `crc32` of its public key, so it changes on a firmware upgrade or re-key. On v4 feeder URLs the API re-points the feeder's `ManagedNode.meshtastic_node_id` (same row, same history) when the feeder reports the new number with a public key that proves it, and records a `ManagedNodeIdentityEvent` either way (applied, or flagged with a reason). Anything unprovable (no key, a key that does not match, a key shared with other nodes, a number already taken) is flagged and left alone, and ingest is never affected. It is behind `MESHTASTIC_FEEDER_AUTO_REKEY`; the decision table is in [Meshtastic packet ingestion](../packet-ingestion/meshtastic.md#feeder-number-change-auto-re-key).

### What the owner sees

- **Automatic change** (`auto_updated`): a Discord DM, if the owner has a verified Discord target (see [Discord notifications](../discord/notifications.md)): "Your feeder <name> changed node number: !old is now !new. It keeps its history and API key. Nothing to do." Without a verified target the DM is skipped and an audit row says so.
- **Flagged change** (`flagged`): a DM naming the reason ("Your feeder <name> reported node number !new but is stored as !old, and it could not be updated automatically (<reason>). Ingest continues. Open My Nodes to review it."). When the reason is `auto_rekey_disabled`, the text says automatic updates are off on this server. A repeat of the same flagged change writes no new event, so there is one DM per event.
- `manual` and `key_changed` events are never sent as a DM; `key_changed` is an audit row only.
- A failed DM never affects the re-key.

`GET /api/nodes/managed-node-identity-events/` lists the events for the caller's own feeders (staff see all), newest first. `?unacknowledged=true` hides acknowledged events and `key_changed`; `?managed_node=<internal_id>` filters to one feeder. `needs_action` is true for a flagged event that has not been resolved. `POST /api/nodes/managed-node-identity-events/{id}/acknowledge/` records who saw it and when; calling it again changes nothing.

### Re-pointing a feeder by hand

For a flagged feeder, the owner (or staff) calls `POST /api/nodes/managed-nodes/{internal_id}/repoint-meshtastic-id/`. The body `{"meshtastic_node_id": <int>}` is optional; the default is the number the feeder last reported. It works whether or not `MESHTASTIC_FEEDER_AUTO_REKEY` is on, because a person is deciding. The feeder keeps its row, history and API key; the number is updated, the public key is taken from the open flagged event when that event reported the same number, a `manual` event is written (acknowledged by the caller) and open flagged events are resolved. Passing the old number reverses a re-key.

Refusals: 400 `{"code": "not_meshtastic" | "no_reported_number" | "invalid_node_id" | "already_current"}`, 409 `{"code": "number_collision"}` when another active feeder has that number, 403 for anyone but the owner or staff.

## Deleted Managed Nodes

When a managed node is removed, the row should be soft-deleted rather than hard-deleted so historical references remain intact. A soft-deleted managed node should not appear in normal managed-node lists, maps, traceroute source selection, statistics, or monitoring views.

If a user tries to convert the same observed node to managed while a soft-deleted `ManagedNode` row already exists, the API should block the request. The UI should explain that the node was previously removed from managed service and must be re-enabled by a system admin.

Admin undeletion is intentionally a separate follow-up feature tracked by meshtastic-bot-ui issue #229.
