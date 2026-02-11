from typing import Optional
from XPPython3 import xp
from XPPython3.utils.datarefs import find_dataref

from ...shared.models.airport import AirportInfo


class AirportService:
    """Detecta el aeropuerto más cercano a la posición del avión."""

    _lat_ref = None
    _lon_ref = None

    @classmethod
    def _ensure_datarefs(cls):
        if cls._lat_ref is None:
            cls._lat_ref = find_dataref("sim/flightmodel/position/latitude")
            cls._lon_ref = find_dataref("sim/flightmodel/position/longitude")

    @classmethod
    def get_current_airport(cls) -> Optional[AirportInfo]:
        """Obtiene el aeropuerto más cercano."""
        cls._ensure_datarefs()
        lat = float(cls._lat_ref.value)
        lon = float(cls._lon_ref.value)

        navRef = xp.findNavAid(lat=lat, lon=lon, navType=xp.Nav_Airport)
        if navRef == xp.NAV_NOT_FOUND:
            return None

        info = xp.getNavAidInfo(navRef)
        return AirportInfo(
            icao=info.navAidID,
            name=info.name,
            latitude=info.latitude,
            longitude=info.longitude,
        )

    @classmethod
    def get_icao(cls) -> str:
        """Devuelve solo el código ICAO."""
        airport = cls.get_current_airport()
        return airport.icao if airport else ""

    @classmethod
    def reset(cls):
        cls._lat_ref = None
        cls._lon_ref = None


if __name__ == '__main__':
    a = AirportService()
    print(a.get_icao())