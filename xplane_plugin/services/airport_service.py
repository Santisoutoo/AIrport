from pathlib import Path
from typing import Optional

from XPPython3 import xp
from XPPython3.utils.datarefs import find_dataref

from ...data.scripts.airport_data_fetcher import XPlaneAirportDownloader
from ...plugins.GND.data_parser import parse_airport
from ...shared.models.airport import AirportInfo
from ...shared.services.airport_data_store import AirportDataStore


class AirportService:
    """Detecta el aeropuerto más cercano a la posición del avión."""

    _lat_ref = None
    _lon_ref = None
    _last_loaded_icao: Optional[str] = None
    _store: Optional[AirportDataStore] = None

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
    def load_airport_data(cls, icao: str) -> bool:
        """
        Descarga, parsea y almacena en Redis los datos del aeropuerto.

        Solo actúa si el ICAO es distinto al último cargado.
        Retorna True si se cargaron datos nuevos.
        """
        if not icao or icao == cls._last_loaded_icao:
            return False

        try:
            # Descargar .dat si no existe
            base_dir = Path(__file__).resolve().parents[3]
            output_dir = base_dir / "data" / "airport_data"
            downloader = XPlaneAirportDownloader(icao, output_directory=output_dir)
            dat_path = downloader.download(verbose=False)

            if dat_path is None:
                xp.log(f"AIrport: No .dat data found for {icao}")
                return False

            # Parsear
            airport_data = parse_airport(str(dat_path))

            # Guardar en Redis
            if cls._store is None:
                cls._store = AirportDataStore()
            cls._store.store(icao, airport_data)

            cls._last_loaded_icao = icao
            xp.log(f"AIrport: Loaded airport data for {icao} into Redis")
            return True

        except Exception as e:
            xp.log(f"AIrport: Error loading airport data for {icao}: {e}")
            return False

    @classmethod
    def reset(cls):
        cls._lat_ref = None
        cls._lon_ref = None
        cls._last_loaded_icao = None
        cls._store = None


if __name__ == '__main__':
    a = AirportService()
    print(a.get_icao())
