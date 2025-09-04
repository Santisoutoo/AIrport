from dataclasses import dataclass
from typing import Optional

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
   id: int
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