import json
import math
import re

import networkx as nx

EARTH_R_M = 6371000.0


def project_point_to_segment(
    lat: float,
    lon: float,
    lat_a: float,
    lon_a: float,
    lat_b: float,
    lon_b: float,
) -> tuple[float, float, float, float]:
    """Perpendicular foot of point P on the (infinite) line through A-B.

    Uses a local equirectangular plane centred at A, accurate enough at
    airport scale (segments of tens to hundreds of metres).

    Returns (foot_lat, foot_lon, perp_dist_m, t) where t is the along-track
    parameter: t=0 at A, t=1 at B. t is NOT clamped — t<0 / t>1 means the
    foot falls beyond an endpoint; the caller decides whether to extend the
    segment ("prolong the line") or clamp to it.
    """
    cos_lat = math.cos(math.radians((lat_a + lat) / 2.0))
    px = math.radians(lon - lon_a) * cos_lat * EARTH_R_M
    py = math.radians(lat - lat_a) * EARTH_R_M
    bx = math.radians(lon_b - lon_a) * cos_lat * EARTH_R_M
    by = math.radians(lat_b - lat_a) * EARTH_R_M

    seg_len_sq = bx * bx + by * by
    if seg_len_sq < 1e-9:
        # Degenerate zero-length segment: the foot is A itself.
        dx = math.hypot(px, py)
        return lat_a, lon_a, dx, 0.0

    t = (px * bx + py * by) / seg_len_sq
    foot_x = t * bx
    foot_y = t * by
    perp_dist = math.hypot(px - foot_x, py - foot_y)
    foot_lat = lat_a + math.degrees(foot_y / EARTH_R_M)
    foot_lon = lon_a + math.degrees(foot_x / (cos_lat * EARTH_R_M))
    return foot_lat, foot_lon, perp_dist, t


