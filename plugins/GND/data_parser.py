from typing import List

from xplane_airports.AptDat import RowCode
from models import TaxiNode


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
    
    
    def parse_nodes(self):
        """Extract taxi route nodes"""
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
    
    def parse_edges(self):
        """Extract taxi route edges"""
        pass
    
    def parse_stands(self):
        """Extract taxi stands"""
        pass
    
    def parse_active_zones(self):
        pass
    

if __name__ == "__main__":
    
    from pathlib import Path

    ICAO = "LEBL"
    BASE_DIR = Path(__file__).resolve().parents[2]  # sube dos niveles hasta "AIrport"
    ROUTE = BASE_DIR / "data" / "airport_data" / ICAO / f"{ICAO}.dat"
    
    parser = AptDatParser(file_path=ROUTE)
    
    nodes = parser.parse_nodes()
    for node_id, node in nodes.items():
        print(f"Node {node_id}: {node}")