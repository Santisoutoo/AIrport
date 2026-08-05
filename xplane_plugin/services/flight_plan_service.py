from typing import Tuple

import requests


class FlightPlanService:
    """Service to communicate with the Flight Plans API."""

    def __init__(self, base_url: str = "http://localhost:8003"):
        self.base_url = base_url
        self.api_path = "/api/v1/flight-plan"

    def _get_url(self, endpoint: str) -> str:
        return f"{self.base_url}{self.api_path}{endpoint}"

    def health_check(self) -> bool:
        """Check if the service is available."""
        try:
            response = requests.get(self._get_url("/health"), timeout=5)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def generate_flight_plan(self, departure: str = None) -> Tuple[bool, dict | str]:
        """
        Generate a flight plan and save it to the database.
        Returns (success, flight_plan_data | error_message).
        """
        try:
            params = {"departure": departure} if departure else {}
            response = requests.get(self._get_url("/generate"), params=params, timeout=10)
            if response.status_code == 200:
                return True, response.json()
            else:
                return False, f"Error {response.status_code}: {response.text}"
        except requests.RequestException as e:
            return False, f"Connection error: {str(e)}"

    def generate_multiple(self, count: int, departure: str = None) -> Tuple[bool, list | str]:
        """
        Generate multiple flight plans.
        Returns (success, list_of_flight_plans | error_message).
        """
        flight_plans = []
        for i in range(count):
            success, result = self.generate_flight_plan(departure=departure)
            if not success:
                return False, f"Failed at flight plan {i + 1}: {result}"
            flight_plans.append(result)
        return True, flight_plans

    def clear_all(self) -> Tuple[bool, str]:
        """
        Delete all existing flight plans.
        Returns (success, message).
        """
        try:
            response = requests.delete(self._get_url("/plans"), timeout=10)
            if response.status_code == 200:
                data = response.json()
                return True, f"Deleted {data.get('deleted_count', 0)} flight plans"
            else:
                return False, f"Error {response.status_code}: {response.text}"
        except requests.RequestException as e:
            return False, f"Connection error: {str(e)}"

    def get_all(self) -> Tuple[bool, list | str]:
        """
        Get all flight plans.
        Returns (success, list_of_flight_plans | error_message).
        """
        try:
            response = requests.get(self._get_url("/plans"), timeout=10)
            if response.status_code == 200:
                return True, response.json()
            else:
                return False, f"Error {response.status_code}: {response.text}"
        except requests.RequestException as e:
            return False, f"Connection error: {str(e)}"

    def get_count(self) -> Tuple[bool, int | str]:
        """
        Get the number of flight plans.
        Returns (success, count | error_message).
        """
        try:
            response = requests.get(self._get_url("/plans/count"), timeout=5)
            if response.status_code == 200:
                return True, response.json().get("count", 0)
            else:
                return False, f"Error {response.status_code}: {response.text}"
        except requests.RequestException as e:
            return False, f"Connection error: {str(e)}"
