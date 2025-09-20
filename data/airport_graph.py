"""
Interactive visualizer for airport .dat files using Folium
Shows specific airport elements in an interactive map
"""

import folium
from pathlib import Path
from typing import List, Dict, Tuple, Optional


class AirportMapVisualizer:
    """
    Single-level visualizer for X-Plane airport .dat files
    Creates interactive Folium maps showing specific airport elements
    """
    
    def __init__(
        self, 
        dat_file_path: str, 
        zoom_start: int = 16
    ):
        """
        Initialize the visualizer with a .dat file and create map immediately
        
        Args:
            dat_file_path: Path to the airport .dat file
            zoom_start: Initial zoom level for the map
        """
        self.dat_file_path = Path (dat_file_path)
        self.airport_data = {}
        self.airport_center = None
        self.airport_name = ""
        self.icao_code = ""
        self.zoom_start = zoom_start
        
        # Elements we want to visualize
        self.target_codes = {
            '100': 'Runways',
            '102': 'Helipads',
            '1200': 'Taxi Network Header',
            '1302': 'Airport Metadata', 
            '1201': 'Taxi Route Nodes',
            '1202': 'Taxi Route Edges',
            '1205': 'Taxi Route Controls',
            '1206': 'Ground Vehicle Routes'
        }
        
        # Colors for each element type
        self.colors = {
            '100': '#FF0000',  # Red for runways
            '102': '#FF8C00',  # Orange for helipads
            '1200': '#000000', # Black for header (not visualized)
            '1302': '#000000', # Black for metadata (not visualized)
            '1201': '#800080', # Purple for taxi nodes
            '1202': '#FFC0CB', # Pink for taxi routes
            '1205': '#FF69B4', # Hot pink for controls
            '1206': '#A52A2A'  # Brown for ground vehicles
        }
        
        # Parse file and create map automatically
        self._parse_dat_file()
        self.map = self._create_map()
    
    def _parse_dat_file(self):
        """Parse the .dat file and extract relevant information"""
        if not self.dat_file_path.exists():
            raise FileNotFoundError(f".dat file not found: {self.dat_file_path}")
        
        with open(self.dat_file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        for line_num, line in enumerate(lines):
            line = line.strip()
            if not line or line.startswith('//'):
                continue
            
            parts = line.split()
            if not parts:
                continue
                
            code = parts[0]
            
            # Airport header
            if code == '1' and len(parts) >= 5:
                self.airport_name = ' '.join(parts[4:])
                self.icao_code = parts[4] if len(parts) > 4 else "Unknown"
            
            # Official airport coordinates
            elif code == '1302' and len(parts) >= 3:
                if parts[1] == 'datum_lat':
                    try:
                        lat = float(parts[2])
                        if hasattr(self, 'datum_lon'):
                            self.airport_center = (lat, self.datum_lon)
                            print(f"Official airport center: {self.airport_center}")
                        else:
                            self.datum_lat = lat
                    except ValueError:
                        pass
                elif parts[1] == 'datum_lon':
                    try:
                        lon = float(parts[2])
                        if hasattr(self, 'datum_lat'):
                            self.airport_center = (self.datum_lat, lon)
                            print(f"Official airport center: {self.airport_center}")
                        else:
                            self.datum_lon = lon
                    except ValueError:
                        pass
            
            # Elements we want to visualize
            elif code in self.target_codes:
                if code not in self.airport_data:
                    self.airport_data[code] = []
                
                try:
                    parsed_element = self._parse_element(code, parts, line)
                    if parsed_element:
                        self.airport_data[code].append(parsed_element)
                except Exception as e:
                    print(f"Error parsing line {line_num}: {line} - {e}")
                    continue
    
    def _parse_element(self, code: str, parts: List[str], full_line: str) -> Optional[Dict]:
        """Parse a specific element according to its code"""
        
        if code == '100':  # Runway
            if len(parts) >= 23:  # Complete format with both ends
                return {
                    'type': 'runway',
                    'width': float(parts[1]),
                    'surface_type': parts[2],
                    'shoulder': parts[3],
                    'smoothness': float(parts[4]),
                    'center_lighting': parts[5],
                    'edge_lighting': parts[6],
                    'distance_signs': parts[7],
                    'runway_end1': parts[8],  # "17"
                    'lat1': float(parts[9]),  # 42.91180046
                    'lon1': float(parts[10]), # -008.42033176
                    'displace1': float(parts[11]),  # 120
                    'overrun1': float(parts[12]),   # 0
                    'marking1': parts[13],    # 7
                    'approach_lighting1': parts[14], # 2
                    'tdz_lighting1': parts[15], # 1
                    'reil1': parts[16],       # 0
                    'runway_end2': parts[17], # "35"
                    'lat2': float(parts[18]), # 42.88381103
                    'lon2': float(parts[19]), # -008.41094228
                    'displace2': float(parts[20]), # 150
                    'overrun2': float(parts[21]),  # 0
                    'marking2': parts[22],    # 7
                    'approach_lighting2': parts[23] if len(parts) > 23 else '0', # 6
                    'tdz_lighting2': parts[24] if len(parts) > 24 else '0', # 0
                    'reil2': parts[25] if len(parts) > 25 else '0', # 2
                    'raw': full_line
                }
        
        elif code == '102':  # Helipad
            if len(parts) >= 6:
                return {
                    'type': 'helipad',
                    'id': parts[1],
                    'lat': float(parts[2]),
                    'lon': float(parts[3]),
                    'orientation': float(parts[4]) if len(parts) > 4 else 0,
                    'raw': full_line
                }
        
        elif code == '1200':  # Taxi network header
            return {
                'type': 'taxi_network_header',
                'raw': full_line
            }
        
        elif code == '1302':  # Airport metadata
            if len(parts) >= 3:
                return {
                    'type': 'airport_metadata',
                    'field': parts[1],
                    'value': ' '.join(parts[2:]),
                    'raw': full_line
                }
        
        elif code == '1201':  # Taxi route node
            if len(parts) >= 5:
                return {
                    'type': 'taxi_node',
                    'lat': float(parts[1]),
                    'lon': float(parts[2]),
                    'type_flag': parts[3],
                    'node_id': int(parts[4]),
                    'name': ' '.join(parts[5:]) if len(parts) > 5 else f'Node {parts[4]}',
                    'raw': full_line
                }
        
        elif code == '1202':  # Taxi route edge
            return {
                'type': 'taxi_edge',
                'node1': int(parts[1]) if len(parts) > 1 else 0,
                'node2': int(parts[2]) if len(parts) > 2 else 0,
                'direction': parts[3] if len(parts) > 3 else 'oneway',
                'category': parts[4] if len(parts) > 4 else 'unknown',
                'name': ' '.join(parts[5:]) if len(parts) > 5 else 'Unnamed edge',
                'raw': full_line
            }
        
        return None
    
    def _create_map(self) -> folium.Map:
        """
        Create the interactive Folium map
        
        Returns:
            Folium map with airport elements
        """
        # Determine map center
        if not self.airport_center:
            self.airport_center = self._calculate_center()
        
        print(f"Creating map centered at: {self.airport_center}")
        
        # Create base map
        m = folium.Map(
            location=self.airport_center,
            zoom_start=self.zoom_start,
            tiles='OpenStreetMap'
        )
        
        # Add title
        title_html = f'''
        <h3 align="center" style="font-size:20px"><b>{self.airport_name} ({self.icao_code})</b></h3>
        '''
        m.get_root().html.add_child(folium.Element(title_html))
        
        # Create layer groups for each element type
        feature_groups = {}
        for code, name in self.target_codes.items():
            if code in self.airport_data and code not in ['1302', '1200']:  # Don't create groups for metadata/headers
                feature_groups[code] = folium.FeatureGroup(name=name)
        
        # Add elements to map
        self._add_runways(m, feature_groups.get('100'))
        self._add_helipads(m, feature_groups.get('102'))
        self._add_taxi_nodes(m, feature_groups.get('1201'))
        self._add_taxi_edges(m, feature_groups.get('1202'))
        self._add_ground_vehicle_routes(m, feature_groups.get('1206'))
        
        # Add other elements as simple markers
        for code in ['1205']:
            if code in self.airport_data and code in feature_groups:
                self._add_simple_markers(m, feature_groups[code], code)
        
        # Add groups to map
        for group in feature_groups.values():
            if group:
                m.add_child(group)
        
        # Layer control
        folium.LayerControl().add_to(m)
        
        return m
    
    def _calculate_center(self) -> Optional[Tuple[float, float]]:
        """Calculate geographic center based on all elements with coordinates"""
        lats, lons = [], []
        
        # Prioritize runway coordinates if they exist
        if '100' in self.airport_data:
            for runway in self.airport_data['100']:
                if 'lat1' in runway and 'lon1' in runway:
                    lats.extend([runway['lat1'], runway['lat2']])
                    lons.extend([runway['lon1'], runway['lon2']])
        
        # If no runways, use taxi nodes
        if not lats and '1201' in self.airport_data:
            for node in self.airport_data['1201']:
                if 'lat' in node and 'lon' in node:
                    lats.append(node['lat'])
                    lons.append(node['lon'])
        
        # Last resort: use any element with coordinates
        if not lats:
            for code, elements in self.airport_data.items():
                for element in elements:
                    if 'lat' in element and 'lon' in element:
                        lats.append(element['lat'])
                        lons.append(element['lon'])
                    elif 'lat1' in element and 'lon1' in element:
                        lats.extend([element['lat1'], element['lat2']])
                        lons.extend([element['lon1'], element['lon2']])
        
        if lats and lons:
            center = (sum(lats) / len(lats), sum(lons) / len(lons))
            print(f"Calculated center: {center}")
            return center
        return None
    
    def _add_runways(self, map_obj: folium.Map, feature_group: folium.FeatureGroup):
        """Add runways to map with detailed X-Plane format information"""
        if not feature_group or '100' not in self.airport_data:
            return
            
        for runway in self.airport_data['100']:
            if all(key in runway for key in ['lat1', 'lon1', 'lat2', 'lon2']):
                # Main runway line
                folium.PolyLine(
                    locations=[(runway['lat1'], runway['lon1']), (runway['lat2'], runway['lon2'])],
                    color=self.colors['100'],
                    weight=8,
                    opacity=0.9,
                    popup=self._create_runway_popup(runway)
                ).add_to(feature_group)
                
                # Marker at end 1 with threshold information
                folium.CircleMarker(
                    location=(runway['lat1'], runway['lon1']),
                    radius=6,
                    color='white',
                    fillColor=self.colors['100'],
                    weight=2,
                    popup=f"Runway {runway['runway_end1']}<br>"
                          f"Displacement: {runway['displace1']}m<br>"
                          f"Overrun: {runway['overrun1']}m<br>"
                          f"Marking: {runway['marking1']}"
                ).add_to(feature_group)
                
                # Marker at end 2 with threshold information
                folium.CircleMarker(
                    location=(runway['lat2'], runway['lon2']),
                    radius=6,
                    color='white',
                    fillColor=self.colors['100'],
                    weight=2,
                    popup=f"Runway {runway['runway_end2']}<br>"
                          f"Displacement: {runway['displace2']}m<br>"
                          f"Overrun: {runway['overrun2']}m<br>"
                          f"Marking: {runway['marking2']}"
                ).add_to(feature_group)
    
    def _create_runway_popup(self, runway: dict) -> str:
        """Create detailed popup for runway"""
        return f"""
        <b>Runway {runway['runway_end1']}/{runway['runway_end2']}</b><br>
        Width: {runway['width']}m<br>
        Surface: {runway['surface_type']}<br>
        Smoothness: {runway['smoothness']}<br>
        Center Lighting: {runway['center_lighting']}<br>
        Edge Lighting: {runway['edge_lighting']}<br>
        Distance Signs: {runway['distance_signs']}<br>
        <hr>
        <b>{runway['runway_end1']} End:</b><br>
        Lat: {runway['lat1']:.6f}<br>
        Lon: {runway['lon1']:.6f}<br>
        <b>{runway['runway_end2']} End:</b><br>
        Lat: {runway['lat2']:.6f}<br>
        Lon: {runway['lon2']:.6f}
        """
    
    def _add_helipads(self, map_obj: folium.Map, feature_group: folium.FeatureGroup):
        """Add helipads to map"""
        if not feature_group or '102' not in self.airport_data:
            return
            
        for helipad in self.airport_data['102']:
            folium.RegularPolygonMarker(
                location=(helipad['lat'], helipad['lon']),
                fill_color=self.colors['102'],
                color=self.colors['102'],
                number_of_sides=6,
                radius=8,
                popup=f"Helipad {helipad['id']}<br>Orientation: {helipad['orientation']}°"
            ).add_to(feature_group)
    
    def _add_taxi_nodes(self, map_obj: folium.Map, feature_group: folium.FeatureGroup):
        """Add taxi nodes to map"""
        if not feature_group or '1201' not in self.airport_data:
            return
            
        for node in self.airport_data['1201']:
            folium.CircleMarker(
                location=(node['lat'], node['lon']),
                radius=3,
                color=self.colors['1201'],
                fillColor=self.colors['1201'],
                popup=f"Taxi Node {node['node_id']}: {node['name']}"
            ).add_to(feature_group)
    
    def _add_taxi_edges(self, map_obj: folium.Map, feature_group: folium.FeatureGroup):
        """Add connections between taxi nodes"""
        if not feature_group or '1202' not in self.airport_data or '1201' not in self.airport_data:
            return
        
        # Create dictionary of nodes for quick lookup
        nodes = {node['node_id']: (node['lat'], node['lon']) 
                for node in self.airport_data['1201']}
        
        for edge in self.airport_data['1202']:
            node1_id = edge['node1']
            node2_id = edge['node2']
            
            if node1_id in nodes and node2_id in nodes:
                folium.PolyLine(
                    locations=[nodes[node1_id], nodes[node2_id]],
                    color=self.colors['1202'],
                    weight=2,
                    opacity=0.7,
                    popup=f"Taxi Edge: {edge['name']}<br>Type: {edge['category']}<br>Direction: {edge['direction']}"
                ).add_to(feature_group)
    
    def _add_ground_vehicle_routes(self, map_obj: folium.Map, feature_group: folium.FeatureGroup):
        """Add ground vehicle routes (code 1206)"""
        if not feature_group or '1206' not in self.airport_data or '1201' not in self.airport_data:
            return
        
        # Create dictionary of nodes for quick lookup
        nodes = {node['node_id']: (node['lat'], node['lon']) 
                for node in self.airport_data['1201']}
        
        for route in self.airport_data['1206']:
            # Format: 1206 node1 node2 direction name
            data = route['data']
            if len(data) >= 2:
                try:
                    node1_id = int(data[0])
                    node2_id = int(data[1])
                    direction = data[2] if len(data) > 2 else 'unknown'
                    name = ' '.join(data[3:]) if len(data) > 3 else 'Ground Vehicle Route'
                    
                    if node1_id in nodes and node2_id in nodes:
                        folium.PolyLine(
                            locations=[nodes[node1_id], nodes[node2_id]],
                            color=self.colors['1206'],
                            weight=3,
                            opacity=0.8,
                            dash_array='5, 5',  # Dashed line to differentiate from taxi
                            popup=f"Ground Vehicle Route<br>"
                                  f"Name: {name}<br>"
                                  f"Direction: {direction}<br>"
                                  f"Nodes: {node1_id} → {node2_id}"
                        ).add_to(feature_group)
                except:
                    continue
    
    def _add_simple_markers(self, map_obj: folium.Map, feature_group: folium.FeatureGroup, code: str):
        """Add simple markers for elements without specific coordinates"""
        if not feature_group or code not in self.airport_data:
            return
        
        for i, element in enumerate(self.airport_data[code]):
            # For elements without specific coordinates, use airport center with small offset
            if self.airport_center:
                offset = 0.001 * (i + 1)  # Small offset to avoid overlap
                location = (self.airport_center[0] + offset, self.airport_center[1] + offset)
                
                folium.CircleMarker(
                    location=location,
                    radius=4,
                    color=self.colors[code],
                    fillColor=self.colors[code],
                    popup=f"{self.target_codes[code]}<br>{element['raw']}"
                ).add_to(feature_group)
    
    def save(self, filename: str = None, output_dir: str = None):
        """
        Save the map to an HTML file
        
        Args:
            filename: Output filename. If None, uses ICAO code
            output_dir: Output directory. If None, uses same directory as .dat file
        """
        if filename is None:
            filename = f"{self.icao_code}_airport_map.html"
        
        # If no output directory specified, use the same directory as the .dat file
        if output_dir is None:
            output_dir = self.dat_file_path.parent
        else:
            output_dir = Path(output_dir)
        
        # Create full path
        full_path = output_dir / filename
        
        self.map.save(str(full_path))
        print(f"Map saved as: {full_path}")
    
    def show_summary(self):
        """Show summary of found elements"""
        print(f"\n=== AIRPORT SUMMARY ===")
        print(f"Name: {self.airport_name}")
        print(f"ICAO Code: {self.icao_code}")
        print(f"Approximate center: {self.airport_center}")
        print(f"\n=== ELEMENTS FOUND ===")
        
        for code, name in self.target_codes.items():
            count = len(self.airport_data.get(code, []))
            if count > 0:
                print(f"{name}: {count} elements")
        
        total_elements = sum(len(elements) for elements in self.airport_data.values())
        print(f"\nTotal relevant elements: {total_elements}")
    
    def display(self):
        """
        Display the map (for Jupyter notebooks)
        
        Returns:
            The Folium map object
        """
        return self.map

if __name__ == "__main__":

    AIRPORT = 'LEBL'.upper()
    dat_file = f".\\airport_data\\{AIRPORT}\\{AIRPORT}.dat"

    try:
        
        airport_viz = AirportMapVisualizer(dat_file, zoom_start=16)
        
        # Show summary
        airport_viz.show_summary()
        
        # Save map
        airport_viz.save()
        
        # For nb
        # airport_viz.display()
        
    except FileNotFoundError:
        print(f"File not found: {dat_file}")
        print("Make sure the .dat file exists at the specified path")