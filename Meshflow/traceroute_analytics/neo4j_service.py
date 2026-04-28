"""Neo4j graph export and query helpers for traceroute analytics."""

import logging
from datetime import datetime

from django.conf import settings
from django.utils import timezone

import networkx as nx
from neo4j import GraphDatabase
from tqdm import tqdm

from common.mesh_node_helpers import meshtastic_id_to_hex
from nodes.models import ManagedNode, ObservedNode
from traceroute.models import AutoTraceRoute

logger = logging.getLogger(__name__)

UNKNOWN_NODE_ID = 0xFFFFFFFF

# Role classification: treat ObservedNode missing or older than this as offline.
HEATMAP_OFFLINE_ROLE_HOURS = 24

_driver = None


def _heatmap_graph_metrics(edges):
    """Return betweenness (0–1) and integer degree per node id for aggregated edges."""
    g = nx.Graph()
    for e in edges:
        g.add_edge(e["from_node_id"], e["to_node_id"])
    if g.number_of_nodes() == 0:
        return {}, {}
    betweenness = nx.betweenness_centrality(g, normalized=True)
    degree = dict(g.degree())
    return betweenness, degree


def _assign_heatmap_roles(nodes, last_heard_by_id, now):
    """Set ``role`` on each node: backbone, relay, leaf, or offline.

    Leaf includes degree 1–2 so lightly attached nodes are not labelled relay/backbone.
    Backbone and relay require degree ≥ 3.
    """
    offline_sec = HEATMAP_OFFLINE_ROLE_HOURS * 3600

    def is_offline(nid):
        lh = last_heard_by_id.get(nid)
        if lh is None:
            return True
        delta = now - lh
        return delta.total_seconds() > offline_sec

    active = [n for n in nodes if not is_offline(n["node_id"])]
    if active:
        sorted_c = sorted(n["centrality"] for n in active)
        last_i = len(sorted_c) - 1
        i75 = max(0, min(last_i, int(round(0.75 * last_i))))
        c75 = sorted_c[i75]
    else:
        c75 = 0.0

    for n in nodes:
        nid = n["node_id"]
        if is_offline(nid):
            n["role"] = "offline"
        elif n["degree"] <= 2:
            n["role"] = "leaf"
        elif n["degree"] >= 3 and n["centrality"] >= c75:
            n["role"] = "backbone"
        else:
            n["role"] = "relay"


def _enrich_heatmap_nodes(nodes, edges):
    """Add centrality, degree, last_seen (ISO), and role using NetworkX + ObservedNode."""
    betweenness, degree = _heatmap_graph_metrics(edges)
    ids = [n["node_id"] for n in nodes]
    last_heard_by_id = {}
    if ids:
        for row in ObservedNode.objects.filter(node_id__in=ids).values("node_id", "last_heard"):
            last_heard_by_id[row["node_id"]] = row["last_heard"]

    now = timezone.now()
    for n in nodes:
        nid = n["node_id"]
        n["centrality"] = float(betweenness.get(nid, 0.0))
        n["degree"] = int(degree.get(nid, 0))
        lh = last_heard_by_id.get(nid)
        n["last_seen"] = lh.isoformat() if lh else None

    _assign_heatmap_roles(nodes, last_heard_by_id, now)


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


def _safe_latest_status(obs):
    """Return obs.latest_status or None (reverse one-to-one raises RelatedObjectDoesNotExist otherwise)."""
    if obs is None:
        return None
    try:
        return obs.latest_status
    except Exception:
        return None


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
        status = _safe_latest_status(observed_by_id.get(node_id))
        if status is not None and status.latitude is not None:
            return status.latitude, status.longitude
        return None

    # Target node: ObservedNode.latest_status
    if node_id == target_node.node_id:
        status = _safe_latest_status(target_node)
        if status is not None and status.latitude is not None:
            return status.latitude, status.longitude
        return None

    # Intermediate nodes: ObservedNode.latest_status
    status = _safe_latest_status(observed_by_id.get(node_id))
    if status is not None and status.latitude is not None:
        return status.latitude, status.longitude
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


