import json
import networkx as nx
import math


class AirportGraph:
    """Create a directed graph to get shortest routes in an airport"""
    
    def __init__(self, json_file_path: str):
        self.data = self._load_json_data(json_file_path)
        self.graph = nx.DiGraph()
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
        
        print(f"Graph built: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")
    
    def find_nearest_node(
        self, 
        target_lat: float, target_lon: float, 
        max_distance: float = 1000.0
    ):
        """Find the nearest node to given coordinates"""
        min_distance = float('inf')
        nearest_node = None
        
        for node_id in self.graph.nodes():
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
        
        # Start and end coordinates for testing
        start_lat, start_lon = 41.294810, 2.079630
        end_lat, end_lon = 41.292172, 2.103167
        
        print(f"Finding route from ({start_lat}, {start_lon}) to ({end_lat}, {end_lon})...")
        
        result = airport.find_shortest_path(start_lat, start_lon, end_lat, end_lon)
        airport.print_route(result)
        
    except FileNotFoundError:
        print(f"File not found: {JSON_FILE}")
    except Exception as e:
        print(f"Error: {e}")