import logging
import os
from typing import Any

import httpx
from google.adk.tools import ToolContext

logger = logging.getLogger(__name__)

_FLIGHT_PLAN_URL = os.environ.get("FLIGHT_PLAN_SERVICE_URL", "")
_WEATHER_URL = os.environ.get("WEATHER_SERVICE_URL", "")

_ROUTES: dict[str, tuple[str, str]] = {
    "DEL": (os.environ.get("DEL_AGENT_URL", ""), "/agents/delivery/run"),
    "GND": (os.environ.get("GND_AGENT_URL", ""), "/agents/ground/run"),
    "TWR": (os.environ.get("TWR_AGENT_URL", ""), "/agents/tower/run"),
}


def _fetch_flight_plan(registration: str) -> dict | None:
    if not _FLIGHT_PLAN_URL:
        return None
    try:
        resp = httpx.get(f"{_FLIGHT_PLAN_URL}/plans/{registration}", timeout=5)
        return resp.json() if resp.status_code == 200 else None
    except Exception as exc:
        logger.warning("[ORCH] could not fetch flight plan for %s: %s", registration, exc)
        return None


def _fetch_atis(departure_icao: str) -> dict | None:
    if not _WEATHER_URL or not departure_icao:
        return None
    try:
        resp = httpx.get(f"{_WEATHER_URL}/atis/{departure_icao}", timeout=5)
        return resp.json() if resp.status_code == 200 else None
    except Exception as exc:
        logger.warning("[ORCH] could not fetch ATIS for %s: %s", departure_icao, exc)
        return None


def forward_to_agent(
    dependency: str,
    registration: str,
    message: str,
    tool_context: ToolContext,
    taxi_route: dict | None = None,
) -> str:
    """
    Forward the pilot message to the correct ATC controller agent and return
    the agent's clearance or instruction text.

    Args:
        dependency:   Controller to call — "DEL", "GND", or "TWR".
        registration: Aircraft callsign in canonical form (e.g. "EC-MIG").
        message:      The pilot message with the callsign corrected.
        taxi_route:   Pre-computed taxi route dict from get_taxi_route().
                      When provided (GND taxi clearances), it is merged into
                      clearance_data so the GND agent can produce a correct
                      readback without needing to call any routing tool itself.
    """
    dep = dependency.upper()
    if dep not in _ROUTES:
        dep = "DEL"

    agent_url, agent_path = _ROUTES[dep]
    if not agent_url:
        logger.error("[ORCH] %s agent URL not configured", dep)
        return f"[ERROR] {dep} agent is not configured"

    session_id = tool_context.state.get("session_id", "")
    target = f"{agent_url}{agent_path}"

    logger.info("[ORCH] forwarding to %s | reg=%s | session=%s | msg=%r",
                dep, registration, session_id, message[:80])

    payload: dict[str, Any] = {"session_id": session_id, "message": message}

    if dep == "DEL" and registration:
        # Pre-fetch flight plan and ATIS for the DEL agent
        flight_plan = _fetch_flight_plan(registration)
        payload["flight_plan"] = flight_plan
        departure_icao = (flight_plan or {}).get("departure_ICAO") or (flight_plan or {}).get("departure_icao", "")
        payload["atis"] = _fetch_atis(departure_icao)
        logger.debug("[ORCH] DEL payload — flight_plan=%s atis=%s",
                     bool(flight_plan), bool(payload.get("atis")))
    else:
        # For GND/TWR pass the full clearance data already stored in state
        known = tool_context.state.get("known_aircraft", [])
        aircraft_data = next(
            (a for a in known if a.get("registration") == registration), {}
        )
        clearance_fields = {
            k: v for k, v in aircraft_data.items()
            if k not in ("registration", "dependency", "source")
        }
        # Merge the pre-computed taxi route so the GND agent knows the exact
        # waypoints and can produce a correct pilot readback.
        if taxi_route and taxi_route.get("success"):
            clearance_fields["taxi_route"] = taxi_route
        if clearance_fields:
            payload["clearance_data"] = clearance_fields
            logger.debug("[ORCH] %s payload — clearance_data=%s", dep, clearance_fields)

    reply = ""
    clearance_data = None
    try:
        resp = httpx.post(target, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        reply = data.get("reply", "")
        clearance_data = data.get("clearance_data")
        logger.info("[ORCH] %s reply: %r", dep, reply[:100])
    except httpx.HTTPStatusError as exc:
        reply = f"[ERROR] {dep} agent returned HTTP {exc.response.status_code}"
        logger.error("[ORCH] %s HTTP error: %s", dep, exc)
    except httpx.RequestError as exc:
        reply = f"[ERROR] could not reach {dep} agent at {target}: {exc}"
        logger.error("[ORCH] %s unreachable: %s", dep, exc)

    # Write results to session state — runner.py reads these after the agent finishes
    tool_context.state["reply"] = reply
    tool_context.state["dependency"] = dep
    tool_context.state["registration"] = registration or None
    tool_context.state["clearance_data"] = clearance_data

    return reply