class AirportGraph:
    """Create a directed graph to get shortest routes in an airport"""

    def __init__(self, json_file_path: str = None, data: dict = None):
        """
        Build the graph from either a JSON file or an already-parsed dict.

        Args:
            json_file_path: Path to a {ICAO}_graph.json file produced by
                plugins.GND.data_parser.parse_airport.
            data: Already-parsed dict (same schema as the JSON file). When
                provided, json_file_path is ignored. This is the path used
                when the data comes from Redis (AirportDataStore.load()).
        """
        if data is not None:
            self.data = data
        elif json_file_path is not None:
            self.data = self._load_json_data(json_file_path)
        else:
            raise ValueError("Either json_file_path or data must be provided")

        self.graph = nx.DiGraph()
        # Lookup indices populated in _build_graph
        self._nodes_by_name: dict[str, list[str]] = {}
        self._nodes_by_taxiway: dict[str, list[str]] = {}
        self._edges_by_taxiway: dict[str, set[tuple[str, str]]] = {}
        self._stands_by_id: dict[str, dict] = {}
        self._runways_by_id: dict[str, tuple[float, float]] = {}

        self._build_graph()

    def _load_json_data(self, json_file_path: str) -> dict:
        with open(json_file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points using Haversine formula (meters)"""
        R = 6371000

        lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
        delta_lat, delta_lon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)

        a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    def _build_graph(self):
        """Build the navigation graph from JSON data"""
        print("Building airport graph...")

        # Create nodes dictionary
        nodes_dict = {str(node["node_id"]): node for node in self.data.get("nodes", [])}

        # Add nodes to graph
        for node in self.data.get("nodes", []):
            node_id = str(node["node_id"])
            self.graph.add_node(node_id, **node)

            # Index by name (case-insensitive). Names are not unique.
            name = node.get("name")
            if name:
                key = name.lower()
                self._nodes_by_name.setdefault(key, []).append(node_id)

        # Add edges to graph
        for edge in self.data.get("edges", []):
            start_id = str(edge["start_node_id"])
            end_id = str(edge["end_node_id"])

            if start_id in nodes_dict and end_id in nodes_dict:
                start_node = nodes_dict[start_id]
                end_node = nodes_dict[end_id]

                distance = self._calculate_distance(
                    start_node["lat"], start_node["lon"], end_node["lat"], end_node["lon"]
                )

                direction = edge.get("direction", "twoway").lower()

                # Add edge(s) based on direction
                if direction == "twoway":
                    self.graph.add_edge(start_id, end_id, weight=distance, **edge)
                    self.graph.add_edge(end_id, start_id, weight=distance, **edge)
                else:  # oneway
                    self.graph.add_edge(start_id, end_id, weight=distance, **edge)

                # Index nodes by taxiway_id (uppercased) for via-point resolution
                taxiway_id = edge.get("taxiway_id")
                if taxiway_id:
                    key = str(taxiway_id).upper()
                    bucket = self._nodes_by_taxiway.setdefault(key, [])
                    if start_id not in bucket:
                        bucket.append(start_id)
                    if end_id not in bucket:
                        bucket.append(end_id)
                    # Index directed edges by taxiway_id for strict routing
                    # (both directions for twoway, matching the edges added above)
                    edge_bucket = self._edges_by_taxiway.setdefault(key, set())
                    edge_bucket.add((start_id, end_id))
                    if direction == "twoway":
                        edge_bucket.add((end_id, start_id))

        # Index stands by a normalised stand_id string. The parser stores
        # stand_id as a Python list-literal string ("['Gate', '224']") so we
        # strip brackets/quotes/commas and uppercase, then do substring lookup.
        for stand in self.data.get("stands", []):
            sid_raw = stand.get("stand_id", "")
            sid_clean = re.sub(r"[\[\]',]", " ", str(sid_raw)).upper()
            sid_clean = " ".join(sid_clean.split())
            if sid_clean:
                self._stands_by_id[sid_clean] = stand

        # Index runway thresholds by their designator
        for runway in self.data.get("runways", []):
            r1 = str(runway.get("runway_1_id", "")).upper()
            r2 = str(runway.get("runway_2_id", "")).upper()
            if r1:
                self._runways_by_id[r1] = (runway["lat"], runway["lon"])
            if r2:
                self._runways_by_id[r2] = (runway["lat_2"], runway["lon_2"])

        # Compute the main (largest) weakly-connected component. Real-world
        # apt.dat files often contain orphan stand-area nodes; snapping a
        # stand to such a node yields a "no path" error. We'll prefer nodes
        # in the main component when snapping coordinates.
        if self.graph.number_of_nodes() > 0:
            components = list(nx.weakly_connected_components(self.graph))
            self._main_cc: set = max(components, key=len)
        else:
            self._main_cc = set()

        print(
            f"Graph built: {self.graph.number_of_nodes()} nodes, "
            f"{self.graph.number_of_edges()} edges, "
            f"{len(self._nodes_by_taxiway)} taxiways, "
            f"{len(self._stands_by_id)} stands, "
            f"{len(self._runways_by_id)} runway ends"
        )

    def find_nearest_node(
        self,
        target_lat: float,
        target_lon: float,
        max_distance: float = 1000.0,
        restrict_to_main_cc: bool = False,
    ):
        """Find the nearest node to given coordinates.

        Args:
            target_lat, target_lon: Point to snap.
            max_distance: Reject candidates farther than this (metres).
            restrict_to_main_cc: When True, only consider nodes that belong
                to the largest weakly-connected component. Useful when
                snapping a stand or runway threshold so the resulting node
                is reachable from the rest of the taxi network.
        """
        min_distance = float("inf")
        nearest_node = None

        candidates = self._main_cc if restrict_to_main_cc else self.graph.nodes()
        for node_id in candidates:
            node = self.graph.nodes[node_id]
            distance = self._calculate_distance(target_lat, target_lon, node["lat"], node["lon"])

            if distance < min_distance and distance <= max_distance:
                min_distance = distance
                nearest_node = node_id

        return (nearest_node, min_distance) if nearest_node else (None, None)

    def find_shortest_path(
        self, start_lat: float, start_lon: float, end_lat: float, end_lon: float, max_search_distance: float = 1000.0
    ):
        """Find shortest path between two coordinates"""
        # Find nearest nodes
        start_node, start_dist = self.find_nearest_node(start_lat, start_lon, max_search_distance)
        end_node, end_dist = self.find_nearest_node(end_lat, end_lon, max_search_distance)

        if not start_node:
            return {"error": f"No node found near start coordinates within {max_search_distance}m"}

        if not end_node:
            return {"error": f"No node found near end coordinates within {max_search_distance}m"}

        try:
            # Calculate shortest path
            path = nx.shortest_path(self.graph, start_node, end_node, weight="weight")
            total_distance = nx.shortest_path_length(self.graph, start_node, end_node, weight="weight")

            # Get taxiway sequence
            taxiways = []
            for i in range(len(path) - 1):
                edge_data = self.graph.edges[path[i], path[i + 1]]
                taxiway = edge_data.get("taxiway_id", "Unknown")
                if taxiway not in taxiways:
                    taxiways.append(taxiway)

            return {
                "success": True,
                "path": path,
                "total_distance": total_distance + start_dist + end_dist,
                "taxiway_sequence": " → ".join(taxiways),
                "start_node": start_node,
                "end_node": end_node,
            }

        except nx.NetworkXNoPath:
            return {"error": f"No route found between nodes {start_node} and {end_node}"}
        except Exception as e:
            return {"error": f"Error calculating route: {str(e)}"}

    def _astar(self, start_node_id: str, end_node_id: str) -> list:
        """A* over the taxi graph using a Haversine heuristic.

        Edge weights are already great-circle distances in metres, so the
        Haversine heuristic is admissible and consistent — A* yields the
        same optimal path as Dijkstra but explores fewer nodes on large
        airports.
        """

        def heuristic(u: str, v: str) -> float:
            nu = self.graph.nodes[u]
            nv = self.graph.nodes[v]
            return self._calculate_distance(nu["lat"], nu["lon"], nv["lat"], nv["lon"])

        return nx.astar_path(
            self.graph,
            start_node_id,
            end_node_id,
            heuristic=heuristic,
            weight="weight",
        )

    def taxiway_subgraph(self, taxiway_id: str) -> nx.DiGraph:
        """Read-only view of the graph restricted to the edges of one taxiway.

        Returns a networkx subgraph view containing only the directed edges
        whose ``taxiway_id`` matches (case-insensitive). Used by strict
        routing to keep A* on the authorized taxiway.
        """
        key = str(taxiway_id).upper()
        edges = self._edges_by_taxiway.get(key, set())
        return nx.subgraph_view(
            self.graph,
            filter_edge=lambda u, v: (u, v) in edges,
        )

    def taxiway_intersections(self, tw_a: str, tw_b: str) -> list:
        """Node ids where taxiways ``tw_a`` and ``tw_b`` meet.

        A node is an intersection when it is an endpoint of at least one
        edge of each taxiway. Returns [] when the taxiways do not touch or
        either is unknown.
        """

        def endpoints(tw: str) -> set:
            edges = self._edges_by_taxiway.get(str(tw).upper(), set())
            nodes: set = set()
            for u, v in edges:
                nodes.add(u)
                nodes.add(v)
            return nodes

        return sorted(endpoints(tw_a) & endpoints(tw_b))

    def _find_nearest_via_start(self, start_lat: float, start_lon: float, via: list) -> tuple:
        """Return (via_idx, node_id) of the via-point node closest to (start_lat, start_lon).

        Iterates every node that belongs to any taxiway in ``via`` and returns
        the (list-index, node_id) pair with minimum haversine distance to the
        given position. This determines which via-point the aircraft is closest
        to so earlier ones can be skipped without backtracking.
        """
        best_dist = float("inf")
        best_idx = 0
        best_node = None
        for i, tw in enumerate(via):
            key = str(tw).upper()
            for nid in self._nodes_by_taxiway.get(key, []):
                n = self.graph.nodes[nid]
                d = self._calculate_distance(start_lat, start_lon, n["lat"], n["lon"])
                if d < best_dist:
                    best_dist, best_idx, best_node = d, i, nid
        return best_idx, best_node

    def _pick_node_by_distance(self, candidates: list, hint_lat, hint_lon) -> str:
        """Return the node id (from candidates) closest to the hint, or the
        first candidate if no hint is provided."""
        if hint_lat is None or hint_lon is None:
            return candidates[0]
        return min(
            candidates,
            key=lambda nid: self._calculate_distance(
                hint_lat,
                hint_lon,
                self.graph.nodes[nid]["lat"],
                self.graph.nodes[nid]["lon"],
            ),
        )

    def _pick_via_node_on_taxiway(self, taxiway_name: str, from_lat: float, from_lon: float):
        """Pick the node on the given taxiway that is closest to (from_lat, from_lon).
        Prefers nodes in the main connected component when any are available."""
        key = str(taxiway_name).upper()
        candidates = self._nodes_by_taxiway.get(key)
        if not candidates:
            return None
        in_main = [nid for nid in candidates if nid in self._main_cc]
        return self._pick_node_by_distance(in_main or candidates, from_lat, from_lon)

    def resolve_point(self, token: str, hint_lat=None, hint_lon=None):
        """Resolve a controller-spoken token to a (node_id, lat, lon) tuple.

        Resolution order:
            1. Runway designator    (e.g. "06R", "24L")
            2. Taxiway letter       (e.g. "B", "G10", "D5")
            3. Stand identifier     (e.g. "Gate 224", "224", "Ramp 175")
            4. Node name            (case-insensitive exact match)

        Returns None if nothing matches.
        """
        if not token:
            return None
        t = str(token).strip()
        if not t:
            return None
        t_upper = t.upper()

        # 0. Direct node_id — allows find_route_from_position to bypass token resolution
        if t in self.graph.nodes:
            n = self.graph.nodes[t]
            return (t, n["lat"], n["lon"])

        # 1. Runway threshold
        if t_upper in self._runways_by_id:
            lat, lon = self._runways_by_id[t_upper]
            node_id, _dist = self.find_nearest_node(
                lat,
                lon,
                max_distance=2000.0,
                restrict_to_main_cc=True,
            )
            if node_id:
                n = self.graph.nodes[node_id]
                return (node_id, n["lat"], n["lon"])

        # 2. Taxiway letter
        if t_upper in self._nodes_by_taxiway:
            best = self._pick_node_by_distance(
                self._nodes_by_taxiway[t_upper],
                hint_lat,
                hint_lon,
            )
            n = self.graph.nodes[best]
            return (best, n["lat"], n["lon"])

        # 3. Stand identifier (substring match against the cleaned-up stand_id)
        for sid_clean, stand in self._stands_by_id.items():
            if t_upper in sid_clean:
                node_id, _dist = self.find_nearest_node(
                    stand["latitude"],
                    stand["longitude"],
                    max_distance=2000.0,
                    restrict_to_main_cc=True,
                )
                if node_id:
                    n = self.graph.nodes[node_id]
                    return (node_id, n["lat"], n["lon"])

        # 4. Node name
        candidates = self._nodes_by_name.get(t.lower())
        if candidates:
            best = self._pick_node_by_distance(candidates, hint_lat, hint_lon)
            n = self.graph.nodes[best]
            return (best, n["lat"], n["lon"])

        return None

    def find_route_via(
        self,
        start_token: str,
        end_token: str,
        via: list = None,
        hint_lat: float = None,
        hint_lon: float = None,
    ) -> dict:
        """Compute a taxi route between two controller-spoken tokens, optionally
        forced through a list of intermediate taxiways/points.

        The path is forced through every via point in order; within each leg,
        A* picks the fastest route.
        """
        # Resolve start
        start = self.resolve_point(start_token, hint_lat, hint_lon)
        if start is None:
            return {"success": False, "error": f"Could not resolve start token: {start_token!r}"}

        # Resolve end (anchor disambiguation to start position)
        end = self.resolve_point(end_token, start[1], start[2])
        if end is None:
            return {"success": False, "error": f"Could not resolve end token: {end_token!r}"}

        # Find the nearest via-point to the start and skip earlier ones so the
        # aircraft never needs to backtrack in mid-taxi re-routing scenarios.
        via_list = list(via or [])
        if via_list:
            start_idx, nearest_node_id = self._find_nearest_via_start(start[1], start[2], via_list)
            remaining_via = via_list[start_idx:]
        else:
            remaining_via = []
            nearest_node_id = None

        # Build resolved waypoint sequence starting from the nearest via-point.
        resolved = [start]
        cur_lat, cur_lon = start[1], start[2]

        if nearest_node_id is not None and nearest_node_id != start[0]:
            n = self.graph.nodes[nearest_node_id]
            resolved.append((nearest_node_id, n["lat"], n["lon"]))
            cur_lat, cur_lon = n["lat"], n["lon"]

        for v in remaining_via[1:]:  # remaining via-points after the nearest
            node_id = self._pick_via_node_on_taxiway(v, cur_lat, cur_lon)
            if node_id is not None:
                n = self.graph.nodes[node_id]
                resolved.append((node_id, n["lat"], n["lon"]))
            else:
                r = self.resolve_point(v, cur_lat, cur_lon)
                if r is None:
                    return {"success": False, "error": f"Could not resolve via point: {v!r}"}
                resolved.append(r)
            cur_lat, cur_lon = resolved[-1][1], resolved[-1][2]

        resolved.append(end)

        # Stitch legs with unconstrained A* (shortest path between each pair).
        full_path: list = []
        total_distance = 0.0
        for i in range(len(resolved) - 1):
            a = resolved[i][0]
            b = resolved[i + 1][0]
            if a == b:
                continue
            try:
                leg = self._astar(a, b)
            except nx.NetworkXNoPath:
                return {
                    "success": False,
                    "error": f"No path from node {a!r} to node {b!r}",
                }
            except nx.NodeNotFound as e:
                return {"success": False, "error": f"Node not in graph: {e}"}
            if not full_path:
                full_path.extend(leg)
            else:
                full_path.extend(leg[1:])  # avoid duplicating the join node
            for j in range(len(leg) - 1):
                edge = self.graph.edges[leg[j], leg[j + 1]]
                total_distance += edge.get("weight", 0.0)

        if not full_path:
            # start == end and no via points -> trivial single-node path
            full_path = [resolved[0][0]]

        # Build waypoint list and taxiway sequence
        waypoints = []
        taxiway_sequence: list = []
        for i, nid in enumerate(full_path):
            n = self.graph.nodes[nid]
            waypoints.append(
                {
                    "node_id": nid,
                    "lat": n["lat"],
                    "lon": n["lon"],
                    "name": n.get("name", ""),
                }
            )
            if i < len(full_path) - 1:
                edge = self.graph.edges[nid, full_path[i + 1]]
                tw = edge.get("taxiway_id")
                if tw and (not taxiway_sequence or taxiway_sequence[-1] != tw):
                    taxiway_sequence.append(tw)

        return {
            "success": True,
            "path_node_ids": full_path,
            "waypoints": waypoints,
            "taxiway_sequence": taxiway_sequence,
            "total_distance_m": round(total_distance, 1),
            "start": {
                "node_id": start[0],
                "lat": start[1],
                "lon": start[2],
                "token": start_token,
            },
            "end": {
                "node_id": end[0],
                "lat": end[1],
                "lon": end[2],
                "token": end_token,
            },
        }

    # Maximum length of the unconstrained hop from the last taxiway to a
    # destination that is not on it (e.g. a runway threshold node). Longer
    # hops mean the strict route would leave the authorized sequence for a
    # significant distance, so we fail instead.
    MAX_EXIT_HOP_M = 1000.0

    # Maximum perpendicular distance from the aircraft position to the first
    # authorized taxiway's centerline. Beyond this the strict route fails
    # ("unable to reach taxiway X") instead of wandering across the graph.
    MAX_ENTRY_JOIN_M = 500.0

    # How far a taxiway segment may be prolonged beyond its endpoint when the
    # perpendicular foot falls past the segment end, so the aircraft still
    # joins the taxiway line straight instead of cutting diagonally to a node.
    MAX_ENTRY_EXTENSION_M = 150.0

    def _dijkstra_to_nearest(self, graph, source: str, targets: set):
        """Shortest path from ``source`` to the closest reachable node of
        ``targets`` within ``graph``. Returns (path, distance) or (None, None)
        when no target is reachable."""
        if source in targets:
            return [source], 0.0
        try:
            lengths = nx.single_source_dijkstra_path_length(
                graph,
                source,
                weight="weight",
            )
        except nx.NodeNotFound:
            return None, None
        reachable = [t for t in targets if t in lengths]
        if not reachable:
            return None, None
        best = min(reachable, key=lambda t: lengths[t])
        return nx.dijkstra_path(graph, source, best, weight="weight"), lengths[best]

    def _join_taxiway_entry(self, lat: float, lon: float, taxiway: str, targets: set):
        """Straight centerline join onto ``taxiway`` from a raw position.

        Projects (lat, lon) perpendicularly onto each directed edge of the
        taxiway; the foot may be prolonged up to MAX_ENTRY_EXTENSION_M beyond
        a segment endpoint so the aircraft still joins the taxiway line
        straight instead of cutting diagonally to a node. A candidate edge is
        feasible when driving toward its end node can reach one of ``targets``
        along the taxiway itself (this also rejects wrong-way one-way edges
        and disconnected segments that share the taxiway name). Candidates
        are ranked by perpendicular join distance first — the aircraft always
        joins the geometrically nearest feasible stretch of the taxiway, never
        a farther one that would shorten the total path — and the driving
        direction along the taxiway is the tie-breaker (along-track + leg to
        the nearest target).

        Returns {"foot": (lat, lon), "entry_node": node_id,
        "entry_dist_m": float, "along_m": float} or None when no feasible
        edge lies within MAX_ENTRY_JOIN_M.
        """
        key = str(taxiway).upper()
        edges = self._edges_by_taxiway.get(key, set())
        if not edges or not targets:
            return None
        sub = self.taxiway_subgraph(key)
        try:
            dist_to_target = nx.multi_source_dijkstra_path_length(
                sub.reverse(copy=False),
                set(targets),
                weight="weight",
            )
        except nx.NodeNotFound:
            return None

        best = None
        for u, v in edges:
            nu, nv = self.graph.nodes[u], self.graph.nodes[v]
            seg_len = self.graph.edges[u, v].get("weight", 0.0)
            if seg_len <= 0.0:
                continue
            _f_lat, _f_lon, _perp, t = project_point_to_segment(
                lat,
                lon,
                nu["lat"],
                nu["lon"],
                nv["lat"],
                nv["lon"],
            )
            ext = self.MAX_ENTRY_EXTENSION_M / seg_len
            t = max(-ext, min(1.0 + ext, t))
            join_lat = nu["lat"] + t * (nv["lat"] - nu["lat"])
            join_lon = nu["lon"] + t * (nv["lon"] - nu["lon"])
            entry_dist = self._calculate_distance(lat, lon, join_lat, join_lon)
            if entry_dist > self.MAX_ENTRY_JOIN_M:
                continue
            # Driving toward v, the first node crossed is u when the foot
            # lies on the prolongation before u, otherwise v.
            entry_node = u if t <= 0.0 else v
            if entry_node not in dist_to_target:
                continue
            en = self.graph.nodes[entry_node]
            along = self._calculate_distance(join_lat, join_lon, en["lat"], en["lon"])
            # Rank: nearest feasible stretch first, then cheapest continuation,
            # then the entry node closest to the foot (breaks the tie between
            # collinear segments whose prolongations claim the same foot).
            # Distances are quantized to 0.1 m so float noise between
            # collinear candidates cannot mask the tie-breakers.
            cost = (
                round(entry_dist, 1),
                round(along + dist_to_target[entry_node], 1),
                along,
            )
            if best is None or cost < best[0]:
                best = (
                    cost,
                    {
                        "foot": (join_lat, join_lon),
                        "entry_node": entry_node,
                        "entry_dist_m": entry_dist,
                        "along_m": along,
                    },
                )
        return best[1] if best else None

    def find_route_strict(
        self,
        start_token: str,
        sequence: list,
        destination_token: str,
    ) -> dict:
        """Compute a taxi route that follows the controller-issued taxiway
        ``sequence`` strictly, in order, using only edges of the authorized
        taxiways (issue #67).

        Unlike find_route_via (which treats vias as soft waypoints and
        stitches legs with unconstrained A*), each leg here is restricted to
        the subgraph of the taxiway being traversed. Joining the first
        taxiway is a straight perpendicular hop onto its centerline
        (_join_taxiway_entry), and only one bounded hop may leave the
        sequence: from the last taxiway to an off-taxiway destination (e.g.
        a runway threshold node). No via is ever skipped; unknown or
        non-connected taxiways fail instead of degrading silently.
        """
        start = self.resolve_point(start_token)
        if start is None:
            return {"success": False, "error": f"Could not resolve start token: {start_token!r}"}
        return self._route_strict_core(
            sequence,
            destination_token,
            start_lat=start[1],
            start_lon=start[2],
            start_node=start[0],
            start_meta={
                "node_id": start[0],
                "lat": start[1],
                "lon": start[2],
                "token": start_token,
            },
        )

    def _route_strict_core(
        self,
        sequence: list,
        destination_token: str,
        *,
        start_lat: float,
        start_lon: float,
        start_node,
        start_meta: dict,
    ) -> dict:
        """Shared core of find_route_strict / find_route_strict_from_position.

        ``start_node`` is the node the aircraft is standing on, or None when
        routing from a raw position; when it is None or not on the first
        authorized taxiway, the entry is a straight perpendicular join onto
        that taxiway's centerline instead of a graph search.
        """
        # Collapse consecutive duplicates ("A A B" -> "A B"); non-adjacent
        # repeats are legitimate and preserved.
        seq: list[str] = []
        for tw in sequence or []:
            key = str(tw).upper()
            if not seq or seq[-1] != key:
                seq.append(key)
        if not seq:
            return {"success": False, "error": "empty taxiway sequence"}

        for tw in seq:
            if tw not in self._edges_by_taxiway:
                return {"success": False, "error": f"unknown taxiway '{tw}'"}

        end = self.resolve_point(destination_token, start_lat, start_lon)
        if end is None:
            return {"success": False, "error": f"Could not resolve end token: {destination_token!r}"}

        def tw_nodes(tw: str) -> set:
            return {n for uv in self._edges_by_taxiway[tw] for n in uv}

        # Entry: no hop at all when already standing on a node of the first
        # taxiway; otherwise project the position perpendicularly onto the
        # first taxiway's centerline and join it straight there. Never a
        # graph search — beyond MAX_ENTRY_JOIN_M the route fails instead.
        entry_wp = None
        entry_dist = 0.0
        entry_along = 0.0
        if start_node is not None and start_node in tw_nodes(seq[0]):
            cur = start_node
        else:
            if len(seq) > 1:
                targets = set(self.taxiway_intersections(seq[0], seq[1]))
                if not targets:
                    return {
                        "success": False,
                        "error": f"taxiway sequence not connected: {seq[0]} -> {seq[1]}",
                    }
            elif end[0] in tw_nodes(seq[0]):
                targets = {end[0]}
            else:
                targets = {
                    min(
                        tw_nodes(seq[0]),
                        key=lambda n: self._calculate_distance(
                            self.graph.nodes[n]["lat"],
                            self.graph.nodes[n]["lon"],
                            end[1],
                            end[2],
                        ),
                    )
                }
            join = self._join_taxiway_entry(start_lat, start_lon, seq[0], targets)
            if join is None:
                return {
                    "success": False,
                    "error": f"no path from start to taxiway '{seq[0]}'",
                }
            entry_wp = {
                "node_id": "entry",
                "lat": join["foot"][0],
                "lon": join["foot"][1],
                "name": f"{seq[0]} entry",
            }
            entry_dist = join["entry_dist_m"]
            entry_along = join["along_m"]
            cur = join["entry_node"]

        full_path: list = [cur]

        # Middle legs: travel along T[i] (edges of T[i] only) to a real
        # intersection with T[i+1].
        for i in range(len(seq) - 1):
            here, nxt = seq[i], seq[i + 1]
            crossings = set(self.taxiway_intersections(here, nxt))
            if not crossings:
                return {
                    "success": False,
                    "error": f"taxiway sequence not connected: {here} -> {nxt}",
                }
            leg_path, _dist = self._dijkstra_to_nearest(
                self.taxiway_subgraph(here),
                cur,
                crossings,
            )
            if leg_path is None:
                return {
                    "success": False,
                    "error": f"taxiway sequence not connected: {here} -> {nxt}",
                }
            full_path.extend(leg_path[1:])
            cur = full_path[-1]

        # Final leg: along the last taxiway to its node closest to the
        # destination, then (if needed) a short bounded exit hop.
        last = seq[-1]
        last_sub = self.taxiway_subgraph(last)
        last_nodes = tw_nodes(last)
        if end[0] in last_nodes:
            leg_path, _dist = self._dijkstra_to_nearest(last_sub, cur, {end[0]})
            if leg_path is None:
                return {
                    "success": False,
                    "error": f"destination not reachable along taxiway '{last}'",
                }
            full_path.extend(leg_path[1:])
        else:
            try:
                lengths = nx.single_source_dijkstra_path_length(
                    last_sub,
                    cur,
                    weight="weight",
                )
            except nx.NodeNotFound:
                lengths = {cur: 0.0}
            reachable = set(lengths) & last_nodes | {cur}
            exit_node = min(
                reachable,
                key=lambda n: self._calculate_distance(
                    self.graph.nodes[n]["lat"],
                    self.graph.nodes[n]["lon"],
                    end[1],
                    end[2],
                ),
            )
            if exit_node != cur:
                leg_path = nx.dijkstra_path(last_sub, cur, exit_node, weight="weight")
                full_path.extend(leg_path[1:])
            # Bounded unconstrained hop off the last taxiway to the destination
            if exit_node != end[0]:
                try:
                    hop = self._astar(exit_node, end[0])
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    return {
                        "success": False,
                        "error": f"no path from taxiway '{last}' to destination",
                    }
                hop_dist = sum(self.graph.edges[hop[j], hop[j + 1]].get("weight", 0.0) for j in range(len(hop) - 1))
                if hop_dist > self.MAX_EXIT_HOP_M:
                    return {
                        "success": False,
                        "error": (
                            f"destination too far from taxiway '{last}' ({hop_dist:.0f}m off the authorized sequence)"
                        ),
                    }
                full_path.extend(hop[1:])

        # Build waypoints, taxiway sequence and total distance (same shape
        # as find_route_via so router/mover consume it unchanged). The
        # synthetic entry waypoint (centerline join point) is prepended to
        # the waypoints only — path_node_ids stays graph-nodes-only.
        total_distance = entry_along + sum(
            self.graph.edges[full_path[j], full_path[j + 1]].get("weight", 0.0) for j in range(len(full_path) - 1)
        )
        waypoints = []
        taxiway_sequence: list = []
        for i, nid in enumerate(full_path):
            n = self.graph.nodes[nid]
            waypoints.append(
                {
                    "node_id": nid,
                    "lat": n["lat"],
                    "lon": n["lon"],
                    "name": n.get("name", ""),
                }
            )
            if i < len(full_path) - 1:
                edge = self.graph.edges[nid, full_path[i + 1]]
                tw = edge.get("taxiway_id")
                if tw and (not taxiway_sequence or taxiway_sequence[-1] != tw):
                    taxiway_sequence.append(tw)
        if entry_wp is not None:
            waypoints.insert(0, entry_wp)

        return {
            "success": True,
            "strict": True,
            "path_node_ids": full_path,
            "waypoints": waypoints,
            "taxiway_sequence": taxiway_sequence,
            "total_distance_m": round(total_distance, 1),
            "entry_distance_m": round(entry_dist, 1),
            "start": start_meta,
            "end": {
                "node_id": end[0],
                "lat": end[1],
                "lon": end[2],
                "token": destination_token,
            },
        }

    def find_route_strict_from_position(
        self,
        start_lat: float,
        start_lon: float,
        sequence: list,
        destination_token: str,
    ) -> dict:
        """Strict route from a raw GPS coordinate (issue #67).

        The raw position is NOT snapped to a node for routing: the entry to
        the first authorized taxiway is a perpendicular projection onto its
        centerline (_join_taxiway_entry), so the aircraft joins the taxiway
        straight instead of cutting diagonally to the nearest node. The
        nearest main-CC node is still used as an off-movement-area guard and
        reported as ``start`` metadata.
        """
        snapped, _snap = self.find_nearest_node(
            start_lat,
            start_lon,
            max_distance=2000.0,
            restrict_to_main_cc=True,
        )
        if snapped is None:
            return {
                "success": False,
                "error": f"No connected node within 2000m of ({start_lat:.6f}, {start_lon:.6f})",
            }
        return self._route_strict_core(
            sequence,
            destination_token,
            start_lat=start_lat,
            start_lon=start_lon,
            start_node=None,
            start_meta={
                "node_id": snapped,
                "lat": start_lat,
                "lon": start_lon,
                "token": snapped,
            },
        )

    def find_route_from_position(
        self,
        start_lat: float,
        start_lon: float,
        end_token: str,
        via: list = None,
    ) -> dict:
        """Route from a raw GPS coordinate to a destination token.

        Snaps (start_lat, start_lon) to the nearest node in the main connected
        component, then delegates to find_route_via using the node_id as origin.
        Used by the orchestrator when the aircraft's real-time position is known
        but there is no explicit stand name for the origin.
        """
        start_node, _snap = self.find_nearest_node(
            start_lat,
            start_lon,
            max_distance=2000.0,
            restrict_to_main_cc=True,
        )
        if start_node is None:
            return {
                "success": False,
                "error": f"No connected node within 2000m of ({start_lat:.6f}, {start_lon:.6f})",
            }
        return self.find_route_via(
            start_token=start_node,  # resolve_point step 0 handles bare node IDs
            end_token=end_token,
            via=via,
            hint_lat=start_lat,
            hint_lon=start_lon,
        )

    def print_route(self, result):
        """Print route information in a clean format"""
        if "error" in result:
            print(f"❌ {result['error']}")
            return

        print("\nRoute found:")
        print(f"Distance: {result['total_distance']:.1f}m")
        print(f"Taxiways: {result['taxiway_sequence']}")
        print(f"Path: {result['start_node']} → {result['end_node']} ({len(result['path'])} nodes)")


if __name__ == "__main__":
    from pathlib import Path

    ICAO = "LEBL"
    BASE_DIR = Path(__file__).resolve().parents[2]
    JSON_FILE = BASE_DIR / "data" / "airport_data" / ICAO / f"{ICAO}_graph.json"

    try:
        airport = AirportGraph(str(JSON_FILE))

        # 1. Existing coordinate-based regression
        start_lat, start_lon = 41.294810, 2.079630
        end_lat, end_lon = 41.292172, 2.103167
        print(f"\n[1] Coordinate route ({start_lat}, {start_lon}) -> ({end_lat}, {end_lon})")
        airport.print_route(airport.find_shortest_path(start_lat, start_lon, end_lat, end_lon))

        # 2. End-to-end via runway designator with no intermediate via points
        print("\n[2] find_route_via('B', '06R')")
        result = airport.find_route_via("B", "06R")
        if result.get("success"):
            print(
                f"  nodes={len(result['path_node_ids'])} "
                f"distance={result['total_distance_m']}m "
                f"taxiways={result['taxiway_sequence']}"
            )
        else:
            print(f"  ERROR: {result.get('error')}")

        # 3. Via-constrained route (controller: "taxi via D, E to runway 24L")
        print("\n[3] find_route_via('B', '24L', via=['D','E'])")
        result = airport.find_route_via("B", "24L", via=["D", "E"])
        if result.get("success"):
            print(
                f"  nodes={len(result['path_node_ids'])} "
                f"distance={result['total_distance_m']}m "
                f"taxiways={result['taxiway_sequence']}"
            )
            print(f"  start={result['start']} end={result['end']}")
        else:
            print(f"  ERROR: {result.get('error')}")

    except FileNotFoundError:
        print(f"File not found: {JSON_FILE}")
    except Exception as e:
        print(f"Error: {e}")
