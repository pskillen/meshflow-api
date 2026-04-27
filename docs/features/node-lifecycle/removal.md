# Node Lifecycle Removal

Meshflow supports two separate removal concepts:

- Unclaiming an observed node.
- Unmanaging a managed node.

These actions are deliberately separate. A user may stop operating a feeder without giving up ownership of the underlying radio, and a user may release ownership of a radio that was never used as a feeder.

## Unclaiming an Observed Node

Unclaiming releases ownership of an `ObservedNode`.

Expected behavior:

- Only the current claim owner can unclaim through the REST API.
- Pending claims are deleted.
- Accepted claims are deleted and `ObservedNode.claimed_by` is cleared when it points at the current user.
- Django staff do not get a REST shortcut to unclaim someone else's node.
- The observed-node row remains in place.
- Packet ingestion can continue to update the observed node if the radio is still active.

Unclaiming is for cases like a radio being sold, destroyed, repurposed, or otherwise no longer owned by the user.

## Unmanaging a Managed Node

Unmanaging removes the feeder role from a `ManagedNode` while preserving historical references.

Expected behavior:

- The managed-node owner can unmanage the node.
- Django staff can unmanage the node to protect the system.
- Constellation admins cannot unmanage nodes unless they are also the managed-node owner or Django staff.
- The `ManagedNode` row is soft-deleted, for example by setting `deleted_at`.
- The matching `ObservedNode` is not deleted.
- `ObservedNode.claimed_by` is not cleared.
- `NodeAuth` rows for the managed node are removed.
- The associated `NodeAPIKey` is not deactivated, because it may be used by other managed nodes.

Soft-deleted managed nodes should be excluded from normal operational surfaces, including:

- Managed-node list and detail APIs.
- The current user's managed-node list.
- Maps and constellation geometry.
- Traceroute source selection.
- DX monitoring and feeder statistics.
- Managed-node liveness tasks.
- Text-message observer lookups.

## Ingestion After Unmanage

Removing `NodeAuth` rows should stop normal API-key authorization for the unmanaged node. The API should also reject ingestion or upsert attempts for deleted managed nodes if a stale `NodeAuth` association somehow remains.

This keeps API keys reusable for other managed nodes while preventing a removed feeder from continuing to submit packets under its old managed-node identity.

## Re-Managing a Deleted Managed Node

The normal "Convert to managed" flow must not silently recreate or reactivate a soft-deleted managed node.

If a user attempts to create a managed node and a deleted `ManagedNode` already exists for that `node_id`, the API should reject the request with a clear error. The UI should warn the user that this node was previously removed from managed service and cannot be managed again through the normal UI. The user should contact a system admin to re-enable management.

This prevents accidental resurrection of removed feeders and leaves a deliberate audit point for system recovery.

## Future Undeletion

Admin undeletion is out of scope for the initial removal work and is tracked by meshtastic-bot-ui issue #229.

The follow-up should allow a system admin to:

- View soft-deleted managed nodes in an admin UI.
- Clear the deleted flag with confirmation.
- Leave observed-node ownership unchanged.
- Require deliberate API-key reassociation through existing key-management flows.

After undeletion, the node owner should be able to manage the node again through the usual managed-node UI.

## Observed Node Retention

Neither unclaiming nor unmanaging deletes the `ObservedNode`.

If the radio remains active, future packets keep it visible and up to date. If the radio stops transmitting, it naturally disappears from recent-node feeds as its `last_heard` timestamp ages out of those views.
