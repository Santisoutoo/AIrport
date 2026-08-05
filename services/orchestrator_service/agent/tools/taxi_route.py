from google.adk.tools import ToolContext

from shared.services.taxi_router import compute_taxi_route


def get_taxi_route(
    registration: str,
    instruction_text: str,
    tool_context: ToolContext,
) -> dict:
    """
    Compute the taxi route for an aircraft from the raw controller instruction.

    Extracts destination and via taxiways directly from instruction_text using
    regex patterns so the orchestrator LLM does not need to parse them manually.

    Args:
        registration:     Aircraft registration used to look up GPS position
                          in Redis (e.g. "EI-MQE").
        instruction_text: Full controller instruction as transcribed (e.g.
                          "RYR7398 taxi holding point E1 runway 17 via T").

    Returns:
        {"success": True, "waypoints": [...], "taxiway_sequence": [...],
         "total_distance_m": float, ...}
        or {"success": False, "error": "..."}.
    """
    from shared.services.taxi_router.destination_parser import extract_destination
    from shared.services.taxi_router.readback_parser import extract_taxiway_tokens
    from shared.services.taxi_router.router import _load_graph

    # Load the airport graph to get valid taxiway tokens for this airport.
    try:
        graph = _load_graph()
        known_tokens = list(graph._nodes_by_taxiway.keys())
    except Exception:
        known_tokens = None

    destination = extract_destination(instruction_text)
    # dedup=False: a clearance may legitimately revisit a taxiway
    # ("via A, B, A") and strict routing (issue #69) must keep the order.
    via = extract_taxiway_tokens(
        taxi_route_text=None,
        fallback_text=instruction_text,
        known_tokens=known_tokens,
        dedup=False,
    )

    # If the destination token also appeared as a via token, remove it from via
    # (e.g. "E1" is both a known taxiway and the destination holding point).
    if destination:
        dest_upper = destination.upper()
        via = [v for v in via if v.upper() != dest_upper]

    # If regex found no destination, treat the last via token as destination.
    if not destination and via:
        destination = via.pop()

    if not destination:
        return {
            "success": False,
            "error": "No destination found in instruction. Check the taxi clearance text.",
        }

    return compute_taxi_route(destination=destination, via=via, callsign=registration)
