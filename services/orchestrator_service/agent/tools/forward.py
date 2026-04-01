import logging
from typing import Any

import httpx
from sqlalchemy.orm import Session

from config import config
from db.repository import ClearanceRepository

logger = logging.getLogger(__name__)

_AGENT_ROUTES: dict[str, tuple[str, str]] = {
    "DEL": (config.DEL_AGENT_URL, "/agents/delivery/run"),
    "GND": (config.GND_AGENT_URL, "/agents/ground/run"),
    "TWR": (config.TWR_AGENT_URL, "/agents/tower/run"),
}


def _fetch_flight_plan(registration: str) -> dict | None:
    try:
        resp = httpx.get(
            f"{config.FLIGHT_PLAN_SERVICE_URL}/plans/{registration}", timeout=5
        )
        return resp.json() if resp.status_code == 200 else None
    except Exception as exc:
        logger.warning("Could not fetch flight plan for %s: %s",
                       registration, exc)
        return None


def _fetch_atis(departure_icao: str) -> dict | None:
    if not departure_icao:
        return None
    try:
        resp = httpx.get(
            f"{config.WEATHER_SERVICE_URL}/atis/{departure_icao}", timeout=5
        )
        return resp.json() if resp.status_code == 200 else None
    except Exception as exc:
        logger.warning("Could not fetch ATIS for %s: %s", departure_icao, exc)
        return None


def make_forward_to_agent(session_id: str, db: Session, context: dict[str, Any]):
    """
    Factory that returns a `forward_to_agent` tool bound to the given session,
    DB session, and context dict.
    """

    def forward_to_agent(dependency: str, registration: str, message: str) -> str:
        """
        Forward the pilot message to the correct ATC controller agent and return
        the agent's clearance or instruction text.

        Args:
            dependency:   Controller to call — "DEL", "GND", or "TWR".
            registration: Aircraft callsign in canonical form (e.g. "EC-MIG").
                          Use empty string if the callsign could not be identified.
            message:      The pilot message with the callsign corrected.

        Returns:
            The controller's reply text, ready to be read back to the pilot.
        """
        dep = dependency.upper()
        if dep not in _AGENT_ROUTES:
            dep = "DEL"

        agent_url, agent_path = _AGENT_ROUTES[dep]
        target = f"{agent_url}{agent_path}"

        logger.info(
            "Forwarding to %s | reg=%s | session=%s | msg='%s'",
            dep, registration, session_id, message,
        )

        # Build request payload — for DEL pre-fetch context so it needs no callbacks
        payload: dict[str, Any] = {
            "session_id": session_id, "message": message}
        if dep == "DEL" and registration:
            flight_plan = _fetch_flight_plan(registration)
            payload["flight_plan"] = flight_plan
            departure_icao = (flight_plan or {}).get("departure_icao", "")
            payload["atis"] = _fetch_atis(departure_icao)

        reply = ""
        try:
            resp = httpx.post(target, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            reply = data.get("reply", "")

            # Persist clearance returned by DEL directly via repository
            if dep == "DEL" and data.get("clearance_data"):
                cd = data["clearance_data"]
                try:
                    ClearanceRepository(db).upsert(
                        registration=cd["aircraft_registration"],
                        session_id=session_id,
                        squawk=cd["squawk"],
                        initial_altitude=cd["initial_altitude"],
                        instrumental_departure=cd["instrumental_departure"],
                        runway_in_use=cd["runway_in_use"],
                        altimeter=cd["altimeter"],
                        destination_icao=cd["destination_icao"],
                        clearance_text=cd["clearance_text"],
                    )
                    logger.info("Clearance persisted for %s",
                                cd["aircraft_registration"])
                except Exception as exc:
                    logger.error("Failed to persist clearance: %s", exc)

        except httpx.HTTPStatusError as exc:
            reply = f"[ERROR] {dep} agent returned HTTP {exc.response.status_code}"
            logger.error("Agent %s HTTP error: %s", dep, exc)
        except httpx.RequestError as exc:
            reply = f"[ERROR] Could not reach {dep} agent at {target}: {exc}"
            logger.error("Agent %s unreachable: %s", dep, exc)

        context["dependency"] = dep
        context["registration"] = registration or None
        context["reply"] = reply

        return reply

    return forward_to_agent
