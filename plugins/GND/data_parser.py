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

import sys
from pathlib import Path
from typing import List

# Allow imports to work both standalone and from XPPython3
_GND_DIR = str(Path(__file__).resolve().parent)
if _GND_DIR not in sys.path:
    sys.path.insert(0, _GND_DIR)

from models import (
    AirportInfo,
    ComFrequency,
    Runway,
    Stand,
    TaxiEdge,
    TaxiNode,
    TrafficPattern,
)
from xplane_airports.AptDat import RowCode

# 1050-1056 (8.33 kHz) → service tag. 1056 is "CENTER" in the X-Plane lib but
# in the apt.dat 1200 spec the same row code is also used for DEP; we surface
# it as DEP because that's what the controller actually says on the radio.
_COM_CHANNEL_MAP = {
    int(RowCode.CHANNEL_AWOS):     "ATIS",    # 1050
    int(RowCode.CHANNEL_CTAF):     "UNICOM",  # 1051
    int(RowCode.CHANNEL_DELIVERY): "DEL",     # 1052
    int(RowCode.CHANNEL_GROUND):   "GND",     # 1053
    int(RowCode.CHANNEL_TOWER):    "TWR",     # 1054
    int(RowCode.CHANNEL_APPROACH): "APP",     # 1055
    int(RowCode.CHANNEL_CENTER):   "DEP",     # 1056
}
_COM_LEGACY_MAP = {
    int(RowCode.FREQUENCY_AWOS):     "ATIS",    # 50
    int(RowCode.FREQUENCY_CTAF):     "UNICOM",  # 51
    int(RowCode.FREQUENCY_DELIVERY): "DEL",     # 52
    int(RowCode.FREQUENCY_GROUND):   "GND",     # 53
    int(RowCode.FREQUENCY_TOWER):    "TWR",     # 54
    int(RowCode.FREQUENCY_APPROACH): "APP",     # 55
    int(RowCode.FREQUENCY_CENTER):   "DEP",     # 56
}


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
        """CODES: 1300 + 1301"""

        stands = []
        lines = self.raw_data
        i = 0
        while i < len(lines):
            parts = lines[i].strip().split()
            try:
                code = int(parts[0])
            except (ValueError, IndexError):
                i += 1
                continue

            if code == RowCode.START_LOCATION_NEW:  # 1300
                if len(parts) >= 7:
                    try:
                        icao_width_code = ""
                        operation_type = ""

                        # Look ahead for row code 1301 (metadata)
                        if i + 1 < len(lines):
                            next_parts = lines[i + 1].strip().split()
                            try:
                                if int(next_parts[0]) == RowCode.START_LOCATION_EXT:  # 1301
                                    icao_width_code = next_parts[1] if len(next_parts) > 1 else ""
                                    operation_type = next_parts[2] if len(next_parts) > 2 else ""
                                    i += 1  # Skip the 1301 line
                            except (ValueError, IndexError):
                                pass

                        stands.append(Stand(
                            latitude=float(parts[1]),
                            longitude=float(parts[2]),
                            true_hdg=float(parts[3]),
                            stand_type=parts[4],
                            allowed_aircraft_types=str(parts[5]),
                            stand_id=" ".join(parts[6:]),
                            icao_width_code=icao_width_code,
                            operation_type=operation_type,
                        ))

                    except (ValueError, IndexError) as e:
                        print(f"Error parsing stand line: {lines[i].strip()} - {e}")
            i += 1
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

    def parse_com_frequencies(self) -> List[ComFrequency]:
        """CODES: 1050-1056 (8.33 kHz, kHz integer) with 50-56 (legacy) fallback.

        Per the apt.dat 1200 spec: if any 1050-1056 row exists, the legacy
        50-56 rows must be ignored. Only when no modern rows are present do
        we fall back to the legacy ones.
        """
        modern: List[ComFrequency] = []
        legacy: List[ComFrequency] = []

        for line in self.raw_data:
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            try:
                code = int(parts[0])
            except ValueError:
                continue

            if code in _COM_CHANNEL_MAP:
                try:
                    freq_khz = int(parts[1])
                    modern.append(ComFrequency(
                        service=_COM_CHANNEL_MAP[code],
                        frequency_mhz=freq_khz / 1000.0,
                        name=" ".join(parts[2:]) if len(parts) > 2 else _COM_CHANNEL_MAP[code],
                    ))
                except (ValueError, IndexError) as e:
                    print(f"Error parsing COM frequency line: {line.strip()} - {e}")
                continue

            if code in _COM_LEGACY_MAP:
                try:
                    legacy.append(ComFrequency(
                        service=_COM_LEGACY_MAP[code],
                        frequency_mhz=int(parts[1]) / 100.0,
                        name=" ".join(parts[2:]) if len(parts) > 2 else _COM_LEGACY_MAP[code],
                    ))
                except (ValueError, IndexError) as e:
                    print(f"Error parsing legacy COM frequency line: {line.strip()} - {e}")

        return modern if modern else legacy

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

def parse_airport(file_path: str) -> dict:
    """
    Parse an airport .dat file and return all data as a plain dict.

    Returns:
        Dict with keys: nodes, edges, stands, runways,
        traffic_patterns, airport_info.  Each value is a list of dicts.
    """
    parser = AptDatParser(file_path=file_path)
    return {
        "nodes": [n.__dict__ for n in parser.parse_nodes()],
        "edges": [e.__dict__ for e in parser.parse_edges()],
        "stands": [s.__dict__ for s in parser.parse_stands()],
        "runways": [r.__dict__ for r in parser.parse_runways()],
        "traffic_patterns": [p.__dict__ for p in parser.parse_traffic_pattern()],
        "airport_info": [i.__dict__ for i in parser.parse_airport_info()],
        "com_frequencies": [c.__dict__ for c in parser.parse_com_frequencies()],
    }


if __name__ == "__main__":

    import json
    from pathlib import Path

    ICAO = (sys.argv[1] if len(sys.argv) > 1 else "LEBL").upper()

    BASE_DIR = Path(__file__).resolve().parents[2]
    INPUT_FILE = BASE_DIR / "data" / "airport_data" / ICAO / f"{ICAO}.dat"
    OUTPUT_FILE = BASE_DIR / "data" / "airport_data" / ICAO / f"{ICAO}_graph.json"

    airport_data = parse_airport(str(INPUT_FILE))

    for section, items in airport_data.items():
        print(f"Found {len(items)} {section}")

    # Save to JSON file
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(airport_data, indent=2, fp=f)
    print(f"\nData saved to {OUTPUT_FILE}")

    # Store in Redis for microservices access
    try:
        import sys
        sys.path.insert(0, str(BASE_DIR / "shared"))
        from services.airport_data_store import AirportDataStore

        store = AirportDataStore()
        store.store(ICAO, airport_data)
        print(f"Data stored in Redis under airport:current:*")
    except Exception as e:
        print(f"Redis storage skipped: {e}")