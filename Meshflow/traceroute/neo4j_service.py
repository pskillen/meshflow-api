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
        session.run("""
            CREATE CONSTRAINT mesh_node_node_id_unique IF NOT EXISTS
            FOR (n:MeshNode) REQUIRE n.node_id IS UNIQUE
            """)
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
        if source_node.default_location_latitude is not None and source_node.default_location_longitude is not None:
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


def _extract_edges(route_data: list) -> list[tuple[int, int, float | None]]:
    """Extract consecutive (from_id, to_id, snr) from route list of {node_id, snr}.
    SNR at receiving node (b) is the SNR of the link a->b."""
    edges = []
    for i in range(len(route_data) - 1):
        a = route_data[i]["node_id"]
        b = route_data[i + 1]["node_id"]
        snr = route_data[i + 1].get("snr")
        if a != UNKNOWN_NODE_ID and b != UNKNOWN_NODE_ID:
            edges.append((a, b, snr if snr is not None else None))
    return edges


def add_traceroute_edges(auto_traceroute: AutoTraceRoute, driver=None):
    """
    Extract edges from route/route_back, upsert nodes, create ROUTED_TO relationships.
    Only creates edges where both endpoints have coordinates.
    """
    driver = driver or get_driver()

    auto_tr = (
        AutoTraceRoute.objects.filter(pk=auto_traceroute.pk)
        .select_related("source_node", "target_node", "target_node__latest_status")
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
        o.node_id: o for o in ObservedNode.objects.filter(node_id__in=node_ids).select_related("latest_status")
    }

    # Build coords and names maps
    coords = {}
    names = {}
    for nid in node_ids:
        pos = _get_node_coords(nid, auto_tr.source_node, auto_tr.target_node, observed_by_id)
        if pos:
            coords[nid] = pos
            names[nid] = _get_node_names(nid, auto_tr.source_node, auto_tr.target_node, observed_by_id)

    # Extract edges (from_id, to_id, snr)
    edges = []
    if auto_tr.route:
        edges.extend(_extract_edges(auto_tr.route))
    if auto_tr.route_back:
        edges.extend(_extract_edges(auto_tr.route_back))

    # Prepend edge (source -> route[0]) — source is not in route per Meshtastic format
    if auto_tr.route and len(auto_tr.route) > 0:
        first_hop = auto_tr.route[0]
        src_id = auto_tr.source_node.node_id
        first_id = first_hop["node_id"]
        if first_id != UNKNOWN_NODE_ID:
            edges.insert(0, (src_id, first_id, first_hop.get("snr")))

    # Filter: both endpoints must have coords
    valid_edges = [(a, b, snr) for a, b, snr in edges if a in coords and b in coords]
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
        for a_id, b_id, snr in valid_edges:
            a_str = meshtastic_id_to_hex(a_id)
            b_str = meshtastic_id_to_hex(b_id)
            a_lat, a_lng = coords[a_id]
            b_lat, b_lng = coords[b_id]
            a_short, a_long = names.get(a_id, (a_str, a_str))
            b_short, b_long = names.get(b_id, (b_str, b_str))

            # Build relationship props: weight, triggered_at always; snr when present
            rel_props = "weight: 1, triggered_at: datetime($triggered_at)"
            params = {
                "a_id": a_id,
                "a_str": a_str,
                "a_lat": a_lat,
                "a_lng": a_lng,
                "a_short_name": a_short,
                "a_long_name": a_long,
                "b_id": b_id,
                "b_str": b_str,
                "b_lat": b_lat,
                "b_lng": b_lng,
                "b_short_name": b_short,
                "b_long_name": b_long,
                "triggered_at": triggered_at_str,
            }
            if snr is not None:
                rel_props += ", snr: $snr"
                params["snr"] = float(snr)

            session.run(
                f"""
                MERGE (a:MeshNode {{node_id: $a_id}})
                SET a.node_id_str = $a_str, a.latitude = $a_lat, a.longitude = $a_lng,
                    a.short_name = $a_short_name, a.long_name = $a_long_name
                MERGE (b:MeshNode {{node_id: $b_id}})
                SET b.node_id_str = $b_str, b.latitude = $b_lat, b.longitude = $b_lng,
                    b.short_name = $b_short_name, b.long_name = $b_long_name
                CREATE (a)-[:ROUTED_TO {{{rel_props}}}]->(b)
                """,
                **params,
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

    qs = (
        AutoTraceRoute.objects.filter(status=AutoTraceRoute.STATUS_COMPLETED)
        .select_related("source_node", "target_node")
        .order_by("id")
    )

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


def run_heatmap_query(
    triggered_at_after=None,
    bbox=None,
    constellation_id=None,
    driver=None,
):
    """
    Query Neo4j for aggregated heatmap edges (bidirectional) and nodes.
    Returns dict with edges, nodes, and meta.
    """
    driver = driver or get_driver()

    # Build Cypher with optional filters
    where_clauses = [
        "a.latitude IS NOT NULL AND b.latitude IS NOT NULL",
    ]
    params = {}

    if triggered_at_after:
        where_clauses.append("r.triggered_at >= datetime($triggered_at_after)")
        params["triggered_at_after"] = (
            triggered_at_after.isoformat() if hasattr(triggered_at_after, "isoformat") else str(triggered_at_after)
        )

    if bbox and len(bbox) >= 4:
        min_lat, min_lon, max_lat, max_lon = bbox[:4]
        where_clauses.append(
            "a.latitude >= $min_lat AND a.latitude <= $max_lat "
            "AND a.longitude >= $min_lon AND a.longitude <= $max_lon "
            "AND b.latitude >= $min_lat AND b.latitude <= $max_lat "
            "AND b.longitude >= $min_lon AND b.longitude <= $max_lon"
        )
        params["min_lat"] = min_lat
        params["min_lon"] = min_lon
        params["max_lat"] = max_lat
        params["max_lon"] = max_lon

    constellation_node_ids = None
    if constellation_id is not None:
        from constellations.models import Constellation

        try:
            constellation = Constellation.objects.get(pk=constellation_id)
            constellation_node_ids = list(constellation.nodes.values_list("node_id", flat=True))
        except Constellation.DoesNotExist:
            constellation_node_ids = []
        if not constellation_node_ids:
            return {
                "edges": [],
                "nodes": [],
                "meta": {"active_nodes_count": 0, "total_trace_routes_count": 0},
            }
        where_clauses.append("(a.node_id IN $constellation_node_ids OR b.node_id IN $constellation_node_ids)")
        params["constellation_node_ids"] = constellation_node_ids

    where_str = " AND ".join(where_clauses)

    # Bidirectional: use canonical direction (a.node_id < b.node_id) and sum weights
    query = f"""
    MATCH (a:MeshNode)-[r:ROUTED_TO]-(b:MeshNode)
    WHERE {where_str}
    WITH a, b, sum(r.weight) AS weight
    WHERE a.node_id < b.node_id
    RETURN a.node_id AS from_node_id,
           a.latitude AS from_lat, a.longitude AS from_lng,
           a.node_id_str AS from_node_id_str,
           a.short_name AS from_short_name, a.long_name AS from_long_name,
           b.node_id AS to_node_id,
           b.latitude AS to_lat, b.longitude AS to_lng,
           b.node_id_str AS to_node_id_str,
           b.short_name AS to_short_name, b.long_name AS to_long_name,
           weight
    """

    edges = []
    nodes_by_id = {}

    with driver.session() as session:
        result = session.run(query, params)
        for record in result:
            from_id = record["from_node_id"]
            to_id = record["to_node_id"]
            edges.append(
                {
                    "from_node_id": from_id,
                    "to_node_id": to_id,
                    "from_lat": record["from_lat"],
                    "from_lng": record["from_lng"],
                    "to_lat": record["to_lat"],
                    "to_lng": record["to_lng"],
                    "weight": record["weight"],
                }
            )
            if from_id not in nodes_by_id:
                nodes_by_id[from_id] = {
                    "node_id": from_id,
                    "node_id_str": record["from_node_id_str"] or meshtastic_id_to_hex(from_id),
                    "lat": record["from_lat"],
                    "lng": record["from_lng"],
                    "short_name": record["from_short_name"] or "",
                    "long_name": record["from_long_name"] or "",
                }
            if to_id not in nodes_by_id:
                nodes_by_id[to_id] = {
                    "node_id": to_id,
                    "node_id_str": record["to_node_id_str"] or meshtastic_id_to_hex(to_id),
                    "lat": record["to_lat"],
                    "lng": record["to_lng"],
                    "short_name": record["to_short_name"] or "",
                    "long_name": record["to_long_name"] or "",
                }

    nodes = list(nodes_by_id.values())

    # Meta: approximate counts (from Django for total TR, from Neo4j for nodes)
    from .models import AutoTraceRoute

    total_tr = AutoTraceRoute.objects.filter(status=AutoTraceRoute.STATUS_COMPLETED).count()
    if triggered_at_after:
        total_tr = AutoTraceRoute.objects.filter(
            status=AutoTraceRoute.STATUS_COMPLETED,
            triggered_at__gte=triggered_at_after,
        ).count()

    meta = {
        "active_nodes_count": len(nodes),
        "total_trace_routes_count": total_tr,
    }

    return {
        "edges": edges,
        "nodes": nodes,
        "meta": meta,
    }


def run_node_links_query(node_id: int, triggered_at_after=None, driver=None):
    """
    Query Neo4j for traceroute links involving a focus node.
    Returns edges (with avg SNR in/out), nodes, and snr_history per peer.
    """
    driver = driver or get_driver()
    params = {"node_id": node_id}
    if triggered_at_after:
        params["triggered_at_after"] = (
            triggered_at_after.isoformat() if hasattr(triggered_at_after, "isoformat") else str(triggered_at_after)
        )

    # Outbound: focus -> peer. Inbound: peer -> focus.
    # Use two queries and merge by peer.
    where_time = " AND r.triggered_at >= datetime($triggered_at_after)" if triggered_at_after else ""
    where_coords = " AND focus.latitude IS NOT NULL AND peer.latitude IS NOT NULL"

    outbound_query = f"""
    MATCH (focus:MeshNode {{node_id: $node_id}})-[r:ROUTED_TO]->(peer:MeshNode)
    WHERE r.snr IS NOT NULL{where_time}{where_coords}
    RETURN peer.node_id AS peer_id,
           peer.latitude AS peer_lat, peer.longitude AS peer_lng,
           peer.node_id_str AS peer_node_id_str,
           peer.short_name AS peer_short_name, peer.long_name AS peer_long_name,
           avg(r.snr) AS avg_snr_out,
           count(r) AS count_out,
           collect({{triggered_at: toString(r.triggered_at), snr: r.snr}}) AS outbound_history
    """

    inbound_query = f"""
    MATCH (focus:MeshNode {{node_id: $node_id}})<-[r:ROUTED_TO]-(peer:MeshNode)
    WHERE r.snr IS NOT NULL{where_time}{where_coords}
    RETURN peer.node_id AS peer_id,
           peer.latitude AS peer_lat, peer.longitude AS peer_lng,
           peer.node_id_str AS peer_node_id_str,
           peer.short_name AS peer_short_name, peer.long_name AS peer_long_name,
           avg(r.snr) AS avg_snr_in,
           count(r) AS count_in,
           collect({{triggered_at: toString(r.triggered_at), snr: r.snr}}) AS inbound_history
    """

    peers = {}
    focus_node = None

    with driver.session() as session:
        # Get focus node coords
        focus_result = session.run(
            """
            MATCH (n:MeshNode {node_id: $node_id})
            WHERE n.latitude IS NOT NULL
            RETURN n.node_id AS node_id, n.latitude AS lat, n.longitude AS lng,
                   n.node_id_str AS node_id_str, n.short_name AS short_name, n.long_name AS long_name
            """,
            node_id=node_id,
        )
        focus_record = focus_result.single()
        if not focus_record:
            return {"edges": [], "nodes": [], "snr_history": []}

        focus_node = {
            "node_id": focus_record["node_id"],
            "lat": focus_record["lat"],
            "lng": focus_record["lng"],
            "node_id_str": focus_record["node_id_str"] or meshtastic_id_to_hex(node_id),
            "short_name": focus_record["short_name"] or "",
            "long_name": focus_record["long_name"] or "",
        }

        # Outbound
        for record in session.run(outbound_query, params):
            pid = record["peer_id"]
            peers[pid] = {
                "peer_id": pid,
                "peer_lat": record["peer_lat"],
                "peer_lng": record["peer_lng"],
                "peer_node_id_str": record["peer_node_id_str"] or meshtastic_id_to_hex(pid),
                "peer_short_name": record["peer_short_name"] or "",
                "peer_long_name": record["peer_long_name"] or "",
                "avg_snr_out": record["avg_snr_out"],
                "count_out": record["count_out"],
                "outbound_history": record["outbound_history"] or [],
                "avg_snr_in": None,
                "count_in": 0,
                "inbound_history": [],
            }

        # Inbound
        for record in session.run(inbound_query, params):
            pid = record["peer_id"]
            if pid not in peers:
                peers[pid] = {
                    "peer_id": pid,
                    "peer_lat": record["peer_lat"],
                    "peer_lng": record["peer_lng"],
                    "peer_node_id_str": record["peer_node_id_str"] or meshtastic_id_to_hex(pid),
                    "peer_short_name": record["peer_short_name"] or "",
                    "peer_long_name": record["peer_long_name"] or "",
                    "avg_snr_out": None,
                    "count_out": 0,
                    "outbound_history": [],
                    "avg_snr_in": None,
                    "count_in": 0,
                    "inbound_history": [],
                }
            peers[pid]["avg_snr_in"] = record["avg_snr_in"]
            peers[pid]["count_in"] = record["count_in"]
            peers[pid]["inbound_history"] = record["inbound_history"] or []

    # Build response
    nodes_by_id = {node_id: focus_node}
    edges = []
    snr_history = []

    for pid, p in peers.items():
        nodes_by_id[pid] = {
            "node_id": pid,
            "lat": p["peer_lat"],
            "lng": p["peer_lng"],
            "node_id_str": p["peer_node_id_str"],
            "short_name": p["peer_short_name"],
            "long_name": p["peer_long_name"],
        }
        count = p["count_out"] + p["count_in"]
        edges.append(
            {
                "from_node_id": node_id,
                "to_node_id": pid,
                "from_lat": focus_node["lat"],
                "from_lng": focus_node["lng"],
                "to_lat": p["peer_lat"],
                "to_lng": p["peer_lng"],
                "avg_snr_in": p["avg_snr_in"],
                "avg_snr_out": p["avg_snr_out"],
                "count": count,
            }
        )
        snr_history.append(
            {
                "peer_node_id": pid,
                "peer_short_name": p["peer_short_name"],
                "inbound": [{"triggered_at": h["triggered_at"], "snr": h["snr"]} for h in p["inbound_history"]],
                "outbound": [{"triggered_at": h["triggered_at"], "snr": h["snr"]} for h in p["outbound_history"]],
            }
        )

    return {
        "edges": edges,
        "nodes": list(nodes_by_id.values()),
        "snr_history": snr_history,
    }
