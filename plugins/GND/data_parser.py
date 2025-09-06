from typing import List

from xplane_airports.AptDat import RowCode
from models import (
    TaxiEdge,
    TaxiNode,
    Stand,
    Runway,
    TrafficPattern
)


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

    
    def parse_nodes(self) -> dict[int, TaxiNode]:
        """CODE: 1201"""

        nodes = {}
        for line in self.raw_data:
            if line.startswith(str(RowCode.TAXI_ROUTE_NODE)):  # 1201
                parts = line.strip().split()
                
                if len(parts) >= 5: # Check it has all required fields
                    try:
                        lat = float(parts[1])
                        lon = float(parts[2])
                        usage_type = parts[3]
                        node_id = int(parts[4])
                        name = ' '.join(parts[5:]) if len(parts) > 5 else f"node_{node_id}"

                        nodes[node_id] = TaxiNode (
                            lat=lat,
                            lon=lon,
                            node_id=node_id,
                            usage=usage_type,
                            name=name
                        )
                      
                    except (ValueError, IndexError) as e:
                        print(f"Error parsing node line: {line.strip()} - {e}")
                        continue
     
        return nodes
  
    def parse_edges(self) -> List[TaxiEdge]:
        """CODE: 1202"""
      
        edges = []
        for line_num, line in enumerate(self.raw_data, 1):
            if line.startswith(str(RowCode.TAXI_ROUTE_EDGE)):  # 1202
                parts = line.strip().split()
            
                # Check it has minimum required fields
                if len(parts) >= 5:
                    try:
                        start_id = int(parts[1])                    
                        end_id = int(parts[2])              
                        direction = parts[3]
                        restriction = parts[4]                      

                        # Taxiway ATC name
                        taxiway_name = parts[5] if len(parts) >= 6 else ""
                  
                        edge = TaxiEdge(
                            start_node_id=start_id,
                            end_node_id=end_id,
                            direction=direction,
                            atc_restriction=restriction,
                            taxiway_id=taxiway_name,
                        )
                        edges.append(edge)
                    
                    except (ValueError, IndexError) as e:
                        print(f"Error parsing edge line {line_num}: {line.strip()} - {e}")
                        continue
                        
                else:
                    print(f"Edge line {line_num} has insufficient fields (expected 5-6): {line.strip()}")
    
        return edges
        
        
    
    def parse_stands(self):
        """CODE: 1300"""

        stands = []
        for line in self.raw_data:
            if line.startswith(str(RowCode.START_LOCATION_NEW)):  # 1300
                parts = line.strip().split()
                
                if len(parts) >= 5: # Check it has all required fields
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
    
    def parse_runways(self):
        """CODE 100"""

        runways = []
        for line in self.raw_data:
            if line.startswith(str(RowCode.LAND_RUNWAY)):
                parts = line.strip().split()
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

    def parse_traffic_pattern(self):
        """CODE 1101"""

        traffic_patterns = []
        for line in self.raw_data:
            if line.startswith(str(RowCode.FLOW_PATTERN)):
                parts = line.strip().split()

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

    def parse_airport_info(self):
        """"CODE: 1"""
        pass
  
    def parse_airport_metadata(self):
        """CODE: 1302"""
        pass

if __name__ == "__main__":
  
    import json
    from pathlib import Path

    ICAO = "LEST".upper()  # Change ICAO code here
  
    BASE_DIR = Path(__file__).resolve().parents[2]
    INPUT_FILE = BASE_DIR / "data" / "airport_data" / ICAO / f"{ICAO}.dat"
    OUTPUT_FILE = BASE_DIR / "data" / "airport_data" / ICAO / f"{ICAO}_graph.json"

    parser = AptDatParser(file_path=str(INPUT_FILE))

    traffic_patterns = parser.parse_traffic_pattern()
    print(f"Found {len(traffic_patterns)} traffic patterns")
    print(json.dumps([p.__dict__ for p in traffic_patterns], indent=2))