# MeshCore / multi-protocol — implementation plan (living document)

This file is the **single cross-repo index** for the MeshCore and related multi-protocol work. **Each epic or phase should add its own dated section** below; do not rewrite prior sections except to fix factual errors.

**Rename / relabelling track:** Sub-plans in `IdeaProjects/MeshFlow/.cursor/plans/` ([index](file:///Users/patricks/IdeaProjects/MeshFlow/.cursor/plans/meshcore-rename-index.plan.md)). GitHub: sub-epic [#307](https://github.com/pskillen/meshflow-api/issues/307) under [#266](https://github.com/pskillen/meshflow-api/issues/266). Progress: [`refactoring-progress.md`](./refactoring-progress.md).

**Convention for contributors**

- Add a new `##` section with a clear phase name, **completion date (or “in progress”)**, and **repos touched**.
- Under **Done**, list concrete deliverables (paths, env vars, PR/issue links).
- Under **Not done (this phase only)**, list what is explicitly out of scope or deferred so the next person does not guess.
- If your phase did **not** change a repo, state **“No meshflow-api / meshflow-ui / meshflow-bot changes for this phase.”**

---

## Phase 0 — Bot protocol seam (RadioInterface, Meshtastic behind adapter)

**Status:** Complete (meshflow-bot). **Tracking:** GitHub `pskillen/meshflow-bot` issue **#80**; implementation and test/CI follow-up in **PR #87** (branch `bot-80/patrick/radio-interface-refactor`).  
**Repos touched in this phase:** **meshflow-bot only** (for this agent’s delivery).

### Purpose of this phase

Introduce a **protocol-agnostic seam** so Meshtastic-specific I/O and packet shapes are not embedded in the bot core. A second radio stack (MeshCore) can attach later without rewriting command/responder logic. **No intentional behaviour change** for existing Meshtastic TCP deployments vs. the pre-refactor bot (staging/prod smoke still the authority).

### meshflow-bot — done

- **`RadioInterface`** abstract API and **`RadioHandlers`** callback bundle in `src/radio/interface.py`.
- **Domain events** in `src/radio/events.py` (`IncomingPacket`, `IncomingTextMessage`, `NodeUpdate`, `ConnectionEstablished`). Event dataclasses are **mutable** (`@dataclass` without `frozen=True`) where tests or adapters need to adjust fields.
- **Error boundaries** in `src/radio/errors.py` (`ErrorCounter`, `safe_callback`, `call_safely`) used from the bot for storage uploads and command dispatch so failures increment counters and do not kill the loop.
- **`MeshflowBot`** (`src/bot.py`) is the single protocol-agnostic core; **`MeshtasticBot`** remains a **backward-compatible alias** to `MeshflowBot`.
- **Meshtastic adapter package** under `src/meshtastic/` (e.g. `radio.py`, `translation.py`, `serializers.py`, `tcp_interface.py`, `traceroute.py`) — Meshtastic TCP + pubsub + translation live here, not in `bot.py`.
- **Entry wiring** in `src/main.py`: reads **`RADIO_PROTOCOL`** (default **`meshtastic`**), builds **`MeshtasticRadio`** + **`MeshtasticPacketSerializer`** for Meshtastic. **MeshCore** branching (`MeshCoreRadio` + serializer stub, capture-only) is implemented in **Phase 0.3** below — Phase 0 only guaranteed the seam and Meshtastic behind the adapter.
- **Tests added or updated for this seam** (pytest):
  - `test/fake_radio.py` — in-memory `RadioInterface` with `deliver_*` helpers and `MagicMock` send methods.
  - `test/radio/test_errors.py` — error counter and safe wrappers.
  - `test/meshtastic/test_translation.py`, `test/meshtastic/test_serializers.py` — Meshtastic dict → event / model translation.
  - `test/test_bot_integration.py` — `MeshflowBot` event routing through `FakeRadio` (connection, packets, node updates, DM command path, command exception swallowed + metric).
  - Command/responder tests refactored to use **`FakeRadio`** / `IncomingTextMessage` instead of mocking Meshtastic `interface` directly (see `test/__init__.py`, `test/test_setup_data.py`, and individual `test/commands/*`, `test/responders/*`).
- **Coverage gate:** `pyproject.toml` configures pytest with **`--cov=src`** and **`--cov-fail-under=70`**. Selected long-lived or device-bound modules are **omitted from coverage denominator** (documented in `pyproject.toml`): `src/main.py`, `src/ws_client.py`, `src/meshtastic/tcp_interface.py`, `src/meshtastic/traceroute.py`. CI must still run the full test command; local runs: **`pip install -r requirements.dev.txt`** then **`pytest test/`** (see `requirements.dev.txt` which pulls runtime deps via `-r requirements.txt` and adds pytest tooling).
- **CI:** `.github/workflows/unit-tests.yaml` installs **`requirements.dev.txt`**, runs pytest (picks up `pyproject.toml`), uploads **`coverage.xml`** per Python matrix version.

### meshflow-bot — not done *in this phase* (do not assume it exists)

- **Full unit coverage** of `src/meshtastic/radio.py` (and related live TCP/pubsub paths) under the coverage gate — adapter remains primarily covered by integration/smoke and omitted I/O modules as above.
- **MeshCore runtime adapter, JSON capture dumps, and `RADIO_PROTOCOL=meshcore` wiring** — delivered in **Phase 0.3** (see next section); do not look for them in pre–0.3 commits.
- **MeshCore “product” parity** with Meshtastic: no MeshCore packet pipeline into **meshflow-api** ingest (still true after Phase 0.3; upload remains Meshtastic-only until a later API epic).
- **meshflow-api** ingest schema changes, new MeshCore-specific REST routes, or persistence changes for MeshCore — **not part of this phase.**

### meshflow-api — status for this phase

**No meshflow-api code or OpenAPI changes** were made for the Phase 0 bot seam work documented here. MeshCore API work is **future phases** (other agents should append sections).

### meshflow-ui — status for this phase

**No meshflow-ui changes** for this phase.

### Verification checklist (for whoever picks up next)

1. **Bot + Meshtastic:** `RADIO_PROTOCOL=meshtastic` (or unset), `MESHTASTIC_IP` set — connect, commands, responders, and API upload behaviour match pre-refactor smoke expectations.
2. **Tests:** from meshflow-bot repo root, `pip install -r requirements.dev.txt` and `pytest test/` — must pass with **≥70%** coverage per `pyproject.toml` (after configured omits).
3. **MeshCore:** treat **[meshflow-bot `docs/MESHCORE.md`](https://github.com/pskillen/meshflow-bot/blob/main/docs/MESHCORE.md)** and **`RADIO_PROTOCOL=meshcore`** as the source of truth for **Phase 0.3 capture-only** behaviour until a later epic documents API/UI ingestion. After **Phase 0.4** lands (bot **[PR #89](https://github.com/pskillen/meshflow-bot/pull/89)**), use **`docs/meshcore_packets/README.md`** and **`MESHCORE_PACKET_FIELDS.md`** in that repo for capture ops + verified field tables; the **API-side** mirror of the field doc + trimmed samples + ADRs is **Phase 0.5** in meshflow-api (**[#276](https://github.com/pskillen/meshflow-api/issues/276)**, **[PR #289](https://github.com/pskillen/meshflow-api/pull/289)**).

---

## Phase 0.3 — MeshCore capture-only connectivity (meshflow-bot)

**Status:** Complete (meshflow-bot). **Tracking:** GitHub `pskillen/meshflow-bot` **PR #88** (branch `meshcore/phase-0/0.3-meshcore-connectivity`; merged or merge-ready per repo default).  
**Repos touched in this phase:** **meshflow-bot only** (this agent’s delivery). **meshflow-api** and **meshflow-ui** were not modified.

### Purpose of this phase

Prove **basic MeshCore connectivity** from the bot using the existing **`RadioInterface`** / **`RadioHandlers`** seam from Phase 0: connect over **USB serial** or **BLE** via [`meshcore` PyPI](https://github.com/meshcore-dev/meshcore_py), translate device events into the same **`IncomingPacket`**, **`IncomingTextMessage`**, **`NodeUpdate`**, and **`ConnectionEstablished`** shapes as Meshtastic, and **persist every captured event to JSON** under the data directory for the §0.4 field-inventory / capture campaign. **No** HTTP upload to meshflow-api, **no** new REST/OpenAPI contract, **no** WebSocket command channel for MeshCore in this phase.

### meshflow-bot — done (concrete checklist)

- **Dependency:** `meshcore>=2.3.7,<3.0.0` in repo-root `requirements.txt` (pulled by `requirements.dev.txt` for CI).
- **New package** `src/meshcore/`:
  - `radio.py` — **`MeshCoreRadio`**: dedicated **`asyncio` event loop in a `threading.Thread` daemon**; `MeshCore.create_serial(...)` or `MeshCore.create_ble(...)` with **`auto_reconnect=True`**; **`subscribe(None, ...)`** on all `EventType`s; **`await start_auto_message_fetching()`**; **`SELF_INFO`** wait (timeout 5s) to set **`local_node_id`** as `mc:<first-12-hex-of-pubkey>` (fallback `mc:unknown`); **`local_nodenum`** always **`None`**; **`ConnectionEstablished.local_nodenum`** passed as **`0`** placeholder for logging only; **`send_*`** raise **`RadioError("MeshCore send not implemented in 0.3 capture-only mode")`**; **`disconnect()`** idempotent (shutdown event + `run_coroutine_threadsafe` → `meshcore.disconnect()` + thread join); **`dispatch_meshcore_event_for_tests(event)`** for unit tests without hardware.
  - `translation.py` — **`event_to_incoming_packet`**, **`event_to_text_message`**, **`event_to_node_update`**; synthetic portnums **`MC_<ENUM_NAME>`** (e.g. `MC_CONTACT_MSG_RECV`); channel text uses placeholder **`mc:channel:<idx>:rx`** when wire has no sender pubkey.
  - `dump.py` — **`dump_meshcore_event(..., base_dir=...)`** writes **`{base_dir}/meshcore_packets/<event_type.value>/<UTC>.json`** with top-level **`"protocol": "meshcore"`**; **`MESHCORE_DUMP_ENABLED`** env (default on); skips disk for **`NO_MORE_MSGS`** and **`OK`** only (still processed in-process).
  - `serializers.py` — **`MeshCorePacketSerializer`** stub: all three `PacketSerializer` methods raise **`NotImplementedError`** (intentional guard until Phase 1.4 upload wiring).
  - `__init__.py` — exports **`MeshCoreRadio`**.
- **`src/main.py`:** **`build_radio(data_dir)`** returns **`MeshCoreRadio` + `MeshCorePacketSerializer`** when **`RADIO_PROTOCOL=meshcore`**; requires **exactly one** of **`MESHCORE_SERIAL_DEVICE`** or **`MESHCORE_BLE_ADDRESS`** (else **`RuntimeError`**); passes **`data_dir`** into the radio for dump paths; **`STORAGE_API_ROOT` / `STORAGE_API_2_ROOT`** and **`MeshflowWSClient`** are **not** attached when `RADIO_PROTOCOL=meshcore` (one-line **`logging.info`** if storage env is set but ignored).
- **`src/bot.py`:** **`dump_packet`** (Meshtastic JSON dump) runs only when **`event.raw`** is a **`dict`** containing **`"decoded"`**; MeshCore **`raw`** uses **`meshcore: True`** envelope — **no** duplicate Meshtastic-style dumps for MC.
- **Docker:** `docker-compose.yaml` — services **`meshflow-bot-meshtastic`** and **`meshflow-bot-meshcore`**, image **`ghcr.io/pskillen/meshflow-bot:latest`**, legacy **`meshtastic-bot`** service/image names removed; MC service uses **`./data-meshcore:/app/data`** and optional **`devices: /dev/ttyUSB0:/dev/ttyUSB0`**; Watchtower watches **both** service names.
- **Docs:** `docs/MESHCORE.md`, `docs/MESHTASTIC.md`; root **`README.md`** and **`AGENTS.md`** updated for dual-protocol; **`.env.example`** documents MeshCore env vars (commented).
- **Tests:** `test/meshcore/` — `test_translation.py`, `test_dump.py`, `test_radio.py`, `test_serializers.py`; full suite **`pytest test/ --doctest-modules`** must pass with **≥70%** line coverage per `pyproject.toml`.

### meshflow-bot — not done *in this phase only* (do not assume it exists)

- **Any HTTP upload** of MeshCore payloads to meshflow-api (no `StorageAPIWrapper` path for `RADIO_PROTOCOL=meshcore`; no `MeshCorePacketSerializer` implementation beyond stub).
- **`MESHCORE_UPLOAD_ENABLED`** or ingest URL wiring — **not present**; deferred to API + bot Phase 1.x work (other agents).
- **Outbound send** over MeshCore: **`send_text`**, **`send_reaction`**, **`send_traceroute`** — **not implemented** (raise **`RadioError`**).
- **TCP transport** via `MeshCore.create_tcp` — **not wired** in `main.py` / env (serial + BLE only).
- **Dedicated per-`EventType` subscriptions** as listed in an early spike doc — implementation uses a **single wildcard subscriber** plus translation filters; do not expect separate named handler files per event.
- **CI / pytest hardware tests** — no automated test spins a real serial/BLE radio; operator-led smoke remains: `RADIO_PROTOCOL=meshcore` + device env + `python -m src.main` → connection log + files under **`data/meshcore_packets/`**.

### meshflow-api — status for this phase

**No meshflow-api application code**, Django migrations, **`openapi.yaml`**, or integration-test changes for Phase 0.3. The **only** change in **this** repository from the Phase 0.3 agent pass is **this document** (`docs/features/meshcore/implementation-plan.md`) — the cross-repo index so api-tracked planning matches bot reality.

### meshflow-ui — status for this phase

**No meshflow-ui changes** for Phase 0.3.

### Verification checklist (for whoever picks up next)

1. **Branch / PR:** Confirm **PR #88** (or its merge commit) is the canonical bot delivery for Phase 0.3.
2. **Meshtastic unchanged:** `RADIO_PROTOCOL=meshtastic` (or unset) — same behaviour as post–Phase 0 bot for TCP, upload, and WS.
3. **MeshCore capture:** `RADIO_PROTOCOL=meshcore` + exactly one of `MESHCORE_SERIAL_DEVICE` / `MESHCORE_BLE_ADDRESS` — no `StorageAPIWrapper` in process; dumps appear under **`{DATA_DIR}/meshcore_packets/`** (default **`data/`** relative to cwd unless overridden); confirm **no** outbound ingest HTTP in a packet capture or proxy log during smoke.
4. **Tests:** from meshflow-bot repo root, `pytest test/ --doctest-modules` — green, coverage ≥ **70%**.

---

## Phase 0.4 — Real-world capture campaign + capture-verified field docs (meshflow-bot)

**Status:** Complete (meshflow-bot documentation + committed capture bundle). **Tracking:** GitHub `pskillen/meshflow-api` **[#275](https://github.com/pskillen/meshflow-api/issues/275)** (Phase 0.4 capture campaign); bot delivery on **`pskillen/meshflow-bot` [PR #89](https://github.com/pskillen/meshflow-bot/pull/89)** (branch **`api-275/paddy/meshcore-packet-caps`**, includes prior commit **`docs: add captured meshcore packets`** plus doc-only follow-up).  
**Repos touched in this phase (this agent):** **meshflow-bot** (captures + markdown). **meshflow-api** change in this pass: **only this file** (`docs/features/meshcore/implementation-plan.md`) unless another agent lands the API mirror in parallel.

### Purpose of this phase

Run Phase **0.3** capture-only mode against a **live** MeshCore mesh for multiple days, commit a **representative JSON dataset** for schema/ADR work, and publish **field tables verified from those files** (not from upstream prose alone). Still **no** meshflow-api ingest, **no** OpenAPI ingest routes, **no** bot upload to the API.

### meshflow-bot — done (concrete checklist)

- **Committed capture tree** under **`docs/meshcore_packets/`** (subfolders by dump category, e.g. `rx_log_data/`, `advertisement/`, `channel_messages/`, plus hand-off archive **`meshcore_packets_20260512.tar.gz`**). Counts and date span are summarized in **`docs/meshcore_packets/README.md`** (order-of-magnitude: tens of JSON files; wall-clock span **2026-05-06** through **2026-05-12** in filenames).
- **`docs/meshcore_packets/README.md`** — **Ops note:** duration, inferred geography (South Scotland / Galloway context from message content), feeder = **0.3 capture-only** bot (no API upload), **firmware/hash not present** in JSON; **inventory table** per subfolder; **one canonical example path per visible payload/event shape** for reviewers; note on **`channel_messages/`** folder vs inner **`"event_type": "channel_message"`** (treat JSON field as canonical).
- **`docs/meshcore_packets/MESHCORE_PACKET_FIELDS.md`** — Per-`event_type` / `rx_log_data` payload tables and **explicit gaps** (e.g. no `battery` / `self_info` dump files in this bundle) for follow-on **[#276](https://github.com/pskillen/meshflow-api/issues/276)** ADRs.
- **`docs/MESHCORE.md`** — New **“Phase 0.4 — capture campaign (complete)”** section with links to the above; **“Next phases”** updated to point at **0.5** (ADRs) and **1.x** (ingest/upload).

### meshflow-bot — not done *in this phase only* (this agent)

- **No code changes** to `MeshCoreRadio`, translation, dump layout, or serializers beyond what Phase **0.3** already shipped; 0.4 is **dataset + documentation**, not new I/O features.
- **No** `StorageAPIWrapper` / **`MESHCORE_UPLOAD_ENABLED`** / HTTP ingest — still deferred to Phase **1.x** (other agents).
- **No** increase in capture volume guarantees — the bundle is **what this campaign collected**, not a statistically complete inventory of every `meshcore` `EventType` (see “gaps” in `MESHCORE_PACKET_FIELDS.md`).

### meshflow-api — status for this phase (this agent)

- **Not delivered in Phase 0.4 itself:** Issue **#275** asked for API-repo mirrors; **this agent’s Phase 0.4 delivery was bot-only** (PR **#89**). No **`docs/features/packet-ingestion/MESHCORE_PACKET_FIELDS.md`**, no **`docs/packets/meshcore/`**, no ADRs in that PR.
- **Follow-on:** The API-side field doc, trimmed samples, and ADRs landed in **Phase 0.5** (meshflow-api **[#276](https://github.com/pskillen/meshflow-api/issues/276)**, **[PR #289](https://github.com/pskillen/meshflow-api/pull/289)**) — see the **Phase 0.5** section below. If you only have bot `main` through **#89**, you still need **api `main` + PR #289** (or equivalent merge) for those paths.
- **No** Django apps, migrations, **`openapi.yaml`**, or ingest endpoints for MeshCore from this agent in Phase 0.4.
- **This document** is updated so api-tracked planning reflects **bot** Phase 0.4 completion and where the API mirror actually lives (**0.5**).

### meshflow-ui — status for this phase (this agent)

**No meshflow-ui changes** for Phase 0.4.

### Verification checklist (for whoever picks up next)

1. **Bot PR:** Open **[meshflow-bot PR #89](https://github.com/pskillen/meshflow-bot/pull/89)** (or its merge commit on `main`) and confirm the three paths exist: **`docs/meshcore_packets/README.md`**, **`docs/meshcore_packets/MESHCORE_PACKET_FIELDS.md`**, updated **`docs/MESHCORE.md`**, plus the **`docs/meshcore_packets/**`** sample tree / tarball.
2. **Issue #275 acceptance:** Use the README’s **representative sample** table as the “one file per type” index; use **`MESHCORE_PACKET_FIELDS.md`** as the evidence base for **#276** ADRs (identity, channel, broadcast, dedup).
3. **API mirror (for #275 / #276):** Confirm **meshflow-api** has **Phase 0.5** merged (see below): `docs/features/packet-ingestion/MESHCORE_PACKET_FIELDS.md`, `docs/packets/meshcore/`, and `docs/features/packet-ingestion/adr/*.md`. That work is **not** in bot PR **#89**.
4. **Runtime unchanged:** `RADIO_PROTOCOL=meshcore` behaviour remains as documented in **Phase 0.3**; 0.4 does not change connection, dump filters, or upload posture.

---

## Phase 0.5 — ADRs + API-side evidence bundle (meshflow-api)

**Status:** Complete (meshflow-api **documentation only**). **Tracking:** GitHub `pskillen/meshflow-api` **[#276](https://github.com/pskillen/meshflow-api/issues/276)** (closes when PR merges); parent epic **[#264](https://github.com/pskillen/meshflow-api/issues/264)**. **Canonical delivery:** **[PR #289](https://github.com/pskillen/meshflow-api/pull/289)** on branch **`meshcore/phase-0-5/adrs`** (verify on `main` with `git log --oneline -- docs/features/packet-ingestion/adr/` if you need merge confirmation).

**Repos touched in this phase (this agent):** **meshflow-api only.** **meshflow-bot** and **meshflow-ui** had **no** commits from this agent for Phase 0.5 — the bot remains the **provenance anchor** for the full Phase 0.4 capture tree; the API repo holds a **derivative** field reference + **one JSON per shape** for ADR citations.

### Purpose of this phase

Turn Phase **0.4** capture evidence into **locked architecture decisions** (ADRs) so Phase **1** implementers can run migrations and ingest without re-opening fundamentals (identity, channels, broadcast semantics, dedup). **Explicitly out of scope:** any runtime code, database schema, OpenAPI contract, or bot upload path.

### meshflow-api — done (concrete checklist)

- **`docs/features/packet-ingestion/MESHCORE_PACKET_FIELDS.md`** — Capture-verified JSON/event field tables (derivative of **`meshflow-bot/docs/meshcore_packets/MESHCORE_PACKET_FIELDS.md`**; bot copy stays tied to the full tarball/tree).
- **`docs/packets/meshcore/README.md`** — Index table mapping each representative sample file to the capture shape (links back to bot `docs/meshcore_packets/` for full bundle).
- **`docs/packets/meshcore/`** sample JSON — One file per visible shape from the bot README’s “Representative samples” table, including subfolders (`advertisement/`, `channel_message/`, `contact_message/`, …) and top-level `rx_log_data_*.json` variants (`TEXT_MSG`, `ADVERT`, `PATH`, `REQ`, `CONTROL`).
- **`docs/features/packet-ingestion/adr/README.md`** — ADR index + lightweight section template (**Context / Decision / Consequences / Evidence**).
- **ADRs (numbered files in the same directory):**
  - **`0001-mc-node-identity.md`** — `ObservedNode.protocol`; primary **`mc_pubkey`** (64 hex), secondary **`mc_pubkey_prefix`** (12 hex, indexed); **`mc_pubkey_hash` dropped** from the earlier migration sketch (not on wire in 0.4 samples); name/position only from **`rx_log_data`** `ADVERT` decode (`adv_name`, `adv_lat`/`adv_lon` when non-zero); prefix-stub reconciliation for DM-only prefix sightings; channel text does not identify a remote node.
  - **`0002-mc-channel-modelling.md`** — `MessageChannel.protocol` + nullable **`mc_channel_idx`**; **`mc_channel_hash` deferred** (not observed); **`ManagedNode.mc_channels`** M2M instead of `channel_0..7` for MC; channel resolution `(observer, channel_idx)` → `MessageChannel` with optional auto-created placeholder name.
  - **`0003-mc-broadcast-semantics.md`** — MC broadcast = **`to_pubkey` and `to_pubkey_prefix` both NULL** (no MT-style `0xFFFFFFFF` sentinel); `route_typename` stored as descriptive metadata, **not** the broadcast indicator.
  - **`0004-mc-dedup-key.md`** — Dedup key **`(pkt_hash, rx_time window)`** from `rx_log_data.pkt_hash`; env **`MESHCORE_PACKET_DEDUP_WINDOW_MINUTES`** (default 10) documented for Phase 1 `ENV_VARS.md`; surrogate-hash fallback for events without `pkt_hash`; decoded-twin handling vs `rx_log_data` authority.
- **`docs/features/packet-ingestion/README.md`** — New **“MeshCore (Phase 0.5 — design only)”** subsection linking to `MESHCORE_PACKET_FIELDS.md`, `adr/README.md`, and `docs/packets/meshcore/`.
- **`docs/features/meshcore/implementation-plan.md`** — This section (and the Phase **0.4** API-status correction above) so the living doc matches reality.

### meshflow-api — not done *in this phase only* (do not assume it exists)

- **No** new Django app (e.g. `meshcore_packets`), **no** models, **no** migrations, **no** views/serializers/services/tests for MC ingest.
- **No** changes to **`openapi.yaml`** or **`docs/ENV_VARS.md`** — ADRs *name* future env vars (`MESHCORE_PACKET_DEDUP_WINDOW_MINUTES`, optional `MESHCORE_DECODED_TWIN_WINDOW_SECONDS` per ADR-0004); wiring them is **Phase 1**.
- **No** `POST /api/meshcore/.../ingest/` or any REST route; **no** `NodeAPIKeyAuthentication` changes; **no** integration tests under `tests/integration/` for MC.
- **No** copy of the **full** Phase 0.4 capture tree or tarball into meshflow-api — only the trimmed representative set under `docs/packets/meshcore/`.

### meshflow-bot — status for this phase (this agent)

**No meshflow-bot changes** from this agent for Phase 0.5. Operators and reviewers should still use **`docs/meshcore_packets/`** on **`meshflow-bot`** for the authoritative capture bundle and campaign ops notes.

### meshflow-ui — status for this phase (this agent)

**No meshflow-ui changes** for Phase 0.5.

### Verification checklist (for whoever picks up next)

1. **PR / branch:** Open **[meshflow-api PR #289](https://github.com/pskillen/meshflow-api/pull/289)** (or its merge commit on `main`) and confirm all paths under **meshflow-api — done** exist on disk.
2. **ADR content vs captures:** Spot-check ADR **Evidence** sections against `docs/packets/meshcore/*.json` and `MESHCORE_PACKET_FIELDS.md`; disagreements should be opened as follow-up issues, not silent drift from the bot bundle.
3. **Phase 1 hand-off:** Use the four ADRs as the **source of truth** for the first meshflow-api migration + ingest PR (issue **[#265](https://github.com/pskillen/meshflow-api/issues/265)** or successor); if an implementer wants to reintroduce `mc_pubkey_hash` or a different dedup key, that is an **ADR amendment**, not an undocumented code choice.
4. **Bot upload:** `RADIO_PROTOCOL=meshcore` remains **capture-only** until a later bot epic wires **`StorageAPIWrapper`** / **`MESHCORE_UPLOAD_ENABLED`** — **not** part of Phase 0.5.

---

## Phase 1.0 — API protocol prep + Meshtastic (MT) relabelling (meshflow-api)

**Status:** **Protocol prep:** merged or merge-ready via **[PR #291](https://github.com/pskillen/meshflow-api/pull/291)** (branch `meshcore/phase-1-0/api-protocol-prep`). **Meshtastic raw row rename + MTI migration:** **[PR #292](https://github.com/pskillen/meshflow-api/pull/292)** on the same branch (verify on `main` after merge). **Tracking:** **[#290](https://github.com/pskillen/meshflow-api/issues/290)** (child of epic **[#265](https://github.com/pskillen/meshflow-api/issues/265)**).  
**Repos touched in this phase:** **meshflow-api only** (no meshflow-bot / meshflow-ui in this phase).

### Purpose of this phase

Add **multi-protocol–ready schema defaults** (existing rows remain **Meshtastic**), **nullable `ObservedNode.node_id`** with a **CHECK** that Meshtastic rows keep a numeric id, and **Meshtastic-only labelling** (constants, URL names, OpenAPI tags) so Phase **1.3** can land MC identity and ingest without a single mega-migration. Follow with an explicit **Meshtastic persistence rename**: the former generic `RawPacket` parent row becomes **`MtRawPacket`** with a dedicated **`packets_mt_raw_packet`** table so the name and storage clearly mean “Meshtastic wire packet,” leaving room for a future MeshCore raw model without overloading the old name. **No** `meshcore_packets` app, **no** `POST /api/meshcore/...`, **no** `mc_pubkey` wiring (issues **#279** / **#280** / **#278**).

### Refactoring delivered in meshflow-api (cumulative — Phases 0.5 + 1.0)

Use this subsection as the **single inventory** of api-repo refactors tied to MeshCore readiness; deeper evidence lives in the Phase **0.5** and **1.0** checklists below.

| Track | What shipped | Where to read details |
| --- | --- | --- |
| **0.5 — design only** | Capture-derived field reference, trimmed JSON samples, four ADRs (identity, channels, broadcast, dedup). | **Phase 0.5** section above; PR **[#289](https://github.com/pskillen/meshflow-api/pull/289)**. |
| **1.0 — protocol prep** | `Protocol` enum, nullable `ObservedNode.node_id` + CHECK, `protocol` / `mc_channel_idx` on shared models, OpenAPI `MeshProtocol`, Meshtastic ingest URL names + tags, `MESHTASTIC_BROADCAST_ID`, cross-app `TODO(meshcore)` / MT scoping notes. | **meshflow-api — done** below; PR **[#291](https://github.com/pskillen/meshflow-api/pull/291)**. |
| **1.0 — Meshtastic raw rename** | `RawPacket` → **`MtRawPacket`**, `db_table` **`packets_mt_raw_packet`**, MTI-safe **`packets.0017`** migration + **`packets/migration_operations.py`**, Django admin for base row + observations, call-site and doc renames (`dx_monitoring`, `stats`, `packets` services/tests, nodes backfill management command, packet-ingestion / DX / recency docs). | Same checklist + **[PR #292](https://github.com/pskillen/meshflow-api/pull/292)**. |

### meshflow-api — done (concrete checklist)

- **Canonical delivery:** **[PR #291](https://github.com/pskillen/meshflow-api/pull/291)** (protocol prep) and **[PR #292](https://github.com/pskillen/meshflow-api/pull/292)** (`MtRawPacket` rename + migration + admin + doc/callsite updates) on **`meshcore/phase-1-0/api-protocol-prep`** (verify on `main` after merge).
- **`Meshflow/common/protocol.py`** — shared `Protocol` `IntegerChoices` (`MESHTASTIC=1`, `MESHCORE=2`).
- **`Meshflow/common/meshcore_node_helpers.py`** — placeholder module for future MC-specific helpers.
- **`Meshflow/common/mesh_node_helpers.py`** — `MESHTASTIC_BROADCAST_ID` + deprecated `BROADCAST_ID` alias; ADR pointer for MC broadcast semantics.
- **Migrations:** `nodes/0034_protocol_fields_observednode_check.py`, `constellations/0006_protocol_fields_messagechannel_constellation.py` — `protocol` on `ObservedNode`, `ManagedNode`, `Constellation`, `MessageChannel`; `mc_channel_idx` on `MessageChannel`; nullable `ObservedNode.node_id` + CHECK (`protocol=1` ⇒ `node_id` not null).
- **Models / serializers** — `protocol` on API payloads where exposed; constellation channel summaries include `protocol` and `mc_channel_idx`; Meshtastic ingest paths filter `ObservedNode` by `protocol=MESHTASTIC`.
- **`Meshflow/packets/`** — package + model docstrings state Meshtastic wire storage; URL `name=` values `meshtastic-packet-ingest` / `meshtastic-node-upsert`; `convert_location_source` uses valid Python 3 multi-`except`.
- **Cross-app** — traceroute / analytics / DX / stats / mesh monitoring: module notes + `TODO(meshcore …)` where MT coupling is real; `MESHTASTIC_BROADCAST_ID` for `0xFFFFFFFF` hop sentinels where applicable; `ObservedNode` lookups scoped to Meshtastic where easy.
- **`openapi.yaml`** — `MeshProtocol` schema; `protocol` / `mc_channel_idx` on shared components; **Meshtastic packets** tag for `/api/packets/…`; `info.description` multi-protocol blurb + link to this file; **NodeApiKeyAuth** on packet ingest paths (fixes undefined `ApiKeyAuth` reference).
- **Tests:** `Meshflow/common/tests/test_mesh_node_helpers.py` updated for `MESHTASTIC_BROADCAST_ID` and alias equality.
- **`RawPacket` → `MtRawPacket` (Meshtastic raw parent row)** — `Meshflow/packets/models.py`: parent model rename, **`Meta.db_table = "packets_mt_raw_packet"`**, all MTI subclasses + `PacketObservation.packet` FK updated; verbose names adjusted for “Meshtastic raw packet.”
- **Migration `packets.0017_rename_rawpacket_to_mtrawpacket`** — **`SeparateDatabaseAndState`**: (1) custom atomic state operation **`RenameMeshtasticRawPacketMtiState`** in **`Meshflow/packets/migration_operations.py`** (mirrors `ProjectState.rename_model` plus child `rawpacket_ptr` → `mtrawpacket_ptr` and `bases` update before reload — avoids Django **#26488 / #28243** `FieldError` / `InvalidBasesError` on MTI); (2) **`RunPython`** applies physical DDL without stepping through a broken `RenameModel` clone: **PostgreSQL** renames child pointer columns, renames parent table, renames four parent indexes; **SQLite** renames child pointer columns + parent table only (legacy physical index names may remain — ORM uses logical migration state).
- **Admin** — **`Meshflow/packets/admin.py`**: `MtRawPacketAdmin`, `PacketObservationAdmin`.
- **Cross-app renames from `RawPacket` → `MtRawPacket`** — e.g. `Meshflow/dx_monitoring/models.py` (`ForeignKey` string `packets.MtRawPacket`), `Meshflow/dx_monitoring/services.py`, `Meshflow/stats/tasks.py`, `Meshflow/stats/views.py`, `Meshflow/packets/services/base.py`, `Meshflow/packets/tests/conftest.py`, `Meshflow/nodes/management/commands/backfill_observednode_created_at.py` (runtime command; historical migration **`nodes/0026_…`** still uses `apps.get_model("packets", "RawPacket")` for replay at that revision).
- **Docs** — Meshtastic wording updates where the old name implied a generic raw row: `docs/features/packet-ingestion/README.md`, `DEDUPLICATION.md`, `adr/0004-mc-dedup-key.md`, `docs/features/dx-monitoring/detection.md`, `docs/features/README.md`, `docs/RECENCY.md`; integration test docstring in `tests/integration/test_packet_deduplication.py`; **`stats/tests/test_tasks.py`** comment alignment.

### meshflow-api — not done *in this phase only* (deferred)

- **MeshCore identity columns** (`mc_pubkey`, …), **MeshCore ingest routes**, **`meshcore_packets`** app — **#279** / **#280** / **#278**.
- **`ManagedNode.mc_channels` M2M** for MeshCore — **#279** unless already required earlier.
- **Neo4j / analytics `protocol` labels on edges** — Phase **3** traceroute work (see module TODOs).
- **Regenerated OpenAPI from code** — contract is maintained as **`openapi.yaml`** hand edits in this repo (no `drf-spectacular` dependency as of this phase).

### meshflow-bot / meshflow-ui — status for this phase

**No meshflow-bot or meshflow-ui changes** in Phase 1.0.

### Verification checklist

1. **Unit tests:** `source venv/bin/activate` (or project venv), `pip install -r Meshflow/requirements.txt` (+ dev deps if needed), `python -m pytest Meshflow/ -v`.
2. **Migrations:** `python manage.py makemigrations --dry-run` — should be clean after `help_text`-only tweaks; if Django emits metadata migrations, commit with a note. After pulling **`packets.0017`**, run **`python manage.py migrate`** against a copy of prod schema (PostgreSQL recommended for index DDL parity) before shipping.
3. **`packets.0017` smoke:** `DJANGO_SETTINGS_MODULE=Meshflow.settings.test python manage.py migrate` (SQLite) and/or **`python -m pytest Meshflow/packets/tests/test_packet_models.py`** — confirms MTI rename migration applies without `InvalidBasesError`.
4. **Import smoke:** `python -c "import django; …"` or `python -c "from packets.serializers import convert_location_source"` from `Meshflow/` with `DJANGO_SETTINGS_MODULE` set — confirms no syntax regressions in serializers.
5. **OpenAPI:** spot-check `/packets/ingest/` and `/packets/nodes/` use **Meshtastic packets** + **NodeApiKeyAuth**; schemas include `MeshProtocol` and nullable `ObservedNode.node_id` where applicable.

---

## Phase 1 — MeshCore ingestion MVP (meshflow-api, meshflow-bot, meshflow-ui)

**Status:** Complete (implementation). **Tracking:** epic [#265](https://github.com/pskillen/meshflow-api/issues/265).

**Repos touched:** meshflow-api, meshflow-bot, meshflow-ui.

### Done

- **API:** `ObservedNode.mc_pubkey` / `mc_pubkey_prefix`, CHECK + partial unique index ([#279](https://github.com/pskillen/meshflow-api/issues/279)); `meshcore_packets` app with ingest + list + dedup + `ObservedNode` receiver ([#280](https://github.com/pskillen/meshflow-api/issues/280), [#278](https://github.com/pskillen/meshflow-api/issues/278)); `protocol` filter on observed-nodes ([#284](https://github.com/pskillen/meshflow-api/issues/284)); `openapi.yaml` + `docs/ENV_VARS.md`; `docs/features/meshcore/feeder-bootstrap.md`.
- **Bot:** `MeshCorePacketSerializer`, `store_raw_meshcore_packet`, `MESHCORE_UPLOAD_ENABLED` ([#83](https://github.com/pskillen/meshflow-bot/issues/83)).
- **UI:** MeshCore map + nodes list pages, sidebar, API hooks ([#250](https://github.com/pskillen/meshflow-ui/issues/250)).

### Not done (deferred)

- `TextMessage` normalisation for MC; telemetry/ack models; MT pages showing MC; automated 24h trial gate (operator checklist in feeder-bootstrap).

### Phase 1.x — tech debt (ADR-0001 display id)

**Status:** Complete. **Tracking:** [#294](https://github.com/pskillen/meshflow-api/issues/294).

- **Done:** Dropped stored `ObservedNode.node_id_str`; API returns computed `!hex8` / `mc:{prefix12}` via model property and serializers (ADR-0001 §6). Migrations `nodes.0043` (nullable interim), `nodes.0044` (RemoveField). Rollback: re-add column and backfill from computed values on a prod clone during a maintenance window.

### Verification

1. `python -m pytest Meshflow/meshcore_packets/tests/ Meshflow/common/tests/test_meshcore_node_helpers.py -v`
2. Bot: `pytest test/meshcore/ -v` (venv + requirements.dev.txt)
3. UI: `npm run build`
4. Integration: `MESHFLOW_MC_API_KEY=... pytest tests/integration/test_meshcore_ingest.py -v`

---

## Phase 2 — MC position from ADVERT ingest (meshflow-api)

**Status:** Complete. **Tracking:** [#298](https://github.com/pskillen/meshflow-api/issues/298) (parent [#266](https://github.com/pskillen/meshflow-api/issues/266)).

**Repos touched:** meshflow-api only.

### Done

- **`MeshCoreLocationSource`** enum (`ADVERT = 1`) on [`Meshflow/nodes/models.py`](../../../Meshflow/nodes/models.py); nullable `meshcore_location_source` on `Position` and `NodeLatestStatus` (internal only — API `latest_location_source` stays MT-only for MC nodes).
- **`Position.original_mc_packet`** FK → `meshcore_packets.MeshCoreRawPacket` (migration `nodes.0045_position_meshcore_provenance`).
- **`meshcore_packets/services/position.py`:** `extract_adv_coords`, `adv_timestamp_to_aware`, `apply_advert_position` — creates `Position` history + updates NLS (mirrors [`PositionPacketService`](../../../Meshflow/packets/services/position.py)).
- **Receiver:** [`meshcore_packets/receivers.py`](../../../Meshflow/meshcore_packets/receivers.py) delegates ADVERT coords to the service; `0.0/0.0` sentinel; prefers `adv_timestamp` over `rx_time`.
- **Tests:** `meshcore_packets/tests/test_advert_position.py`; ingest test asserts `Position` row + provenance.

### Not done (deferred)

- `original_mt_packet` on `Position` for Meshtastic provenance; `protocol` column on `Position`.
- Altitude/heading/speed from ADVERT; `adv_flags` / `adv_type` → node role.
- Public `latest_meshcore_location_source` in OpenAPI.
- Bot/UI changes.

### Verification

1. `python -m pytest Meshflow/meshcore_packets/tests/ -v`
2. `python manage.py migrate` (applies `nodes.0045`)

---

<!-- Future sections: append below with dated ## headings per contributor convention. -->
