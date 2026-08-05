import os

import requests

HMI_URL = os.getenv("HMI_SERVICE_URL", "http://localhost:8005")


class HmiService:
    """Comunica datos del plugin X-Plane al controller_hmi_service."""

    @classmethod
    def send_airport(cls, icao: str) -> bool:
        """Envía el ICAO actual al HMI service. Retorna True si tuvo éxito."""
        try:
            resp = requests.post(
                f"{HMI_URL}/api/v1/hmi/airport",
                json={"icao": icao},
                timeout=5,
            )
            return resp.status_code == 200
        except requests.RequestException:
            return False
