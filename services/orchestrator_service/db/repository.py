from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from db.models import AircraftClearance


class ClearanceRepository:
    def __init__(self, db: Session):
        self._db = db

    def upsert(
        self,
        registration: str,
        session_id: Optional[str],
        squawk: int,
        initial_altitude: int,
        instrumental_departure: str,
        runway_in_use: str,
        altimeter: float,
        destination_icao: str,
        clearance_text: str,
        dependency: str = "DEL",
    ) -> AircraftClearance:
        record = (
            self._db.query(AircraftClearance).filter(AircraftClearance.aircraft_registration == registration).first()
        )
        if record is None:
            record = AircraftClearance(aircraft_registration=registration)
            self._db.add(record)

        record.session_id = session_id
        record.squawk = squawk
        record.initial_altitude = initial_altitude
        record.instrumental_departure = instrumental_departure
        record.runway_in_use = runway_in_use
        record.altimeter = altimeter
        record.destination_icao = destination_icao
        record.clearance_text = clearance_text
        record.dependency = dependency
        record.cleared_at = datetime.now(timezone.utc)
        record.updated_at = datetime.now(timezone.utc)

        self._db.commit()
        self._db.refresh(record)
        return record

    def get(self, registration: str) -> Optional[AircraftClearance]:
        return self._db.query(AircraftClearance).filter(AircraftClearance.aircraft_registration == registration).first()

    def update_dependency(self, registration: str, dependency: str) -> bool:
        updated = (
            self._db.query(AircraftClearance)
            .filter(AircraftClearance.aircraft_registration == registration)
            .update({"dependency": dependency, "updated_at": datetime.now(timezone.utc)})
        )
        self._db.commit()
        return updated > 0
