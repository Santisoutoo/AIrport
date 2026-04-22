import logging
from typing import Any

from google.adk.tools import ToolContext

logger = logging.getLogger(__name__)


def get_known_aircraft(tool_context: ToolContext) -> list[dict[str, Any]]:
    """
    Return the list of known aircraft with their current ATC dependency.

    Each item has:
      - registration (str): aircraft registration, e.g. "EC-MIG"
      - callsign (str):     operational callsign, e.g. "VLG1234" (airline) or "EC-MIG" (GA)
      - dependency (str):   current controller — "DEL", "GND", or "TWR"
      - source (str):       where the record came from ("db", "flight_plan", "redis")
      - squawk, initial_altitude, runway_in_use, ... (only for GND/TWR aircraft)

    Data is pre-fetched before the agent starts and stored in session state.
    """
    aircraft = tool_context.state.get("known_aircraft", [])
    logger.debug("[ORCH] get_known_aircraft → %d aircraft", len(aircraft))
    return aircraft
