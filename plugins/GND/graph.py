import json
import re
import networkx as nx
import math


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
        self._stands_by_id: dict[str, dict] = {}
        self._runways_by_id: dict[str, tuple[float, float]] = {}

        self._build_graph()

    def _load_json_data(self, json_file_path: str) -> dict:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _calculate_distance(
        self, 
        lat1: float, lon1: float, 
        lat2: float, lon2: float
        ) -> float:
        """Calculate distance between two points using Haversine formula (meters)"""
        R = 6371000
        
        lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
        delta_lat, delta_lon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
        
        a = (math.sin(delta_lat/2)**2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    def _build_graph(self):
        """Build the navigation graph from JSON data"""
        print("Building airport graph...")

        # Create nodes dictionary
        nodes_dict = {str(node['node_id']): node for node in self.data.get('nodes', [])}

        # Add nodes to graph
        for node in self.data.get('nodes', []):
            node_id = str(node['node_id'])
            self.graph.add_node(node_id, **node)

            # Index by name (case-insensitive). Names are not unique.
            name = node.get('name')
            if name:
                key = name.lower()
                self._nodes_by_name.setdefault(key, []).append(node_id)

        # Add edges to graph
        for edge in self.data.get('edges', []):
            start_id = str(edge['start_node_id'])
            end_id = str(edge['end_node_id'])

            if start_id in nodes_dict and end_id in nodes_dict:
                start_node = nodes_dict[start_id]
                end_node = nodes_dict[end_id]

                distance = self._calculate_distance(
                    start_node['lat'], start_node['lon'],
                    end_node['lat'], end_node['lon']
                )

                direction = edge.get('direction', 'twoway').lower()

                # Add edge(s) based on direction
                if direction == 'twoway':
                    self.graph.add_edge(start_id, end_id, weight=distance, **edge)
                    self.graph.add_edge(end_id, start_id, weight=distance, **edge)
                else:  # oneway
                    self.graph.add_edge(start_id, end_id, weight=distance, **edge)

                # Index nodes by taxiway_id (uppercased) for via-point resolution
                taxiway_id = edge.get('taxiway_id')
                if taxiway_id:
                    key = str(taxiway_id).upper()
                    bucket = self._nodes_by_taxiway.setdefault(key, [])
                    if start_id not in bucket:
                        bucket.append(start_id)
                    if end_id not in bucket:
                        bucket.append(end_id)

        # Index stands by a normalised stand_id string. The parser stores
        # stand_id as a Python list-literal string ("['Gate', '224']") so we
        # strip brackets/quotes/commas and uppercase, then do substring lookup.
        for stand in self.data.get('stands', []):
            sid_raw = stand.get('stand_id', '')
            sid_clean = re.sub(r"[\[\]',]", " ", str(sid_raw)).upper()
            sid_clean = " ".join(sid_clean.split())
            if sid_clean:
                self._stands_by_id[sid_clean] = stand

        # Index runway thresholds by their designator
        for runway in self.data.get('runways', []):
            r1 = str(runway.get('runway_1_id', '')).upper()
            r2 = str(runway.get('runway_2_id', '')).upper()
            if r1:
                self._runways_by_id[r1] = (runway['lat'], runway['lon'])
            if r2:
                self._runways_by_id[r2] = (runway['lat_2'], runway['lon_2'])

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
        target_lat: float, target_lon: float,
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
        min_distance = float('inf')
        nearest_node = None

        candidates = self._main_cc if restrict_to_main_cc else self.graph.nodes()
        for node_id in candidates:
            node = self.graph.nodes[node_id]
            distance = self._calculate_distance(target_lat, target_lon, node['lat'], node['lon'])

            if distance < min_distance and distance <= max_distance:
                min_distance = distance
                nearest_node = node_id

        return nearest_node, min_distance if nearest_node else (None, None)
    
    def find_shortest_path(
        self, 
        start_lat: float, start_lon: float, 
        end_lat: float, end_lon: float, 
        max_search_distance: float = 1000.0
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
            path = nx.shortest_path(self.graph, start_node, end_node, weight='weight')
            total_distance = nx.shortest_path_length(self.graph, start_node, end_node, weight='weight')
            
            # Get taxiway sequence
            taxiways = []
            for i in range(len(path) - 1):
                edge_data = self.graph.edges[path[i], path[i+1]]
                taxiway = edge_data.get('taxiway_id', 'Unknown')
                if taxiway not in taxiways:
                    taxiways.append(taxiway)
            
            return {
                "success": True,
                "path": path,
                "total_distance": total_distance + start_dist + end_dist,
                "taxiway_sequence": " → ".join(taxiways),
                "start_node": start_node,
                "end_node": end_node
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
            return self._calculate_distance(nu['lat'], nu['lon'], nv['lat'], nv['lon'])

        return nx.astar_path(
            self.graph, start_node_id, end_node_id,
            heuristic=heuristic, weight='weight',
        )

    def _pick_node_by_distance(self, candidates: list, hint_lat, hint_lon) -> str:
        """Return the node id (from candidates) closest to the hint, or the
        first candidate if no hint is provided."""
        if hint_lat is None or hint_lon is None:
            return candidates[0]
        return min(
            candidates,
            key=lambda nid: self._calculate_distance(
                hint_lat, hint_lon,
                self.graph.nodes[nid]['lat'], self.graph.nodes[nid]['lon'],
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
            return (t, n['lat'], n['lon'])

        # 1. Runway threshold
        if t_upper in self._runways_by_id:
            lat, lon = self._runways_by_id[t_upper]
            node_id, _dist = self.find_nearest_node(
                lat, lon, max_distance=2000.0, restrict_to_main_cc=True,
            )
            if node_id:
                n = self.graph.nodes[node_id]
                return (node_id, n['lat'], n['lon'])

        # 2. Taxiway letter
        if t_upper in self._nodes_by_taxiway:
            best = self._pick_node_by_distance(
                self._nodes_by_taxiway[t_upper], hint_lat, hint_lon,
            )
            n = self.graph.nodes[best]
            return (best, n['lat'], n['lon'])

        # 3. Stand identifier (substring match against the cleaned-up stand_id)
        for sid_clean, stand in self._stands_by_id.items():
            if t_upper in sid_clean:
                node_id, _dist = self.find_nearest_node(
                    stand['latitude'], stand['longitude'],
                    max_distance=2000.0, restrict_to_main_cc=True,
                )
                if node_id:
                    n = self.graph.nodes[node_id]
                    return (node_id, n['lat'], n['lon'])

        # 4. Node name
        candidates = self._nodes_by_name.get(t.lower())
        if candidates:
            best = self._pick_node_by_distance(candidates, hint_lat, hint_lon)
            n = self.graph.nodes[best]
            return (best, n['lat'], n['lon'])

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

        # Resolve via points, each anchored to the previous waypoint
        resolved = [start]
        cur_lat, cur_lon = start[1], start[2]
        for v in (via or []):
            # Prefer taxiway-name resolution: pick the node on that taxiway
            # closest to where we currently are.
            node_id = self._pick_via_node_on_taxiway(v, cur_lat, cur_lon)
            if node_id is not None:
                n = self.graph.nodes[node_id]
                resolved.append((node_id, n['lat'], n['lon']))
            else:
                # Fall back to general resolution (stand, runway, node name)
                r = self.resolve_point(v, cur_lat, cur_lon)
                if r is None:
                    return {"success": False, "error": f"Could not resolve via point: {v!r}"}
                resolved.append(r)
            cur_lat, cur_lon = resolved[-1][1], resolved[-1][2]
        resolved.append(end)

        # Run A* on each leg and stitch
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
                total_distance += edge.get('weight', 0.0)

        if not full_path:
            # start == end and no via points -> trivial single-node path
            full_path = [resolved[0][0]]

        # Build waypoint list and taxiway sequence
        waypoints = []
        taxiway_sequence: list = []
        for i, nid in enumerate(full_path):
            n = self.graph.nodes[nid]
            waypoints.append({
                "node_id": nid,
                "lat": n['lat'],
                "lon": n['lon'],
                "name": n.get('name', ''),
            })
            if i < len(full_path) - 1:
                edge = self.graph.edges[nid, full_path[i + 1]]
                tw = edge.get('taxiway_id')
                if tw and (not taxiway_sequence or taxiway_sequence[-1] != tw):
                    taxiway_sequence.append(tw)

        return {
            "success": True,
            "path_node_ids": full_path,
            "waypoints": waypoints,
            "taxiway_sequence": taxiway_sequence,
            "total_distance_m": round(total_distance, 1),
            "start": {
                "node_id": start[0], "lat": start[1], "lon": start[2],
                "token": start_token,
            },
            "end": {
                "node_id": end[0], "lat": end[1], "lon": end[2],
                "token": end_token,
            },
        }

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
            start_lat, start_lon, max_distance=2000.0, restrict_to_main_cc=True,
        )
        if start_node is None:
            return {
                "success": False,
                "error": f"No connected node within 2000m of ({start_lat:.6f}, {start_lon:.6f})",
            }
        return self.find_route_via(
            start_token=start_node,   # resolve_point step 0 handles bare node IDs
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
        airport.print_route(
            airport.find_shortest_path(start_lat, start_lon, end_lat, end_lon)
        )

        # 2. End-to-end via runway designator with no intermediate via points
        print("\n[2] find_route_via('B', '06R')")
        result = airport.find_route_via("B", "06R")
        if result.get("success"):
            print(f"  nodes={len(result['path_node_ids'])} "
                  f"distance={result['total_distance_m']}m "
                  f"taxiways={result['taxiway_sequence']}")
        else:
            print(f"  ERROR: {result.get('error')}")

        # 3. Via-constrained route (controller: "taxi via D, E to runway 24L")
        print("\n[3] find_route_via('B', '24L', via=['D','E'])")
        result = airport.find_route_via("B", "24L", via=["D", "E"])
        if result.get("success"):
            print(f"  nodes={len(result['path_node_ids'])} "
                  f"distance={result['total_distance_m']}m "
                  f"taxiways={result['taxiway_sequence']}")
            print(f"  start={result['start']} end={result['end']}")
        else:
            print(f"  ERROR: {result.get('error')}")

    except FileNotFoundError:
        print(f"File not found: {JSON_FILE}")
    except Exception as e:
        print(f"Error: {e}")