def add_traceroute_edges(auto_traceroute: AutoTraceRoute, driver=None, *, quiet: bool = False):
    """
    Extract edges from route/route_back, upsert nodes, create ROUTED_TO relationships.
    Only creates edges where both endpoints have coordinates.
    When quiet=True, suppresses success logging (for bulk export to avoid clashing with tqdm).

    Route format (Meshtastic): ``route`` and ``route_back`` are relay-only lists of
    ``{node_id, snr}`` dicts. The source is ``auto_tr.source_node`` (ManagedNode); the
    target/responder is ``auto_tr.target_node`` (ObservedNode, = packet ``from_node``).
    Neither endpoint is stored in ``route`` / ``route_back``. This function emits the
    full chain of edges for both directions, including the synthetic bookends
    (``source → route[0]``, ``route[-1] → target`` and mirror on the return path),
    plus a ``source ↔ target`` pair for direct (zero-relay) traceroutes when both
    endpoints have coordinates.
    """
    driver = driver or get_driver()

    auto_tr = (
        AutoTraceRoute.objects.filter(pk=auto_traceroute.pk)
        .select_related("source_node", "target_node", "target_node__latest_status", "raw_packet")
        .first()
    )
    if not auto_tr:
        return

    route = auto_tr.route or []
    route_back = auto_tr.route_back or []

    # Collect all node_ids from route, route_back, source and target
    node_ids = set()
    for item in route + route_back:
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

    # Trailing SNR values from the raw packet (firmware sometimes sends one extra
    # value per direction: the SNR at the responding endpoint for the final hop).
    # auto_tr.route only carries snr_towards[:len(route)], so pull the bookend
    # SNR from raw_packet when available.
    raw_packet = auto_tr.raw_packet
    forward_target_snr = None
    return_source_snr = None
    if raw_packet is not None:
        snr_towards = raw_packet.snr_towards or []
        snr_back = raw_packet.snr_back or []
        if len(snr_towards) > len(route):
            forward_target_snr = snr_towards[len(route)]
        if len(snr_back) > len(route_back):
            return_source_snr = snr_back[len(route_back)]

    source_id = auto_tr.source_node.node_id
    target_id = auto_tr.target_node.node_id

    # Build full chains (source/target are not in route); reuse _extract_edges which
    # filters UNKNOWN_NODE_ID and picks SNR from the receiving end of each hop.
    forward_chain = (
        [{"node_id": source_id, "snr": None}] + list(route) + [{"node_id": target_id, "snr": forward_target_snr}]
    )
    return_chain = (
        [{"node_id": target_id, "snr": None}] + list(route_back) + [{"node_id": source_id, "snr": return_source_snr}]
    )

    edges = _extract_edges(forward_chain) + _extract_edges(return_chain)

    # Defensive: drop self-loops (pathological data where source/target collide with a relay).
    edges = [(a, b, snr) for a, b, snr in edges if a != b]

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

    auto_tr_id = auto_tr.id

    with driver.session() as session:
        for a_id, b_id, snr in valid_edges:
            a_str = meshtastic_id_to_hex(a_id)
            b_str = meshtastic_id_to_hex(b_id)
            a_lat, a_lng = coords[a_id]
            b_lat, b_lng = coords[b_id]
            a_short, a_long = names.get(a_id, (a_str, a_str))
            b_short, b_long = names.get(b_id, (b_str, b_str))

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
                "auto_tr_id": auto_tr_id,
                "snr": float(snr) if snr is not None else None,
                "source_node_id": source_id,
                "target_strategy": auto_tr.target_strategy,
            }

            # MERGE keyed on (auto_tr_id, a_id, b_id, triggered_at) so a re-export
            # of the same AutoTraceRoute is idempotent: the existing relationship
            # is updated in place rather than duplicated. weight stays at 1 per TR
            # so bidirectional aggregation in run_heatmap_query continues to count
            # one unit per distinct traceroute-hop.
            session.run(
                """
                MERGE (a:MeshNode {node_id: $a_id})
                SET a.node_id_str = $a_str, a.latitude = $a_lat, a.longitude = $a_lng,
                    a.short_name = $a_short_name, a.long_name = $a_long_name
                MERGE (b:MeshNode {node_id: $b_id})
                SET b.node_id_str = $b_str, b.latitude = $b_lat, b.longitude = $b_lng,
                    b.short_name = $b_short_name, b.long_name = $b_long_name
                MERGE (a)-[r:ROUTED_TO {
                    auto_tr_id: $auto_tr_id,
                    a_id: $a_id,
                    b_id: $b_id,
                    triggered_at: datetime($triggered_at)
                }]->(b)
                ON CREATE SET r.weight = 1, r.snr = $snr,
                    r.source_node_id = $source_node_id,
                    r.target_strategy = $target_strategy
                ON MATCH SET r.weight = 1, r.snr = $snr,
                    r.source_node_id = $source_node_id,
                    r.target_strategy = $target_strategy
                """,
                **params,
            )

    if not quiet:
        logger.info(
            "add_traceroute_edges: pushed %d edges for AutoTraceRoute %s",
            len(valid_edges),
            auto_tr.id,
        )


