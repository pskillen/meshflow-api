# Mesh monitoring and Discord

[Mesh monitoring](README.md) can notify users when a **watched** node is **confirmed offline** after a verification round (traceroutes + deadline), and when **verification starts** (monitoring traceroutes are being dispatched) unless disabled by env.

## Behaviour

- **Who gets a DM:** Users with an **enabled** **`NodeWatch`** on that **`ObservedNode`**, who also have **verified** Discord notification settings (same anti-spam rules as the test endpoint).
- **Deduping:** If one user has multiple watches on the same node, they should still receive at most **one** alert per offline event (per product design).
- **Transport:** Server-side **`push_notifications.discord.send_dm`** — no duplicate Discord REST client inside **`mesh_monitoring`**.

## Verification-start DMs (#165)

When mesh monitoring **first enters** a new verification episode (silence exceeded threshold, **`verification_started_at`** set, monitoring round dispatched), the API sends a Discord DM to the same watcher audience **before** offline is confirmed (unless turned off below). This helps with aggressive **`offline_after`** values or flap debugging (you see that RF verification has started, even if **`_dispatch_monitoring_round`** finds no sources).

| Control | Details |
|---------|---------|
| **Feature flag** | **`MESH_MONITORING_NOTIFY_VERIFICATION_START`** — **default on** when the variable is **unset**. Set to `0`, `false`, `no`, `off`, or empty to disable. When set to enable explicitly, truthy values are `1`, `true`, `yes`, `on` (case-insensitive). |
| **Cooldown** | **`MESH_MONITORING_VERIFICATION_NOTIFY_COOLDOWN_SECONDS`** (default **3600** = 1 hour). If **`NodePresence.last_verification_notify_at`** is set and the last notify is newer than this window, another verification-start DM is **not** sent for the next episode start. |
| **State** | **`last_verification_notify_at`** is updated only when at least one **`send_dm`** was **attempted** (same semantics as offline notify). Cleared when the node is **heard again** (packet hook **`clear_presence_on_packet_from_node`** or periodic **not silent** path) so recovery resets the cooldown anchor. |
| **Message** | Explains that RF verification (monitoring traceroutes) has started, includes **`node_id_str`**, **`long_name`**, and the effective silence threshold in seconds. |
| **Deep link** | If **`FRONTEND_URL`** is non-empty (see Django settings), the message appends **`{FRONTEND_URL}/nodes/{node_id}`** (decimal **`ObservedNode.node_id`**, consistent with the UI node route). |

Implementation: **`mesh_monitoring.services.notify_watchers_verification_started`**, wired from **`process_node_watch_presence`** / **`_process_one_observed_node`** only on **new** verification (not on every tick while already verifying). See [models.md](models.md) for **`NodePresence.last_verification_notify_at`**.

## Documentation

- **Prefs, verification, test API, bot setup:** [Discord notifications](../discord/notifications.md)
- **Linking Discord vs logging in with Discord:** [Discord account linking](../discord/account-linking.md) and [Discord overview](../discord/README.md)
