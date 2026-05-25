# Permissions implementation status

| Phase | Item | Status |
|-------|------|--------|
| 0 | Access matrix (`README.md`) | done |
| 1 | `common/access.py`, `common/drf_permissions.py` | done |
| 1 | Remove `ConstellationUserMembership` + migrations | done |
| 1 | Feeder group + data migration | done |
| 1 | Traceroute trigger = feeder/admin | done |
| 1 | API keys = feeder/admin, any constellation | done |
| 2 | Guest read: constellations, channels | done |
| 2 | Guest read: messages | done |
| 2 | Guest read: observed nodes (redaction) | done |
| 2 | Guest read: stats global/snapshots | done |
| 2 | Guest read: traceroutes + analytics GET | done |
| 3 | UI #298 anonymous routes | tracked in meshflow-ui |
| 4 | Unit tests `common/tests/test_guest_access.py` | done |
| 4 | Integration tests | done |
| 4 | OpenAPI `security: []` on guest GETs | partial (key paths) |
