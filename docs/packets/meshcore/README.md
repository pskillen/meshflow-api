# MeshCore representative samples (API-side)

One JSON file per **visible shape** from the Phase 0.4 capture campaign, copied from **meshflow-bot** for citation in ADRs and reviews without vendoring the full capture tree.

**Provenance:** Full bundle, inventory, and filenames live in [meshflow-bot `docs/meshcore_packets/`](https://github.com/pskillen/meshflow-bot/tree/main/docs/meshcore_packets) (see the “Representative samples” table in that README). Files here match those paths unless noted.

| Shape | Path in this repo |
| ----- | ----------------- |
| Advertisement | [`advertisement/20260506_211140_430432.json`](advertisement/20260506_211140_430432.json) |
| Channel text (`CHAN`) | [`channel_message/20260507_094921_075978.json`](channel_message/20260507_094921_075978.json) |
| Contact / DM (`PRIV`) | [`contact_message/20260506_205758_541689.json`](contact_message/20260506_205758_541689.json) |
| Control | [`control_data/20260506_211530_400099.json`](control_data/20260506_211530_400099.json) |
| Discover response | [`discover_response/20260506_211530_400913.json`](discover_response/20260506_211530_400913.json) |
| Messages waiting | [`messages_waiting/20260506_205758_540343.json`](messages_waiting/20260506_205758_540343.json) |
| Path update | [`path_update/20260506_205759_895381.json`](path_update/20260506_205759_895381.json) |
| RX log — `TEXT_MSG` | [`rx_log_data_text.json`](rx_log_data_text.json) |
| RX log — `ADVERT` (decoded) | [`rx_log_data_advert.json`](rx_log_data_advert.json) |
| RX log — `PATH` | [`rx_log_data_path.json`](rx_log_data_path.json) |
| RX log — `REQ` | [`rx_log_data_req.json`](rx_log_data_req.json) |
| RX log — `CONTROL` | [`rx_log_data_control.json`](rx_log_data_control.json) |
| Trace data | [`trace_data/20260507_154102_445613.json`](trace_data/20260507_154102_445613.json) |

Field tables: [`docs/features/packet-ingestion/MESHCORE_PACKET_FIELDS.md`](../../features/packet-ingestion/MESHCORE_PACKET_FIELDS.md).
