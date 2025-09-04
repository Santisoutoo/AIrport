from dataclasses import dataclass

@dataclass
class TaxiNode:
    """
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