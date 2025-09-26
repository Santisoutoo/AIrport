"""
DISCLAIMER: THIS INFORMATION IS NOT INTENDED FOR REAL OPERATIONS.
THE DATA IS UPDATED BY ENTHUSIASTS WHO VOLUNTEER THEIR TIME TO UPDATE SCENERY'S INFORMATION.
"""

from dataclasses import dataclass
from typing import List, Optional

@dataclass
class AirportInfo():
    """
    CODES: 1 and 1302
    """

    metdata: List

@dataclass
class Runway:
    """
    CODE: 100
    Represents a land runway in X-Plane airport data.
    
    Attributes:
        number_1 (str): First runway end number.
        lat_1 (float): First runway end latitude.
        lon_1 (float): First runway end longitude.
        number_2 (str): Second runway end number.
        lat_2 (float): Second runway end latitude.
        lon_2 (float): Second runway end longitude.
    """
    runway_1_id: str
    lat: float
    lon: float
    runway_2_id: str
    lat_2: float
    lon_2: float

@dataclass
class TaxiNode:
    """
    CODE: 1201
    Represents a node in the taxiway network of an airport.
    
    Attributes:
        lat (float): Latitude of the node.
        lon (float): Longitude of the node.
        id (int): Unique identifier for the node.
        usage (str): Usage type of the node. Can be:
            - "dest": Destination node.
            - "init": Initial node.
            - "both": Both destination and initial node.
            - "junc": Junction node.
        name (str): Name or label of the node.
    """
    lat: float
    lon: float
    node_id: int
    usage: str
    name: str

@dataclass
class TaxiEdge:
    """
    CODE: 1202
    Represents an edge (taxiway segment) connecting two taxi nodes.
    
    Attributes:
        start_node_id (int): ID of the starting node.
        end_node_id (int): ID of the ending node.
        direction (str): Direction of the taxiway segment.
        atc_restriction (str): ATC restriction for the edge. Possible values include:
            - "runway": The edge represents a runway. Clearance from ATC is required
              before an aircraft can enter, cross, or taxi on this segment.
            - "taxiway_a", "taxiway_b", ...: The edge represents a taxiway with a
              maximum wingspan restriction. The trailing letter indicates the maximum
              aircraft wingspan category allowed to use this taxiway.
        taxiway_id (Optional[str]): Optional identifier for the specific taxiway.
            Defaults to None if not specified.
    """
    start_node_id: int
    end_node_id: int
    direction: str
    atc_restriction: str
    taxiway_id: Optional[str] = None

@dataclass
class Stand:
    """
    CODE: 1300
    Represents a start or end point for aircraft. Not linked to taxi routing 
    network by edges (row code 1202).
    
    Attributes:
        latitude (float): Latitude of location in decimal degrees. 
                         Eight decimal places supported.
        longitude (float): Longitude of location in decimal degrees. 
                          Eight decimal places supported.
        true_hdg (float): Heading (true) of airplane positioned at this location.
                         Decimal degrees, true heading.
        stand_type (str): Type of location. Possible values include:
                         - "gate": Gate position for passenger boarding/disembarking
                         - "hangar": Hangar position for aircraft maintenance/storage
                         - "misc": Miscellaneous location type
                         - "tie-down": Tie-down position for aircraft parking
        allowed_aircraft_types (str): Airplane types that can use this location.
                                     Pipe-separated list (e.g., "A320|B737|jets").
        id (str): Unique name of location. Text string, must be unique within 
                 a single airport.
    """
    latitude: float
    longitude: float
    true_hdg: float
    stand_type: str
    allowed_aircraft_types: str
    stand_id: str

@dataclass
class TrafficPattern():
    """
    CODE 1101

    This information in some AD is not reliable and do not reflect
    real operations
    
    Represents the avaliable traffic patterns for AD rwys
    Attributes:
        runway_id (str): Identifier of the runways
        side (str): traffic patterns avalible for the rwy
    """
    runway_id: str
    side: str
