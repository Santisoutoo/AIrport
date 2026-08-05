from datetime import datetime
from typing import Optional
import logging
import string

from models.schemas import ATISResponse, CloudLayer
from core.metar_taf_fetcher import NoWeatherDataError, get_metar

logger = logging.getLogger(__name__)


# dummy data
AIRPORT_DATA = {
    "LEST": {
        "name": "Santiago",
        "runways": ["17", "35"],
        "elevation": 1213,
        "transition_altitude": 6000,
        "approaches": {"17": ["ILS", "VOR", "RNAV"], "35": ["VOR", "RNAV"]},
    },
    "LEBL": {
        "name": "Barcelona El Prat",
        "runways": ["02", "20", "07L", "07R", "25L", "25R"],
        "elevation": 12,
        "transition_altitude": 6000,
        "approaches": {"25R": ["ILS", "RNAV"], "25L": ["ILS", "RNAV"], "02": ["ILS", "RNAV"], "07R": ["ILS", "RNAV"]},
    },
    "LEMD": {
        "name": "Madrid Barajas",
        "runways": ["14L", "14R", "18L", "18R", "32L", "32R", "36L", "36R"],
        "elevation": 2000,
        "transition_altitude": 6000,
        "approaches": {"32L": ["ILS", "RNAV"], "32R": ["ILS", "RNAV"], "18L": ["ILS", "RNAV"], "18R": ["ILS", "RNAV"]},
    },
    "LECO": {
        "name": "A Coruña",
        "runways": ["03", "21"],
        "elevation": 326,
        "transition_altitude": 6000,
        "approaches": {"21": ["VOR", "RNAV"], "03": ["VOR", "RNAV"]},
    },
    "LEVX": {
        "name": "Vigo",
        "runways": ["02", "20"],
        "elevation": 856,
        "transition_altitude": 6000,
        "approaches": {"20": ["ILS", "VOR", "RNAV"], "02": ["VOR", "RNAV"]},
    },
    "LEGE": {
        "name": "Girona Costa Brava",
        "runways": ["02", "20"],
        "elevation": 468,
        "transition_altitude": 6000,
        "approaches": {"02": ["ILS", "RNAV"], "20": ["VOR", "RNAV"]},
    },
    "LEPA": {
        "name": "Palma de Mallorca",
        "runways": ["06L", "06R", "24L", "24R"],
        "elevation": 27,
        "transition_altitude": 6000,
        "approaches": {"24L": ["ILS", "RNAV"], "24R": ["ILS", "RNAV"], "06L": ["ILS", "RNAV"], "06R": ["ILS", "RNAV"]},
    },
    "LEVC": {
        "name": "Valencia",
        "runways": ["12", "30"],
        "elevation": 240,
        "transition_altitude": 6000,
        "approaches": {"30": ["ILS", "RNAV"], "12": ["ILS", "RNAV"]},
    },
    "LEAL": {
        "name": "Alicante-Elche",
        "runways": ["10", "28"],
        "elevation": 141,
        "transition_altitude": 6000,
        "approaches": {"28": ["ILS", "RNAV"], "10": ["ILS", "RNAV"]},
    },
    "LEZL": {
        "name": "Sevilla",
        "runways": ["09", "27"],
        "elevation": 112,
        "transition_altitude": 6000,
        "approaches": {"27": ["ILS", "RNAV"], "09": ["VOR", "RNAV"]},
    },
    "LEMG": {
        "name": "Málaga Costa del Sol",
        "runways": ["13", "31"],
        "elevation": 52,
        "transition_altitude": 6000,
        "approaches": {"31": ["ILS", "RNAV"], "13": ["ILS", "RNAV"]},
    },
}

PHONETIC_ALPHABET = [
    "ALFA",
    "BRAVO",
    "CHARLIE",
    "DELTA",
    "ECHO",
    "FOXTROT",
    "GOLF",
    "HOTEL",
    "INDIA",
    "JULIET",
    "KILO",
    "LIMA",
    "MIKE",
    "NOVEMBER",
    "OSCAR",
    "PAPA",
    "QUEBEC",
    "ROMEO",
    "SIERRA",
    "TANGO",
    "UNIFORM",
    "VICTOR",
    "WHISKEY",
    "XRAY",
    "YANKEE",
    "ZULU",
]

