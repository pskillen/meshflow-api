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

## Deleted Managed Nodes

When a managed node is removed, the row should be soft-deleted rather than hard-deleted so historical references remain intact. A soft-deleted managed node should not appear in normal managed-node lists, maps, traceroute source selection, statistics, or monitoring views.

If a user tries to convert the same observed node to managed while a soft-deleted `ManagedNode` row already exists, the API should block the request. The UI should explain that the node was previously removed from managed service and must be re-enabled by a system admin.

Admin undeletion is intentionally a separate follow-up feature tracked by meshtastic-bot-ui issue #229.
