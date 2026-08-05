import random
from datetime import datetime, timedelta

from models.schemas import FlightPlanResponse
from core.data import (
    AIRCRAFT_DATA, AIRPORT_DATA, DISTANCES, PILOT_NAMES,
    AIRLINE_DATA, AIRLINE_REGISTRATION_PREFIX,
)
from core.registration import generate_registration


class FlightPlanGenerator:
    """Generates complete flight plans automatically"""

    def __init__(self):
        self.aircraft_types = list(AIRCRAFT_DATA.keys())
        self.airports = list(AIRPORT_DATA.keys())

    def generate(self, departure: str = None) -> FlightPlanResponse:
        """Generate a complete flight plan with all fields auto-generated"""

        # Generate random values
        aircraft_type = self._generate_aircraft_type()
        departure, destination = self._generate_route_pair(departure)
        flight_rules = self._generate_flight_rules(aircraft_type)
        pic_name = self._generate_pilot_name()
        passengers = self._generate_passengers(aircraft_type)

        # Determine airline and callsign
        is_commercial = aircraft_type not in ("C172", "PA28")
        if is_commercial:
            airline_icao = self._select_airline(aircraft_type)
            airline = AIRLINE_DATA[airline_icao]
            callsign = self._generate_callsign(airline_icao)
            prefix = AIRLINE_REGISTRATION_PREFIX.get(airline["country"], "EC")
            aircraft_reg = generate_registration(prefix)
            flight_type = "S"  # Scheduled
        else:
            callsign = ""
            aircraft_reg = generate_registration("EC")
            flight_type = "G"  # General aviation

        # Get aircraft data
        aircraft = AIRCRAFT_DATA[aircraft_type]
        cruise_speed = aircraft["speed"]

        # Calculate route and times
        distance = self._get_distance(departure, destination)
        eet_hours = distance / cruise_speed
        eet_minutes = int(eet_hours * 60)

        # Determine cruise altitude
        cruise_alt = self._calculate_cruise_altitude(distance, flight_rules)

        # Generate route string
        route = self._generate_route_string(departure, destination, cruise_alt)

        # Get alternates
        alternate, second_alternate = self._get_alternates(destination)

        # Calculate departure time (random within next 2 hours)
        now = datetime.utcnow()
        random_minutes = random.randint(10, 120)
        departure_time = now + timedelta(minutes=random_minutes)
        departure_time = departure_time.replace(second=0, microsecond=0)
        # Round to nearest 5 minutes
        departure_time = departure_time.replace(minute=(departure_time.minute // 5) * 5)
        dep_time_int = int(departure_time.strftime("%H%M"))

        # Calculate endurance (EET + 45min reserve)
        endurance_minutes = eet_minutes + 45
        endurance_str = f"{endurance_minutes // 60:02d}{endurance_minutes % 60:02d}"

        return FlightPlanResponse(
            aircraft_registration=aircraft_reg,
            flight_rules=flight_rules,
            flight_type=flight_type,
            aircraft_type=aircraft_type,
            wake_turbulence_category=aircraft["wtc"],
            equipment=aircraft["equipment"],
            transponder=aircraft["transponder"],
            departure_ICAO=departure,
            departure_time=dep_time_int,
            cruising_speed=cruise_speed,
            cruising_altitude=cruise_alt,
            route=route,
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

    def _generate_aircraft_type(self) -> str:
        """Generate random aircraft type"""
        return random.choice(self.aircraft_types)

    def _select_airline(self, aircraft_type: str) -> str:
        """Select a random airline that operates the given aircraft type"""
        compatible = [
            icao for icao, data in AIRLINE_DATA.items()
            if aircraft_type in data["aircraft_types"]
        ]
        return random.choice(compatible)

    def _generate_callsign(self, airline_icao: str) -> str:
        """Generate airline callsign: ICAO prefix + 3-4 digit flight number"""
        flight_number = random.randint(100, 9999)
        return f"{airline_icao}{flight_number}"

    def _generate_route_pair(self, departure: str = None) -> tuple[str, str]:
        """Force departure to the given ICAO; fall back to LEST if unsupported."""
        if departure and departure in self.airports:
            dep = departure
        else:
            dep = "LEST" if "LEST" in self.airports else self.airports[0]
        available_destinations = [a for a in self.airports if a != dep]
        destination = random.choice(available_destinations)
        return dep, destination

    def _generate_flight_rules(self, aircraft_type: str) -> str:
        return "I"

    def _generate_pilot_name(self) -> str:
        """Generate random pilot name"""
        return random.choice(PILOT_NAMES)

    def _generate_passengers(self, aircraft_type: str) -> int:
        """Generate random passenger count based on aircraft"""
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

    def _get_distance(self, departure: str, destination: str) -> int:
        """Get distance between airports in nautical miles"""
        key = (departure, destination)
        reverse_key = (destination, departure)

        if key in DISTANCES:
            return DISTANCES[key]
        elif reverse_key in DISTANCES:
            return DISTANCES[reverse_key]
        else:
            # Estimate based on random value
            return random.randint(150, 400)

    def _calculate_cruise_altitude(self, distance: int, flight_rules: str) -> int:
        """Calculate appropriate cruise altitude"""
        if flight_rules == "V":  # VFR
            if distance < 50:
                return 3500
            elif distance < 150:
                return 5500
            else:
                return 7500
        else:  # IFR
            if distance < 100:
                return 10000
            elif distance < 300:
                return 25000
            else:
                return 35000

    def _generate_route_string(self, departure: str, destination: str, altitude: int) -> str:
        """Generate a route string"""
        if altitude >= 25000:
            return "DCT UN871 DCT"
        elif altitude >= 10000:
            return "DCT UQ10 DCT"
        else:
            return "DCT"

    def _get_alternates(self, destination: str) -> tuple[str, str]:
        """Get alternate airports for destination"""
        if destination in AIRPORT_DATA:
            alternates = AIRPORT_DATA[destination]["alternates"]
            alt1 = alternates[0] if len(alternates) > 0 else ""
            alt2 = alternates[1] if len(alternates) > 1 else ""
            return alt1, alt2
        return "", ""
