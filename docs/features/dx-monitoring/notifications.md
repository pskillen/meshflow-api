# DX monitoring: opt-in Discord notifications

Users can opt in to Meshflow **Discord direct messages** when DX events match selected categories. Delivery uses the same verified Discord target as other Meshflow DMs (see user settings / Discord resync) and the shared `DiscordNotificationAudit` trail (`push_notifications`).

## Eligibility

- The user must have a **linked Discord account** and `discord_notify_user_id` / `discord_notify_verified_at` in sync with a Discord `SocialAccount` (see `users.discord_sync.user_has_verified_discord_dm_target`).
- The self-service API returns `discord.status`: `verified`, `not_linked`, or `needs_relink`.
- Enabling the subscription in the API (`enabled: true`) is rejected with `NEEDS_DISCORD_VERIFICATION` if DMs are not verified.

## Categories (stable strings)

- **new_distant_node** – destination outside the observing constellation cluster footprint.
- **returned_dx_node** – node reappears after a configured quiet period with prior DX history.
- **distant_observation** – direct (single-hop) observation with large observer–destination distance.
- **traceroute_distant_hop** – distant hop seen on a completed traceroute path.
- **confirmed_event** – `DxEvent.observation_count` reaches `DX_MONITORING_NOTIFICATION_CONFIRMED_MIN_OBSERVATIONS` (not emitted when that threshold is below 2).
- **event_closed_summary** – optional DM when a `DxEvent` transitions to `state=closed` (e.g. staff or future automation).

Subscription can use **all categories** (`all_categories: true`) or a granular allow-list. There is no separate `all` category value: “receive everything” is the `all_categories` flag.

## Rollout and kill switch

- **`DX_MONITORING_NOTIFICATIONS_ENABLED`** (default `false`) must be on for enqueued deliveries and for hooks that schedule `notify_dx_event` (new event, evidence threshold, closed). Detection (`DX_MONITORING_DETECTION_ENABLED`) remains independent.

## Anti-spam

- **Idempotency:** at most one `DxNotificationDelivery` row per `(event, user, category)`; repeats are dropped without a new send.
- **Per-user per-category cool-down** across *different* events: `DX_MONITORING_NOTIFICATION_CATEGORY_COOLDOWN_MINUTES` (0 disables). Skips are recorded in `DiscordNotificationAudit` with status `skipped`.
- **Message size:** text is built to stay within Discord’s 2000 character limit (truncated if needed).

## Non-goals (current)

- **Constellation-scoped** subscriptions: deferred; the model can be extended later.
- A separate DX-only delivery log beyond `DxNotificationDelivery` and `DiscordNotificationAudit`: not used.

## API

- `GET` / `PUT` / `PATCH` **`/api/dx/notifications/settings/`** (authenticated)
  - `GET` returns `enabled`, `all_categories`, `categories`, and `discord` readiness.
  - `PUT` replaces the three fields; `PATCH` merges with existing data.

Celery task: **`dx_monitoring.tasks.notify_dx_event`** (event UUID string + category string).
