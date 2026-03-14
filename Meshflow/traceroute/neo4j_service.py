"""Neo4j service for traceroute heatmap graph operations."""

import logging
from datetime import datetime

from django.conf import settings
from neo4j import GraphDatabase

from common.mesh_node_helpers import meshtastic_id_to_hex
from nodes.models import ManagedNode, ObservedNode

from .models import AutoTraceRoute

logger = logging.getLogger(__name__)

UNKNOWN_NODE_ID = 0xFFFFFFFF

_driver = None


def get_driver():
    """Lazy Neo4j driver connection."""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
    return _driver


def ensure_schema(driver=None):
    """Create constraints and indexes for MeshNode. Idempotent."""
    driver = driver or get_driver()
    with driver.session() as session:
        # Neo4j 5: CREATE CONSTRAINT IF NOT EXISTS
        session.run(
            """
            CREATE CONSTRAINT mesh_node_node_id_unique IF NOT EXISTS
            FOR (n:MeshNode) REQUIRE n.node_id IS UNIQUE
            """
        )
    logger.info("Neo4j schema ensured: MeshNode.node_id unique constraint")


def upsert_node(
    driver,
    node_id: int,
    node_id_str: str,
    lat: float,
    lng: float,
    short_name: str | None = None,
    long_name: str | None = None,
):
    """Merge a MeshNode by node_id, set node_id_str, latitude, longitude, short_name, long_name."""
    with driver.session() as session:
        session.run(
            """
            MERGE (n:MeshNode {node_id: $node_id})
            SET n.node_id_str = $node_id_str,
                n.latitude = $latitude,
                n.longitude = $longitude,
                n.short_name = $short_name,
                n.long_name = $long_name
            """,
            node_id=node_id,
            node_id_str=node_id_str,
            latitude=lat,
            longitude=lng,
            short_name=short_name or "",
            long_name=long_name or "",
        )


def _get_node_coords(
    node_id: int,
    source_node: ManagedNode,
    target_node: ObservedNode,
    observed_by_id: dict,
) -> tuple[float, float] | None:
    """Return (lat, lng) for node_id, or None if unknown."""
    if node_id == UNKNOWN_NODE_ID:
        return None

    # Source node: ManagedNode default_location or ObservedNode.latest_status
    if node_id == source_node.node_id:
        if (
            source_node.default_location_latitude is not None
            and source_node.default_location_longitude is not None
        ):
            return (
                source_node.default_location_latitude,
                source_node.default_location_longitude,
            )
        obs = observed_by_id.get(node_id)
        if obs and obs.latest_status and obs.latest_status.latitude is not None:
            return obs.latest_status.latitude, obs.latest_status.longitude
        return None

    # Target node: ObservedNode.latest_status
    if node_id == target_node.node_id:
        if target_node.latest_status and target_node.latest_status.latitude is not None:
            return (
                target_node.latest_status.latitude,
                target_node.latest_status.longitude,
            )
        return None

    # Intermediate nodes: ObservedNode.latest_status
    obs = observed_by_id.get(node_id)
    if obs and obs.latest_status and obs.latest_status.latitude is not None:
        return obs.latest_status.latitude, obs.latest_status.longitude
    return None


def _get_node_names(
    node_id: int,
    source_node: ManagedNode,
    target_node: ObservedNode,
    observed_by_id: dict,
) -> tuple[str, str]:
    """Return (short_name, long_name) for node_id. Uses node_id_str as fallback."""
    fallback = meshtastic_id_to_hex(node_id)
    if node_id == UNKNOWN_NODE_ID:
        return ("unknown", "unknown")

    # Source node: ObservedNode if exists, else ManagedNode.name
    if node_id == source_node.node_id:
        obs = observed_by_id.get(node_id)
        if obs:
            return (obs.short_name or fallback, obs.long_name or fallback)
        name = source_node.name or fallback
        return (name[:5] if len(name) > 5 else name, name)

    # Target node and intermediate nodes: ObservedNode
    obs = observed_by_id.get(node_id)
    if obs:
        return (obs.short_name or fallback, obs.long_name or fallback)
    return (fallback, fallback)


def _extract_edges(route_data: list) -> list[tuple[int, int]]:
    """Extract consecutive (from_id, to_id) pairs from route list of {node_id, snr}."""
    edges = []
    for i in range(len(route_data) - 1):
        a = route_data[i]["node_id"]
        b = route_data[i + 1]["node_id"]
        if a != UNKNOWN_NODE_ID and b != UNKNOWN_NODE_ID:
            edges.append((a, b))
    return edges


