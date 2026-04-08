from typing import Optional

from google.adk.tools import ToolContext
from shared.services.taxi_router import compute_taxi_route


def get_taxi_route(
    registration: str,
    destination: str,
    tool_context: ToolContext,
    via: Optional[list[str]] = None,
) -> dict:
    """
    Compute the taxi route for an aircraft before forwarding the instruction
    to the GND agent.

    Call this tool when the controller issues a taxi clearance to GND-phase
    aircraft. The result must be passed as `taxi_route` to `forward_to_agent`
    so the GND pilot agent can produce the correct readback.

    Args:
        registration: Aircraft registration / callsign (e.g. "EC-MIG").
                      Used to look up the aircraft's current GPS position in
                      Redis when no explicit origin is needed.
        destination:  Runway or holding-point designator (e.g. "06R", "24L").
        via:          Ordered list of taxiways the controller specified
                      (e.g. ["B", "D", "E"]). Pass an empty list or None if
                      the controller did not specify via taxiways.

    Returns:
        {"success": True, "waypoints": [...], "taxiway_sequence": [...],
         "total_distance_m": float, "start": {...}, "end": {...}}
        or {"success": False, "error": "..."}.
    """
    return compute_taxi_route(
        destination=destination,
        via=via or [],
        callsign=registration,
    )