def clear_all_routed_to_edges(driver=None) -> int:
    """
    Delete every ROUTED_TO relationship in Neo4j. Returns the number deleted.

    Intended for bulk backfill workflows (``export_traceroutes_to_neo4j --clear``)
    where an operator wants a clean slate before re-exporting the full history.
    Nodes are left untouched - they'll be re-upserted by the subsequent export.
    """
    driver = driver or get_driver()
    logger.warning("clear_all_routed_to_edges: deleting ALL ROUTED_TO relationships")
    with driver.session() as session:
        result = session.run("""
            MATCH ()-[r:ROUTED_TO]->()
            WITH r
            DELETE r
            RETURN count(r) AS deleted
            """)
        record = result.single()
        deleted = record["deleted"] if record else 0
    logger.info("clear_all_routed_to_edges: deleted %d ROUTED_TO relationships", deleted)
    return int(deleted or 0)


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

    with tqdm(total=total, unit="tr", desc="Exporting to Neo4j") as pbar:
        for offset in range(0, total, batch_size):
            batch = list(qs[offset : offset + batch_size])
            for auto_tr in batch:
                try:
                    add_traceroute_edges(auto_tr, driver=driver, quiet=True)
                    exported += 1
                except Exception as e:
                    logger.exception(
                        "export_all_traceroutes_to_neo4j: failed for AutoTraceRoute %s: %s",
                        auto_tr.id,
                        e,
                    )
                pbar.update(1)

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
    edge_metric="packets",
    source_node_id=None,
    target_strategy_tokens=None,
    driver=None,
):
    """
    Query Neo4j for aggregated heatmap edges (bidirectional) and nodes.
    Returns dict with edges, nodes, and meta.

    edge_metric: "packets" (default) - edges colored by sum of packet count; "snr" - by avg link quality.

    ``target_strategy_tokens``: optional list of strategy keys and/or ``legacy`` for null strategy rows.
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

    if source_node_id is not None:
        where_clauses.append("r.source_node_id = $source_node_id")
        params["source_node_id"] = int(source_node_id)

    if target_strategy_tokens:
        names = {t.strip() for t in target_strategy_tokens if t and str(t).strip()}
        legacy_labels = {"legacy", AutoTraceRoute.TARGET_STRATEGY_LEGACY}
        inc_legacy = bool(names & legacy_labels)
        names -= legacy_labels
        strat_parts = []
        if inc_legacy:
            strat_parts.append("(r.target_strategy IS NULL OR r.target_strategy = $legacy_marker)")
            params["legacy_marker"] = AutoTraceRoute.TARGET_STRATEGY_LEGACY
        if names:
            strat_parts.append("r.target_strategy IN $heatmap_strategy_names")
            params["heatmap_strategy_names"] = list(names)
        if strat_parts:
            where_clauses.append("(" + " OR ".join(strat_parts) + ")")

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

    # Bidirectional: use canonical direction (a.node_id < b.node_id)
    # packets: sum(weight); snr: also avg(snr) for link quality
    agg = "sum(r.weight) AS weight"
    ret_extra = ""
    if edge_metric == "snr":
        agg += ", avg(r.snr) AS avg_snr"
        ret_extra = ", avg_snr"

    query = f"""
    MATCH (a:MeshNode)-[r:ROUTED_TO]-(b:MeshNode)
    WHERE {where_str}
    WITH a, b, {agg}
    WHERE a.node_id < b.node_id
    RETURN a.node_id AS from_node_id,
           a.latitude AS from_lat, a.longitude AS from_lng,
           a.node_id_str AS from_node_id_str,
           a.short_name AS from_short_name, a.long_name AS from_long_name,
           b.node_id AS to_node_id,
           b.latitude AS to_lat, b.longitude AS to_lng,
           b.node_id_str AS to_node_id_str,
           b.short_name AS to_short_name, b.long_name AS to_long_name,
           weight{ret_extra}
    """

    edges = []
    nodes_by_id = {}

    with driver.session() as session:
        result = session.run(query, params)
        for record in result:
            from_id = record["from_node_id"]
            to_id = record["to_node_id"]
            edge_data = {
                "from_node_id": from_id,
                "to_node_id": to_id,
                "from_lat": record["from_lat"],
                "from_lng": record["from_lng"],
                "to_lat": record["to_lat"],
                "to_lng": record["to_lng"],
                "weight": record["weight"],
            }

            if edge_metric == "snr":
                # Directly read projected value when we're in the snr query path.
                try:
                    avg_snr_raw = record["avg_snr"]
                except Exception:
                    avg_snr_raw = None

                if avg_snr_raw is not None:
                    edge_data["avg_snr"] = float(avg_snr_raw)
            edges.append(edge_data)
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
    if nodes:
        _enrich_heatmap_nodes(nodes, edges)

    # Meta: approximate counts (from Django for total TR, from Neo4j for nodes)
    from django.db.models import Q

    tr_q = AutoTraceRoute.objects.filter(status=AutoTraceRoute.STATUS_COMPLETED)
    if triggered_at_after:
        tr_q = tr_q.filter(triggered_at__gte=triggered_at_after)
    if source_node_id is not None:
        tr_q = tr_q.filter(source_node__node_id=source_node_id)
    if target_strategy_tokens:
        tok = [t.strip() for t in target_strategy_tokens if t and str(t).strip()]
        strat_q = Q()
        legacy_labels = {"legacy", AutoTraceRoute.TARGET_STRATEGY_LEGACY}
        any_legacy = bool(set(tok) & legacy_labels)
        rest = [t for t in tok if t not in legacy_labels]
        if any_legacy:
            strat_q |= Q(target_strategy__isnull=True) | Q(target_strategy=AutoTraceRoute.TARGET_STRATEGY_LEGACY)
        for s in rest:
            strat_q |= Q(target_strategy=s)
        tr_q = tr_q.filter(strat_q)

    total_tr = tr_q.count()

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
