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

from typing import List

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

    def _load_file(self) -> List[str]:
        """Load .dat file from a given path"""
        with open(self.file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        return lines

    def parse_nodes(self) -> List[TaxiNode]:
        """CODE: 1201"""

        nodes = []
        for line in self.raw_data:
            parts = line.strip().split()

            code = int(parts[0])
            if code == RowCode.TAXI_ROUTE_NODE:  # 1201
                if len(parts) >= 5:
                    try:
                        nodes.append(
                            TaxiNode(
                            lat=float(parts[1]),
                            lon=float(parts[2]),
                            usage=parts[3],  
                            node_id=parts[4],
                            name=' '.join(parts[5:]) if len(parts) > 5 else f"node_{parts[3]}"
                            )
                        )

                    except (ValueError, IndexError) as e:
                        print(f"Error parsing node line: {line.strip()} - {e}")
                        continue

        return nodes

    def parse_edges(self) -> List[TaxiEdge]:
        """CODE: 1202"""

        edges = []
        for line_num, line in enumerate(self.raw_data, 1):
            parts = line.strip().split()

            code = int(parts[0])
            if code == RowCode.TAXI_ROUTE_EDGE:  # 1202
                if len(parts) >= 5:
                    try:

                        edges.append(
                            TaxiEdge(
                            start_node_id=int(parts[1]),
                            end_node_id=int(parts[2]),
                            direction=parts[3],
                            atc_restriction=parts[4] ,
                            taxiway_id=parts[5] if len(parts) >= 6 else "",   
                            )
                        )

                    except (ValueError, IndexError) as e:
                        print(f"Error parsing edge line {line_num}: {line.strip()} - {e}")
                        continue
        return edges

    def parse_stands(self) -> List[Stand]:
        """CODE: 1300"""

        stands = []
        for line in self.raw_data:
            parts = line.strip().split()

            code = int(parts[0])
            if code == RowCode.START_LOCATION_NEW:  # 1300
                if len(parts) >= 5: 
                    try:
                        stands.append(Stand(
                            latitude=float(parts[1]),
                            longitude=float(parts[2]), 
                            true_hdg=float(parts[3]),
                            stand_type=parts[4],
                            allowed_aircraft_types=str(parts[5]),
                            stand_id=str(parts[6:])
                        ))

                    except (ValueError, IndexError) as e:
                        print(f"Error parsing stand line: {line.strip()} - {e}")
                        continue
        return stands

    def parse_runways(self) -> List[Runway]:
        """CODE 100"""

        runways = []
        for line in self.raw_data:
            parts = line.strip().split()

            code = int(parts[0])
            if code == RowCode.LAND_RUNWAY:  # 100
                if len(parts) >= 20:
                    try:
                        runways.append(Runway(
                            runway_1_id=parts[8],
                            lat=float(parts[9]),
                            lon=float(parts[10]),
                            runway_2_id=parts[17],
                            lat_2=float(parts[18]),
                            lon_2=float(parts[19]),
                        ))
                    except (ValueError, IndexError) as e:
                        print(f"Error parsing runway line: {line.strip()} - {e}")
                        continue

        return runways

    def parse_active_zones(self):
        pass

    def parse_traffic_pattern(self) -> List[TrafficPattern]:
        """CODE 1101"""

        traffic_patterns = []
        for line in self.raw_data:
            parts = line.strip().split()

            code = int(parts[0])
            if code == RowCode.FLOW_PATTERN:  # 1101
                if len(parts) >= 3:
                    try:
                        traffic_patterns.append(
                            TrafficPattern(
                                runway_id=parts[1],
                                side=parts[2]
                            )
                        )
                    except(ValueError, IndexError) as e:
                        print(f"Error parsing runway line: {line.strip()} - {e}")
                        continue

        return traffic_patterns

    def parse_airport_info(self) -> List[AirportInfo]:
        """"CODE: 1 and 1302"""

        airport_info = []
        for line in self.raw_data:
            # Parse the line first to extract all parts
            parts = line.strip().split()
            code = int(parts[0])

            # Check if this line contains airport header or metadata
            if code == RowCode.AIRPORT_HEADER or \
               code == RowCode.METADATA:  # 1 or 1302

                try:
                    airport_info.append(
                        AirportInfo(
                            metdata=parts
                        )
                    )
                except (ValueError, IndexError) as e:
                    print(f'Error parsing runway line: {line.strip()} - {e}')

        return airport_info

if __name__ == "__main__":

    import json
    from pathlib import Path

    ICAO = "LEBL".upper()  # Change ICAO code here

    BASE_DIR = Path(__file__).resolve().parents[2]
    INPUT_FILE = BASE_DIR / "data" / "airport_data" / ICAO / f"{ICAO}.dat"
    OUTPUT_FILE = BASE_DIR / "data" / "airport_data" / ICAO / f"{ICAO}_graph.json"

    parser = AptDatParser(
        file_path=INPUT_FILE
    )

    test_nodes = parser.parse_nodes()
    test_edges = parser.parse_edges()
    test_stands = parser.parse_stands()
    test_runways = parser.parse_runways()
    test_traffic_patterns = parser.parse_traffic_pattern()
    test_airport_info = parser.parse_airport_info()

    print(f"\nParsing results for {ICAO}:")
    print(f"Found {len(test_nodes)} taxi nodes")
    print(f"Found {len(test_edges)} taxi edges")
    print(f"Found {len(test_stands)} stands")
    print(f"Found {len(test_runways)} runways")
    print(f"Found {len(test_traffic_patterns)} traffic patterns")
    print(f"Found {len(test_airport_info)} airport info records")

    # Create a dictionary with all data  
    # .__dict__ to change the objects into a dictionary
    airport_data = {
        "nodes": [node.__dict__ for node in test_nodes],  
        "edges": [edge.__dict__ for edge in test_edges],
        "stands": [stand.__dict__ for stand in test_stands],
        "runways": [runway.__dict__ for runway in test_runways],
        "traffic_patterns": [pattern.__dict__ for pattern in test_traffic_patterns],
        "airport_info": [info.__dict__ for info in test_airport_info]
    }

    # Save to JSON file
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(airport_data, indent=2, fp=f)

    print(f"\nData saved to {OUTPUT_FILE}")