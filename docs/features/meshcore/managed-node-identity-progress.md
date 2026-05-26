# ManagedNode protocol identity — progress

**Tracking:** [meshflow-api#362](https://github.com/pskillen/meshflow-api/issues/362) (parent [meshflow-ui#291](https://github.com/pskillen/meshflow-ui/issues/291))  
**Plan:** `.cursor/plans/api_362_protocol_identity_9b9056b9.plan.md`  
**Repos:** meshflow-api only

**Blocks:** [meshflow-ui#293](https://github.com/pskillen/meshflow-ui/issues/293) enrollment; API side of [meshflow-ui#254](https://github.com/pskillen/meshflow-ui/issues/254)

---

## Overall status

**Status:** Complete (pending PR + deploy)

**Branch:** `api-362/managed-node-protocol-identity` (to push)

---

## Delivered

| Slice | Status | Notes |
| --- | --- | --- |
| Migration `0050` | Complete | `0`→NULL for MC; nullable `meshtastic_node_id`; `managednode_protocol_identity` CHECK; partial unique on MT id |
| Django admin + feeder-bootstrap.md | Complete | MC requires `mc_pubkey`; no placeholder `0` |
| Serializers | Complete | Protocol-aware create; `mc_pubkey` + default location writable; `linked_managed_nodes` on API key detail |
| Views | Complete | `internal_id` lookup + MT numeric compat; `managed_node_internal_id` on add/remove node |
| OpenAPI | Complete | Path `{internal_id}` uuid; nullable `meshtastic_node_id`; linked nodes schema |
| Tests | Complete | `test_managed_node_protocol_identity.py`; fixture coercion; reverse `internal_id` |

**Verify locally**

```bash
cd Meshflow && source ../venv/bin/activate
python manage.py migrate
python -m pytest nodes/tests/test_managed_node_protocol_identity.py nodes/tests/ -q
```

---

## Next

1. Open PR linking #362 / #291; deploy API before UI enrollment (#293).
