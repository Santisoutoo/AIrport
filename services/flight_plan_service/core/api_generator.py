import os
import random
import string
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx

from models.schemas import FlightPlanResponse
from core.data import AIRCRAFT_DATA, PILOT_NAMES, AIRLINE_DATA, AIRLINE_REGISTRATION_PREFIX

logger = logging.getLogger(__name__)

API_BASE_URL = "https://api.flightplandatabase.com"
API_KEY = os.getenv("FLIGHT_PLAN_GENERATOR_KEY", "")

DEPARTURE_ICAO = "LEST"
ALLOWED_DESTINATIONS = ["LEBL", "LEMD", "LEVC", "LEAL"]


class APIFlightPlanGenerator:
    """
    Generates flight plans using FlightPlanDatabase.com for route data.
    Aircraft, pilot and timing data is generated locally.
    Only routes from LEST to LEBL, LEMD, LEVC, LEAL.
    """

    def __init__(self):
        self.aircraft_types = list(AIRCRAFT_DATA.keys())
        self.client = httpx.AsyncClient(
            base_url=API_BASE_URL,
            auth=(API_KEY, ""),
            headers={"X-Units": "AVIATION"},
            timeout=15.0,
        )

    async def generate(self, destination: Optional[str] = None) -> FlightPlanResponse:
        """
        Generate a flight plan with route from FlightPlanDatabase.com API.

        Args:
            destination: ICAO code (LEBL, LEMD, LEVC or LEAL). Random if None.
        """
        if destination:
            destination = destination.upper()
            if destination not in ALLOWED_DESTINATIONS:
                raise ValueError(
                    f"Destination not found for this airport {ALLOWED_DESTINATIONS}, got '{destination}'"
                )
        else:
            destination = random.choice(ALLOWED_DESTINATIONS)

        aircraft_type = random.choice(self.aircraft_types)
        aircraft = AIRCRAFT_DATA[aircraft_type]
        cruise_speed = aircraft["speed"]

        default_cruise_alt = 35000 if aircraft_type not in ["C172", "PA28"] else 7500

        # Call API to generate route
        plan_response = await self._generate_route(
            from_icao=DEPARTURE_ICAO,
            to_icao=destination,
            cruise_alt=default_cruise_alt,
            cruise_speed=cruise_speed,
        )

        plan_id = plan_response["id"]
        api_distance = plan_response.get("distance", 0)
        api_max_altitude = plan_response.get("maxAltitude", default_cruise_alt)

        # Get full route with waypoint nodes
        plan_detail = await self._get_plan_detail(plan_id)
        nodes = plan_detail.get("route", {}).get("nodes", [])

        route_string = self._build_route_string(nodes)

        # Generate remaining fields locally
        flight_rules = self._generate_flight_rules(aircraft_type)
        pic_name = random.choice(PILOT_NAMES)
        passengers = self._generate_passengers(aircraft_type)

        # Determine airline and callsign
        is_commercial = aircraft_type not in ("C172", "PA28")
        if is_commercial:
            airline_icao = self._select_airline(aircraft_type)
            airline = AIRLINE_DATA[airline_icao]
            callsign = self._generate_callsign(airline_icao)
            prefix = AIRLINE_REGISTRATION_PREFIX.get(airline["country"], "EC")
            aircraft_reg = self._generate_registration(prefix)
            flight_type = "S"
        else:
            callsign = ""
            aircraft_reg = self._generate_registration("EC")
            flight_type = "G"

        # Calculate times
        eet_hours = api_distance / cruise_speed if cruise_speed > 0 else 1.0
        eet_minutes = max(int(eet_hours * 60), 1)

        now = datetime.utcnow()
        random_minutes = random.randint(10, 120)
        departure_time = now + timedelta(minutes=random_minutes)
        departure_time = departure_time.replace(second=0, microsecond=0)
        departure_time = departure_time.replace(
            minute=(departure_time.minute // 5) * 5
        )
        dep_time_int = int(departure_time.strftime("%H%M"))

        endurance_minutes = eet_minutes + 45
        endurance_str = f"{endurance_minutes // 60:02d}{endurance_minutes % 60:02d}"

        alternate, second_alternate = self._get_alternates(destination)

        cruising_altitude = int(api_max_altitude)

        return FlightPlanResponse(
            aircraft_registration=aircraft_reg,
            flight_rules=flight_rules,
            flight_type=flight_type,
            aircraft_type=aircraft_type,
            wake_turbulence_category=aircraft["wtc"],
            equipment=aircraft["equipment"],
            transponder=aircraft["transponder"],
            departure_ICAO=DEPARTURE_ICAO,
            departure_time=dep_time_int,
            cruising_speed=cruise_speed,
            cruising_altitude=cruising_altitude,
            route=route_string,
            destination_ICAO=destination,
            total_EET=f"{eet_minutes // 60:02d}{eet_minutes % 60:02d}",
            alternate_ICAO=alternate,
            second_alternate_ICAO=second_alternate,
            other_info=f"PBN/B2C2D2S1 DOF/{now.strftime('%y%m%d')} REG/{aircraft_reg}",
            endurance=endurance_str,
            people_on_board=str(passengers),
            remarks="",
            PIC_name=pic_name,
            callsign=callsign or aircraft_reg,
        )

    async def _generate_route(
        self,
        from_icao: str,
        to_icao: str,
        cruise_alt: int,
        cruise_speed: int,
    ) -> dict:
        """Call POST /auto/generate to create a route."""
        response = await self.client.post(
            "/auto/generate",
            json={
                "fromICAO": from_icao,
                "toICAO": to_icao,
                "cruiseAlt": cruise_alt,
                "cruiseSpeed": cruise_speed,
                "useAWYLO": True,
                "useAWYHI": True,
            },
        )
        response.raise_for_status()
        return response.json()

    async def _get_plan_detail(self, plan_id: int) -> dict:
        """Call GET /plan/{id} to get full route with nodes."""
        response = await self.client.get(f"/plan/{plan_id}")
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _build_route_string(nodes: list[dict]) -> str:
        """
        Build ICAO route string from API route nodes.

        Skips departure (first) and destination (last) airport nodes.
        Collapses consecutive waypoints on the same airway into
        entry_waypoint airway exit_waypoint.
        """
        if len(nodes) < 3:
            return "DCT"

        waypoints = nodes[1:-1]

        parts = []
        current_airway = None
        last_exit_wp = None

        for wp in waypoints:
            via = wp.get("via")
            airway_ident = via.get("ident") if via else None

            if airway_ident and airway_ident == current_airway:
                last_exit_wp = wp["ident"]
                continue

            if current_airway is not None and last_exit_wp:
                parts.append(last_exit_wp)

            if airway_ident:
                if not current_airway:
                    parts.append(wp["ident"])
                parts.append(airway_ident)
                current_airway = airway_ident
                last_exit_wp = wp["ident"]
            else:
                parts.append(wp["ident"])
                current_airway = None
                last_exit_wp = None

        if current_airway is not None and last_exit_wp:
            parts.append(last_exit_wp)

        return " ".join(parts) if parts else "DCT"

    @staticmethod
    def _generate_registration(prefix: str = "EC") -> str:
        letters = "".join(random.choices(string.ascii_uppercase, k=3))
        if prefix.endswith("-"):
            return f"{prefix}{letters}"
        return f"{prefix}-{letters}"

    @staticmethod
    def _select_airline(aircraft_type: str) -> str:
        """Select a random airline that operates the given aircraft type"""
        compatible = [
            icao for icao, data in AIRLINE_DATA.items()
            if aircraft_type in data["aircraft_types"]
        ]
        return random.choice(compatible)

    @staticmethod
    def _generate_callsign(airline_icao: str) -> str:
        """Generate airline callsign: ICAO prefix + 3-4 digit flight number"""
        flight_number = random.randint(100, 9999)
        return f"{airline_icao}{flight_number}"

    @staticmethod
    def _generate_flight_rules(aircraft_type: str) -> str:
        if aircraft_type in ["C172", "PA28"]:
            return random.choice(["V", "V", "I"])
        return "I"

    @staticmethod
    def _generate_passengers(aircraft_type: str) -> int:
        passenger_ranges = {
            "A320": (120, 180),
            "A321": (150, 220),
            "B738": (140, 189),
            "B737": (130, 175),
            "E190": (80, 114),
            "C172": (1, 3),
            "PA28": (1, 3),
        }
        min_pax, max_pax = passenger_ranges.get(aircraft_type, (2, 100))
        return random.randint(min_pax, max_pax)

    @staticmethod
    def _get_alternates(destination: str) -> tuple[str, str]:
        # TODO: implement logic to get alternate airport
        return "LECO", "LEMD"

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
