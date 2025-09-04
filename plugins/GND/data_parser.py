from typing import List

from xplane_airports.AptDat import RowCode
from models import TaxiEdge, TaxiNode


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
                            id=node_id,
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
        """Extract taxi stands"""
        pass
    
    def parse_active_zones(self):
        pass
    


if __name__ == "__main__":
    
    import json
    from pathlib import Path

    ICAO = "LEBL".upper()  # Change ICAO code here
    
    BASE_DIR = Path(__file__).resolve().parents[2]
    ROUTE = BASE_DIR / "data" / "airport_data" / ICAO / f"{ICAO}.dat"
    OUTPUT_FILE = BASE_DIR / "data" / "airport_data" / ICAO / f"{ICAO}_graph.json"

    parser = AptDatParser(file_path=str(ROUTE))
    nodes = parser.parse_nodes()
    edges = parser.parse_edges()

    # Save to JSON
    graph_data = {
        "nodes": [
            {
                "id": node.id,
                "lat": node.lat,
                "lon": node.lon,
                "usage": node.usage,
                "name": node.name
            }
            for node in nodes.values()
        ],
        "edges": [
            {
                "start_node_id": edge.start_node_id,
                "end_node_id": edge.end_node_id,
                "direction": edge.direction,  
                "atc_restriction": edge.atc_restriction,
                "taxiway_id": edge.taxiway_id
            }
            for edge in edges
        ]
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, indent=4)

    print(f"Info stored in:  {OUTPUT_FILE}")
        
