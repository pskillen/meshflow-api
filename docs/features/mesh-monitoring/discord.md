# Mesh monitoring and Discord

[Mesh monitoring](README.md) can notify users when a **watched** node is **confirmed offline** after a verification round (traceroutes + deadline).

## Behaviour

- **Who gets a DM:** Users with an **enabled** **`NodeWatch`** on that **`ObservedNode`**, who also have **verified** Discord notification settings (same anti-spam rules as the test endpoint).
- **Deduping:** If one user has multiple watches on the same node, they should still receive at most **one** alert per offline event (per product design).
- **Transport:** Server-side **`push_notifications.discord.send_dm`** — no duplicate Discord REST client inside **`mesh_monitoring`**.

## Documentation

- **Prefs, verification, test API, bot setup:** [Discord notifications](../discord/notifications.md)
- **Linking Discord vs logging in with Discord:** [Discord account linking](../discord/account-linking.md) and [Discord overview](../discord/README.md)