WEATHER_DESCRIPTIONS = {
    "RA": "rain",
    "SN": "snow",
    "DZ": "drizzle",
    "FG": "fog",
    "BR": "mist",
    "HZ": "haze",
    "TS": "thunderstorm",
    "SH": "showers",
    "GR": "hail",
    "FZ": "freezing",
    "+RA": "heavy rain",
    "-RA": "light rain",
    "+SN": "heavy snow",
    "-SN": "light snow",
    "TSRA": "thunderstorm with rain",
    "VCSH": "showers in vicinity",
}

CLOUD_COVERAGE = {
    "FEW": "few",
    "SCT": "scattered",
    "BKN": "broken",
    "OVC": "overcast",
}


class ATISGenerator:
    """Generates ATIS broadcasts from METAR data"""

    def __init__(self):
        self.airports = AIRPORT_DATA
        self._atis_counters: dict[str, int] = {}

    async def generate(
        self,
        icao_code: str,
        departure_runway=None,
        arrival_runway=None,
        approach=None,
        qfe: Optional[int] = None,
        include_tl: bool = True,
        include_ta: bool = True,
        remarks: Optional[str] = None,
        preview: bool = False,
    ) -> ATISResponse:
        """
        Generate a complete ATIS broadcast for an airport.

        Args:
            icao_code: ICAO airport code
            departure_runway: Departure runway (set by ATC). If None, auto-selected from wind.
            arrival_runway: Arrival runway (set by ATC). If None, auto-selected from wind.
            approach: Approach type (set by ATC). If None, auto-selected for the chosen runway.

        Returns:
            ATISResponse with complete ATIS data
        """
        icao_code = icao_code.upper()

        # Fetch current METAR
        metar_data = await self._fetch_metar(icao_code)

        # Parse METAR data
        parsed = self._parse_metar(metar_data)

        # Get airport data
        airport = self.airports.get(icao_code, self._get_default_airport(icao_code))

        # Auto-select runways from wind when not provided by ATC
        if arrival_runway is None and not parsed.get("wind_variable"):
            arrival_runway = self._select_runway_from_wind(parsed["wind_direction"], airport["runways"])
        if departure_runway is None and not parsed.get("wind_variable"):
            departure_runway = self._select_runway_from_wind(parsed["wind_direction"], airport["runways"])

        # Auto-select approach type for arrival runway when not provided by ATC
        if approach is None and arrival_runway:
            approach = self._select_approach_for_runway(arrival_runway, airport)

        # Get next ATIS letter (preview mode: no increment)
        atis_letter = self._get_next_atis_letter(icao_code, preview=preview)

        # Calculate transition level
        transition_level = self._calculate_transition_level(parsed["qnh_hpa"])

        # Generate ATIS text
        atis_text = self._generate_atis_text(
            icao_code=icao_code,
            atis_letter=atis_letter,
            parsed=parsed,
            departure_runway=departure_runway,
            arrival_runway=arrival_runway,
            approach=approach,
            transition_level=transition_level,
            transition_altitude=airport["transition_altitude"],
            airport_name=airport.get("name", icao_code),
            qfe=qfe,
            include_tl=include_tl,
            include_ta=include_ta,
            remarks=remarks,
        )

        return ATISResponse(
            icao_code=icao_code,
            atis_letter=atis_letter,
            observation_time=parsed["observation_time"],
            wind_direction=parsed["wind_direction"],
            wind_speed=parsed["wind_speed"],
            wind_gust=parsed.get("wind_gust"),
            wind_variable=parsed.get("wind_variable", False),
            wind_variable_from=parsed.get("wind_variable_from"),
            wind_variable_to=parsed.get("wind_variable_to"),
            visibility_m=parsed["visibility_m"],
            weather=parsed.get("weather"),
            weather_description=parsed.get("weather_description"),
            clouds=parsed.get("clouds", []),
            ceiling_ft=parsed.get("ceiling_ft"),
            cavok=parsed.get("cavok", False),
            temperature_c=parsed["temperature_c"],
            dewpoint_c=parsed["dewpoint_c"],
            qnh_hpa=parsed["qnh_hpa"],
            departure_runway=departure_runway,
            arrival_runway=arrival_runway,
            approach_type=approach,
            transition_level=transition_level,
            transition_altitude=airport["transition_altitude"],
            remarks=remarks,
            raw_metar=parsed["raw_metar"],
            atis_text=atis_text,
        )

    async def _fetch_metar(self, icao_code: str) -> dict:
        """Fetch METAR data from the upstream API.

        Raises:
            NoWeatherDataError: the upstream has no observation for this
                airport (the API layer maps this to a 404).
            WeatherUpstreamError: the upstream is unreachable or answered with
                an error status. Deliberately *not* converted to ``ValueError``:
                an upstream outage is a 502, not "airport not found".
        """
        data = await get_metar(icao_code, output_format="json")
        if data and len(data) > 0:
            return data[0]
        logger.info("No METAR data available for %s", icao_code)
        raise NoWeatherDataError(f"No METAR data available for {icao_code}")

    def _parse_metar(self, metar_data: dict) -> dict:
        """Parse METAR JSON data into structured format"""
        result = {
            "raw_metar": metar_data.get("rawOb", ""),
            "observation_time": datetime.fromisoformat(
                metar_data.get("reportTime", datetime.utcnow().isoformat()).replace("Z", "+00:00")
            ),
        }

        # Wind
        wdir = metar_data.get("wdir")
        if wdir == "VRB" or wdir is None:
            result["wind_direction"] = 0
            result["wind_variable"] = True
        else:
            result["wind_direction"] = int(wdir)
            result["wind_variable"] = False

        result["wind_speed"] = int(metar_data.get("wspd", 0))
        result["wind_gust"] = int(metar_data.get("wgst")) if metar_data.get("wgst") else None

        # Visibility
        raw_ob = metar_data.get("rawOb", "")
        visib = metar_data.get("visib")
        if " 9999 " in f" {raw_ob} ":
            result["visibility_m"] = 9999
        elif visib:
            visib_clean = str(visib).replace("+", "")
            result["visibility_m"] = min(int(float(visib_clean) * 1609.34), 9999)
        else:
            result["visibility_m"] = 9999

        # Weather phenomena
        wx_string = metar_data.get("wxString")
        if wx_string:
            result["weather"] = wx_string
            result["weather_description"] = WEATHER_DESCRIPTIONS.get(wx_string, wx_string)

        # Clouds
        clouds = []
        ceiling = None
        for cloud in metar_data.get("clouds", []):
            cover = cloud.get("cover")
            base = cloud.get("base")
            if cover and base is not None:
                clouds.append(CloudLayer(coverage=cover, base_ft=int(base)))
                if cover in ["BKN", "OVC"] and (ceiling is None or int(base) < ceiling):
                    ceiling = int(base)

        result["clouds"] = clouds
        result["ceiling_ft"] = ceiling

        # Temperature
        result["temperature_c"] = int(metar_data.get("temp", 15))
        result["dewpoint_c"] = int(metar_data.get("dewp", 10))

        # Pressure (altim from aviationweather.gov is already in hPa)
        altim = metar_data.get("altim")
        if altim:
            result["qnh_hpa"] = int(float(altim))
        else:
            result["qnh_hpa"] = 1013

        return result

    def _select_runway_from_wind(self, wind_direction: int, runways: list) -> Optional[str]:
        """Select the runway that provides the best headwind alignment."""
        best_rwy = None
        best_score = -1

        for rwy in runways:
            # Strip L/R/C suffix to get the numeric heading
            rwy_num = rwy.rstrip("LRC")
            try:
                rwy_hdg = int(rwy_num) * 10
            except ValueError:
                continue

            angle_diff = abs(wind_direction - rwy_hdg) % 360
            if angle_diff > 180:
                angle_diff = 360 - angle_diff
            # score: 180 = pure headwind, 0 = pure tailwind
            score = 180 - angle_diff
            if score > best_score:
                best_score = score
                best_rwy = rwy

        return best_rwy

    def _select_approach_for_runway(self, runway: str, airport: dict) -> Optional[str]:
        """Select the best available approach type for the given runway (ILS > VOR > RNAV)."""
        approaches = airport.get("approaches", {})
        available = approaches.get(runway, [])
        for preferred in ("ILS", "VOR", "RNAV"):
            if preferred in available:
                return preferred
        return available[0] if available else None

    def _get_next_atis_letter(self, icao_code: str, preview: bool = False) -> str:
        """Get the next ATIS letter in sequence for the airport.
        In preview mode the counter is NOT incremented."""
        current = self._atis_counters.get(icao_code, -1)
        next_idx = (current + 1) % 26
        if not preview:
            self._atis_counters[icao_code] = next_idx
        return string.ascii_uppercase[next_idx]

    def _calculate_transition_level(self, qnh_hpa: int) -> str:
        """
        Calculate transition level based on QNH.
        """
        if qnh_hpa >= 1032:
            return "FL65"
        if qnh_hpa >= 1014:
            return "FL70"
        if qnh_hpa >= 996:
            return "FL75"
        if qnh_hpa >= 978:
            return "FL80"
        return "FL90"

    def _get_default_airport(self, icao_code: str) -> dict:
        """Return default airport data for unknown airports"""
        # TODO: implement this funcion with apt.dat files

        return {
            "name": icao_code,
            "runways": ["09", "27"],
            "elevation": 0,
            "transition_altitude": 6000,
            "approaches": {"09": ["RNAV"], "27": ["RNAV"]},
        }

    def _generate_atis_text(
        self,
        icao_code: str,
        atis_letter: str,
        parsed: dict,
        departure_runway: str,
        arrival_runway: str,
        approach: str,
        transition_level: str,
        transition_altitude: int,
        airport_name: str,
        qfe: Optional[int] = None,
        include_tl: bool = True,
        include_ta: bool = True,
        remarks: Optional[str] = None,
    ) -> str:
        """Generate the full ATIS broadcast text"""
        phonetic = PHONETIC_ALPHABET[string.ascii_uppercase.index(atis_letter)]
        obs_time = parsed["observation_time"].strftime("%H%M")

        lines = [
            f"{airport_name} information {phonetic}.",
        ]

        # Runways - only if set by ATC
        if departure_runway:
            lines.append(f"Departure runway {departure_runway}.")
        if arrival_runway:
            lines.append(f"Arrival runway {arrival_runway}.")

        # Approach - only if set by ATC
        if approach:
            lines.append(f"{approach} approach available.")

        # Wind
        if parsed.get("wind_variable") or parsed["wind_direction"] == 0:
            lines.append(f"Wind variable at {parsed['wind_speed']} knots.")
        else:
            wind_text = f"Wind {parsed['wind_direction']:03d} degrees, {parsed['wind_speed']} knots"
            if parsed.get("wind_gust"):
                wind_text += f", gusting {parsed['wind_gust']}"
            lines.append(wind_text + ".")

        # Visibility
        if parsed.get("cavok"):
            lines.append("CAVOK.")
        else:
            vis_km = parsed["visibility_m"] / 1000
            lines.append(f"Visibility {vis_km:.1f} kilometers.")

        # Weather
        if parsed.get("weather_description"):
            lines.append(f"Weather: {parsed['weather_description']}.")

        # Clouds
        if parsed.get("clouds"):
            cloud_text = []
            for cloud in parsed["clouds"]:
                coverage = CLOUD_COVERAGE.get(cloud.coverage, cloud.coverage)
                cloud_text.append(f"{coverage} at {cloud.base_ft} feet")
            lines.append(f"Clouds {', '.join(cloud_text)}.")

        # Temperature
        lines.append(f"Temperature {parsed['temperature_c']}, dewpoint {parsed['dewpoint_c']}.")

        # QNH
        lines.append(f"QNH {parsed['qnh_hpa']} hectopascals.")

        # QFE (only if provided by ATC)
        if qfe:
            lines.append(f"QFE {qfe} hectopascals.")

        # Transition level and altitude (conditional)
        if include_tl:
            lines.append(f"Transition level {transition_level}.")
        if include_ta:
            lines.append(f"Transition altitude {transition_altitude} feet.")

        # Time and closing
        lines.append(f"Information {phonetic} recorded at {obs_time} Zulu.")
        lines.append(f"Advise on initial contact you have information {phonetic}.")

        # Remarks
        if remarks and remarks.strip():
            lines.append(f"RMK {remarks.strip()}")

        return " ".join(lines)
