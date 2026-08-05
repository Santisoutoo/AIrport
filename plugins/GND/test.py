"""
╔═════════════════════════════════════════════════════════════════════════════════╗
║                               DISCLAIMER                                        ║
║                                                                                 ║
║ THIS INFORMATION IS NOT INTENDED FOR REAL OPERATIONS.                           ║
║ The data is maintained by volunteer enthusiasts who update scenery information. ║
║                                                                                 ║
║ Purpose: Parse X-Plane .dat scenery files to extract key airport data           ║
║          and build a graph structure for pathfinding algorithms.                ║
║                                                                                 ║
╚═════════════════════════════════════════════════════════════════════════════════╝
"""

from typing import List, Set, Dict

from models import (
    AirportInfo,
    Runway,
    Stand,
    TaxiEdge,
    TaxiNode,
    TrafficPattern,
)
from xplane_airports.AptDat import RowCode


class AptDatParser:
    """Parser for X-Plane .dat airport files to extract taxi routes and stands"""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.raw_data = self._load_file()
        self.active_zones = self._parse_active_zones()

    def _load_file(self) -> List[str]:
        """Load .dat file from a given path"""
        with open(self.file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return lines

    def _parse_active_zones(self) -> Dict[str, Dict]:
        """
        Parse active zones (row code 1204) and associate them with edges.
        Returns a dictionary mapping edge_id (as string) to active zone information.
        """
        active_zones = {}
        current_edge_id = None

        for line in self.raw_data:
            parts = line.strip().split()
            if not parts:
                continue

            try:
                code = int(parts[0])

                # Track the current edge being processed
                if code == RowCode.TAXI_ROUTE_EDGE:  # 1202
                    if len(parts) >= 3:
                        # Use string format for JSON serialization
                        current_edge_id = f"{parts[1]}-{parts[2]}"

                # Parse active zone for the current edge
                elif code == 1204:  # TAXI_ROUTE_EDGE_ACTIVE_ZONE
                    if current_edge_id and len(parts) >= 3:
                        zone_type = parts[1]  # "arrival", "departure", "ils"
                        runways = parts[2].split(",") if len(parts) > 2 else []

                        if current_edge_id not in active_zones:
                            active_zones[current_edge_id] = []

                        active_zones[current_edge_id].append({"type": zone_type, "runways": runways})

            except (ValueError, IndexError):
                continue

        return active_zones

    def parse_nodes(self, active_runway: str = None) -> List[TaxiNode]:
        """
        CODE: 1201
        Parse taxi nodes, optionally filtering based on active runway configuration
        """
        nodes = []
        for line in self.raw_data:
            parts = line.strip().split()

            try:
                code = int(parts[0])
                if code == RowCode.TAXI_ROUTE_NODE:  # 1201
                    if len(parts) >= 5:
                        node = TaxiNode(
                            lat=float(parts[1]),
                            lon=float(parts[2]),
                            usage=parts[3],  # CORREGIDO: usage es el 4to campo (índice 3)
                            node_id=parts[4],  # CORREGIDO: node_id es el 5to campo (índice 4)
                            name=" ".join(parts[5:]) if len(parts) > 5 else f"node_{parts[4]}",
                        )

                        # If no active runway specified, include all nodes
                        if active_runway is None:
                            nodes.append(node)
                        else:
                            # Check if this node is accessible given the active runway
                            if self._is_node_accessible(node, active_runway):
                                nodes.append(node)

            except (ValueError, IndexError) as e:
                print(f"Error parsing node line: {line.strip()} - {e}")
                continue

        return nodes

    def parse_edges(self, active_runway: str = None) -> List[TaxiEdge]:
        """
        CODE: 1202
        Parse taxi edges, optionally filtering based on active runway configuration
        """
        edges = []
        for line_num, line in enumerate(self.raw_data, 1):
            parts = line.strip().split()

            try:
                code = int(parts[0])
                if code == RowCode.TAXI_ROUTE_EDGE:  # 1202
                    if len(parts) >= 5:
                        edge = TaxiEdge(
                            start_node_id=int(parts[1]),
                            end_node_id=int(parts[2]),
                            direction=parts[3],
                            atc_restriction=parts[4],
                            taxiway_id=parts[5] if len(parts) >= 6 else "",
                        )

                        # If no active runway specified, include all edges
                        if active_runway is None:
                            edges.append(edge)
                        else:
                            # Check if this edge is accessible given the active runway
                            if self._is_edge_accessible(edge, active_runway):
                                edges.append(edge)

            except (ValueError, IndexError) as e:
                print(f"Error parsing edge line {line_num}: {line.strip()} - {e}")
                continue

        return edges

    def _is_node_accessible(self, node: TaxiNode, active_runway: str) -> bool:
        """
        Determine if a node is accessible given the active runway configuration.
        A node is accessible if it's not connected exclusively to restricted edges.
        """
        node_id = int(node.node_id)

        # Find all edges connected to this node
        connected_edges = []
        for line in self.raw_data:
            parts = line.strip().split()
            try:
                code = int(parts[0])
                if code == RowCode.TAXI_ROUTE_EDGE and len(parts) >= 3:
                    start_node = int(parts[1])
                    end_node = int(parts[2])
                    if start_node == node_id or end_node == node_id:
                        connected_edges.append(f"{start_node}-{end_node}")
            except (ValueError, IndexError):
                continue

        # If no edges are connected, the node is accessible
        if not connected_edges:
            return True

        # Check if at least one connected edge is accessible
        for edge_key in connected_edges:
            if self._is_edge_key_accessible(edge_key, active_runway):
                return True

        return False

    def _is_edge_accessible(self, edge: TaxiEdge, active_runway: str) -> bool:
        """
        Determine if an edge is accessible given the active runway configuration.
        """
        edge_key = f"{edge.start_node_id}-{edge.end_node_id}"
        return self._is_edge_key_accessible(edge_key, active_runway)

    def _is_edge_key_accessible(self, edge_key: str, active_runway: str) -> bool:
        """
        Determine if an edge (identified by "start-end" string) is accessible
        given the active runway configuration.
        """
        # If edge has no active zones, it's always accessible
        if edge_key not in self.active_zones:
            return True

        # Check each active zone for this edge
        for zone in self.active_zones[edge_key]:
            zone_type = zone["type"]
            zone_runways = zone["runways"]

            # If the active runway is in the restricted list for this zone
            if active_runway in zone_runways:
                # Edge is restricted for the active runway
                if zone_type in ["arrival", "departure", "ils"]:
                    return False

        # If we get here, the edge is not restricted by any active zone
        return True

    def get_accessible_network(self, active_runway: str = None) -> Dict:
        """
        Get the complete accessible taxi network for a given active runway configuration.
        Returns a dictionary with filtered nodes and edges.
        """
        accessible_nodes = self.parse_nodes(active_runway)
        accessible_edges = self.parse_edges(active_runway)

        # Get node IDs that are accessible
        accessible_node_ids = {int(node.node_id) for node in accessible_nodes}

        # Filter edges to only include those connecting accessible nodes
        filtered_edges = []
        for edge in accessible_edges:
            if edge.start_node_id in accessible_node_ids and edge.end_node_id in accessible_node_ids:
                filtered_edges.append(edge)

        return {
            "nodes": accessible_nodes,
            "edges": filtered_edges,
            "active_runway": active_runway,
            "total_accessible_nodes": len(accessible_nodes),
            "total_accessible_edges": len(filtered_edges),
        }

    def debug_runway_restrictions(self, active_runway: str) -> Dict:
        """
        Debug function to understand why certain nodes/edges are restricted
        """
        debug_info = {
            "active_runway": active_runway,
            "total_active_zones": len(self.active_zones),
            "restricted_edges": [],
            "zones_affecting_runway": [],
        }

        for edge_key, zones in self.active_zones.items():
            edge_restricted = False
            for zone in zones:
                if active_runway in zone["runways"]:
                    edge_restricted = True
                    debug_info["zones_affecting_runway"].append(
                        {"edge": edge_key, "zone_type": zone["type"], "runways": zone["runways"]}
                    )

            if edge_restricted:
                debug_info["restricted_edges"].append(edge_key)

        return debug_info

    def get_available_runways(self) -> List[str]:
        """
        Get list of all runways mentioned in active zones and runway definitions
        """
        runways_in_zones = set()

        # Get runways from active zones
        for zones in self.active_zones.values():
            for zone in zones:
                runways_in_zones.update(zone["runways"])

        # Get runways from runway definitions
        runways_from_def = []
        for line in self.raw_data:
            parts = line.strip().split()
            try:
                code = int(parts[0])
                if code == RowCode.LAND_RUNWAY and len(parts) >= 20:
                    runways_from_def.extend([parts[8], parts[17]])
            except (ValueError, IndexError):
                continue

        all_runways = list(runways_in_zones) + runways_from_def
        return sorted(list(set(all_runways)))

    def parse_stands(self) -> List[Stand]:
        """CODE: 1300"""
        stands = []
        for line in self.raw_data:
            parts = line.strip().split()

            try:
                code = int(parts[0])
                if code == RowCode.START_LOCATION_NEW:  # 1300
                    if len(parts) >= 5:
                        stands.append(
                            Stand(
                                latitude=float(parts[1]),
                                longitude=float(parts[2]),
                                true_hdg=float(parts[3]),
                                stand_type=parts[4],
                                allowed_aircraft_types=str(parts[5]),
                                stand_id=str(parts[6:]),
                            )
                        )

            except (ValueError, IndexError) as e:
                print(f"Error parsing stand line: {line.strip()} - {e}")
                continue
        return stands

    def parse_runways(self) -> List[Runway]:
        """CODE 100"""
        runways = []
        for line in self.raw_data:
            parts = line.strip().split()

            try:
                code = int(parts[0])
                if code == RowCode.LAND_RUNWAY:  # 100
                    if len(parts) >= 20:
                        runways.append(
                            Runway(
                                runway_1_id=parts[8],
                                lat=float(parts[9]),
                                lon=float(parts[10]),
                                runway_2_id=parts[17],
                                lat_2=float(parts[18]),
                                lon_2=float(parts[19]),
                            )
                        )
            except (ValueError, IndexError) as e:
                print(f"Error parsing runway line: {line.strip()} - {e}")
                continue

        return runways

    def parse_active_zones(self):
        return self.active_zones

    def parse_traffic_pattern(self) -> List[TrafficPattern]:
        """CODE 1101"""
        traffic_patterns = []
        for line in self.raw_data:
            parts = line.strip().split()

            try:
                code = int(parts[0])
                if code == RowCode.FLOW_PATTERN:  # 1101
                    if len(parts) >= 3:
                        traffic_patterns.append(TrafficPattern(runway_id=parts[1], side=parts[2]))
            except (ValueError, IndexError) as e:
                print(f"Error parsing runway line: {line.strip()} - {e}")
                continue

        return traffic_patterns

    def parse_airport_info(self) -> List[AirportInfo]:
        """ "CODE: 1 and 1302"""
        airport_info = []
        for line in self.raw_data:
            parts = line.strip().split()
            try:
                code = int(parts[0])
                if code == RowCode.AIRPORT_HEADER or code == RowCode.METADATA:
                    airport_info.append(AirportInfo(metdata=parts))
            except (ValueError, IndexError) as e:
                print(f"Error parsing runway line: {line.strip()} - {e}")

        return airport_info


if __name__ == "__main__":
    import json
    from pathlib import Path

    ICAO = "LEST"  # Change ICAO code here
    ACTIVE_RUNWAY = "02"  # Example active runway

    BASE_DIR = Path(__file__).resolve().parents[2]
    INPUT_FILE = BASE_DIR / "data" / "airport_data" / ICAO / f"{ICAO}.dat"
    OUTPUT_FILE = BASE_DIR / "data" / "airport_data" / ICAO / f"{ICAO}_graph.json"

    parser = AptDatParser(file_path=INPUT_FILE)

    # Get list of available runways for reference
    available_runways = parser.get_available_runways()

    # Get complete network (no filtering)
    all_nodes = parser.parse_nodes()
    all_edges = parser.parse_edges()

    # Get accessible network for active runway
    accessible_network = parser.get_accessible_network(ACTIVE_RUNWAY)

    # Debug information
    debug_info = parser.debug_runway_restrictions(ACTIVE_RUNWAY)

    # Other data
    test_stands = parser.parse_stands()
    test_runways = parser.parse_runways()
    test_traffic_patterns = parser.parse_traffic_pattern()
    test_airport_info = parser.parse_airport_info()

    print(f"\nParsing results for {ICAO}:")
    print(f"Available runways in data: {available_runways}")
    print(f"Total nodes: {len(all_nodes)}")
    print(f"Total edges: {len(all_edges)}")
    print(f"Accessible nodes with runway {ACTIVE_RUNWAY}: {accessible_network['total_accessible_nodes']}")
    print(f"Accessible edges with runway {ACTIVE_RUNWAY}: {accessible_network['total_accessible_edges']}")
    print(f"Active zones found: {debug_info['total_active_zones']}")
    print(f"Edges restricted by {ACTIVE_RUNWAY}: {len(debug_info['restricted_edges'])}")
    print(f"Found {len(test_stands)} stands")
    print(f"Found {len(test_runways)} runways")
    print(f"Found {len(test_traffic_patterns)} traffic patterns")
    print(f"Found {len(test_airport_info)} airport info records")

    # Create a dictionary with all data including filtered network
    airport_data = {
        "all_nodes": [node.__dict__ for node in all_nodes],
        "all_edges": [edge.__dict__ for edge in all_edges],
        "accessible_nodes": [node.__dict__ for node in accessible_network["nodes"]],
        "accessible_edges": [edge.__dict__ for edge in accessible_network["edges"]],
        "active_runway": ACTIVE_RUNWAY,
        "available_runways": available_runways,
        "stands": [stand.__dict__ for stand in test_stands],
        "runways": [runway.__dict__ for runway in test_runways],
        "traffic_patterns": [pattern.__dict__ for pattern in test_traffic_patterns],
        "airport_info": [info.__dict__ for info in test_airport_info],
        "active_zones": parser.active_zones,
        "debug_info": debug_info,
    }

    # Save to JSON file
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(airport_data, indent=2, fp=f)

    print(f"\nData saved to {OUTPUT_FILE}")