def add_traceroute_edges(auto_traceroute: AutoTraceRoute, driver=None):
    """
    Extract edges from route/route_back, upsert nodes, create ROUTED_TO relationships.
    Only creates edges where both endpoints have coordinates.
    """
    driver = driver or get_driver()

    auto_tr = (
        AutoTraceRoute.objects \
            .filter(pk=auto_traceroute.pk) \
            .select_related("source_node", "target_node", "target_node__latest_status") \
            .first()
    )
    if not auto_tr or not auto_tr.route and not auto_tr.route_back:
        return

    # Collect all node_ids from route and route_back
    node_ids = set()
    for item in (auto_tr.route or []) + (auto_tr.route_back or []):
        nid = item["node_id"]
        if nid != UNKNOWN_NODE_ID:
            node_ids.add(nid)
    node_ids.add(auto_tr.source_node.node_id)
    node_ids.add(auto_tr.target_node.node_id)

    observed_by_id = {
        o.node_id: o
        for o in ObservedNode.objects.filter(node_id__in=node_ids).select_related(
            "latest_status"
        )
    }

    # Build coords and names maps
    coords = {}
    names = {}
    for nid in node_ids:
        pos = _get_node_coords(
            nid, auto_tr.source_node, auto_tr.target_node, observed_by_id
        )
        if pos:
            coords[nid] = pos
            names[nid] = _get_node_names(
                nid, auto_tr.source_node, auto_tr.target_node, observed_by_id
            )

    # Extract edges
    edges = []
    if auto_tr.route:
        edges.extend(_extract_edges(auto_tr.route))
    if auto_tr.route_back:
        edges.extend(_extract_edges(auto_tr.route_back))

    # Filter: both endpoints must have coords
    valid_edges = [(a, b) for a, b in edges if a in coords and b in coords]
    if not valid_edges:
        logger.debug(
            "add_traceroute_edges: no edges with coords for AutoTraceRoute %s",
            auto_tr.id,
        )
        return

    triggered_at = auto_tr.triggered_at
    if triggered_at and hasattr(triggered_at, "isoformat"):
        triggered_at_str = triggered_at.isoformat()
    elif triggered_at:
        triggered_at_str = datetime.fromisoformat(str(triggered_at)).isoformat()
    else:
        triggered_at_str = datetime.utcnow().isoformat() + "Z"

    with driver.session() as session:
        for a_id, b_id in valid_edges:
            a_str = meshtastic_id_to_hex(a_id)
            b_str = meshtastic_id_to_hex(b_id)
            a_lat, a_lng = coords[a_id]
            b_lat, b_lng = coords[b_id]
            a_short, a_long = names.get(a_id, (a_str, a_str))
            b_short, b_long = names.get(b_id, (b_str, b_str))

            session.run(
                """
                MERGE (a:MeshNode {node_id: $a_id})
                SET a.node_id_str = $a_str, a.latitude = $a_lat, a.longitude = $a_lng,
                    a.short_name = $a_short_name, a.long_name = $a_long_name
                MERGE (b:MeshNode {node_id: $b_id})
                SET b.node_id_str = $b_str, b.latitude = $b_lat, b.longitude = $b_lng,
                    b.short_name = $b_short_name, b.long_name = $b_long_name
                CREATE (a)-[:ROUTED_TO {weight: 1, triggered_at: datetime($triggered_at)}]->(b)
                """,
                a_id=a_id,
                a_str=a_str,
                a_lat=a_lat,
                a_lng=a_lng,
                a_short_name=a_short,
                a_long_name=a_long,
                b_id=b_id,
                b_str=b_str,
                b_lat=b_lat,
                b_lng=b_lng,
                b_short_name=b_short,
                b_long_name=b_long,
                triggered_at=triggered_at_str,
            )

    logger.info(
        "add_traceroute_edges: pushed %d edges for AutoTraceRoute %s",
        len(valid_edges),
        auto_tr.id,
    )


def export_all_traceroutes_to_neo4j(driver=None, batch_size: int = 100):
    """Batch export all completed AutoTraceRoute records to Neo4j."""
    driver = driver or get_driver()
    ensure_schema(driver)

    qs = AutoTraceRoute.objects \
        .filter(status=AutoTraceRoute.STATUS_COMPLETED) \
        .select_related("source_node", "target_node") \
        .order_by("id")

    total = qs.count()
    exported = 0

    for offset in range(0, total, batch_size):
        batch = list(qs[offset : offset + batch_size])
        for auto_tr in batch:
            try:
                add_traceroute_edges(auto_tr, driver=driver)
                exported += 1
            except Exception as e:
                logger.exception(
                    "export_all_traceroutes_to_neo4j: failed for AutoTraceRoute %s: %s",
                    auto_tr.id,
                    e,
                )

    logger.info(
        "export_all_traceroutes_to_neo4j: exported %d of %d traceroutes",
        exported,
        total,
    )
    return {"total": total, "exported": exported}
