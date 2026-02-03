import random
import string
from datetime import datetime, timedelta

from models.schemas import FlightPlanResponse


# Aircraft performance data
AIRCRAFT_DATA = {
    "A320": {"speed": 450, "equipment": "SDE2E3FGHIJ1RWXY", "transponder": "LB1D1"},
    "A321": {"speed": 450, "equipment": "SDE2E3FGHIJ1RWXY", "transponder": "LB1D1"},
    "B738": {"speed": 460, "equipment": "SDE2E3FGHIJ1RWXY", "transponder": "LB1D1"},
    "B737": {"speed": 455, "equipment": "SDE2E3FGHIJ1RWXY", "transponder": "LB1D1"},
    "C172": {"speed": 120, "equipment": "SDFGY", "transponder": "S"},
    "PA28": {"speed": 110, "equipment": "SDFY", "transponder": "S"},
    "E190": {"speed": 470, "equipment": "SDE2E3FGHIJ1RWXY", "transponder": "LB1D1"},
}

# Spanish airports with alternates
AIRPORT_DATA = {
    "LEST": {"name": "Santiago", "alternates": ["LECO", "LEVX"], "elevation": 1213},
    "LEBL": {"name": "Barcelona", "alternates": ["LEGE", "LERS"], "elevation": 12},
    "LEMD": {"name": "Madrid Barajas", "alternates": ["LETO", "LECU"], "elevation": 2000},
    "LECO": {"name": "A Coruña", "alternates": ["LEST", "LEVX"], "elevation": 326},
    "LEVX": {"name": "Vigo", "alternates": ["LEST", "LECO"], "elevation": 856},
    "LEGE": {"name": "Girona", "alternates": ["LEBL", "LFMP"], "elevation": 468},
    "LERS": {"name": "Reus", "alternates": ["LEBL", "LEGE"], "elevation": 233},
    "LEPA": {"name": "Palma Mallorca", "alternates": ["LEIB", "LEMH"], "elevation": 27},
    "LEVC": {"name": "Valencia", "alternates": ["LEAL", "LEBL"], "elevation": 240},
    "LEAL": {"name": "Alicante", "alternates": ["LEVC", "LELC"], "elevation": 141},
    "LEZL": {"name": "Sevilla", "alternates": ["LEMG", "LEMD"], "elevation": 112},
    "LEMG": {"name": "Málaga", "alternates": ["LEZL", "LEGR"], "elevation": 52},
}

# Approximate distances between airports (nm)
DISTANCES = {
    ("LEST", "LEBL"): 480,
    ("LEST", "LEMD"): 320,
    ("LEST", "LECO"): 35,
    ("LEBL", "LEMD"): 270,
    ("LEBL", "LEPA"): 130,
    ("LEMD", "LEVC"): 160,
    ("LEMD", "LEZL"): 220,
    ("LEMD", "LEMG"): 260,
    ("LEVC", "LEBL"): 160,
    ("LEAL", "LEBL"): 250,
    ("LEZL", "LEBL"): 500,
}

# Common pilot names for random generation
PILOT_NAMES = [
    "GARCIA MARTINEZ", "RODRIGUEZ LOPEZ", "FERNANDEZ SANCHEZ",
    "GONZALEZ PEREZ", "MARTIN GOMEZ", "RUIZ DIAZ", "HERNANDEZ MUÑOZ",
    "ALVAREZ ROMERO", "JIMENEZ TORRES", "MORENO NAVARRO"
]


class FlightPlanGenerator:
    """Generates complete flight plans automatically"""

    def __init__(self):
        self.aircraft_types = list(AIRCRAFT_DATA.keys())
        self.airports = list(AIRPORT_DATA.keys())

    def generate(self) -> FlightPlanResponse:
        """Generate a complete flight plan with all fields auto-generated"""

        # Generate random values
        aircraft_type = self._generate_aircraft_type()
        aircraft_reg = self._generate_registration()
        departure, destination = self._generate_route_pair()
        flight_rules = self._generate_flight_rules(aircraft_type)
        pic_name = self._generate_pilot_name()
        passengers = self._generate_passengers(aircraft_type)

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
            flight_type="G",  # General aviation
            aircraft_type=aircraft_type,
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
            PIC_name=pic_name,
        )

    def _generate_aircraft_type(self) -> str:
        """Generate random aircraft type"""
        return random.choice(self.aircraft_types)

    def _generate_registration(self) -> str:
        """Generate random Spanish aircraft registration (EC-XXX)"""
        letters = ''.join(random.choices(string.ascii_uppercase, k=3))
        return f"EC-{letters}"

    def _generate_route_pair(self) -> tuple[str, str]:
        """Generate random departure and destination pair"""
        departure = random.choice(self.airports)
        # Ensure destination is different from departure
        available_destinations = [a for a in self.airports if a != departure]
        destination = random.choice(available_destinations)
        return departure, destination

    def _generate_flight_rules(self, aircraft_type: str) -> str:
        """Generate flight rules based on aircraft type"""
        # Small aircraft more likely VFR, large aircraft IFR
        if aircraft_type in ["C172", "PA28"]:
            return random.choice(["V", "V", "I"])  # 66% VFR
        else:
            return "I"  # Always IFR for airliners

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
