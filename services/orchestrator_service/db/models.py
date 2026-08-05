from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from db.connection import Base


def _now():
    return datetime.now(timezone.utc)


class AircraftClearance(Base):
    __tablename__ = "aircraft_clearances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    aircraft_registration = Column(String(20), unique=True, nullable=False, index=True)
    session_id = Column(String(100), nullable=True)

    # DEL clearance fields
    squawk = Column(Integer, nullable=True)
    initial_altitude = Column(Integer, nullable=True)
    instrumental_departure = Column(String(20), nullable=True)  # SID
    runway_in_use = Column(String(10), nullable=True)
    altimeter = Column(Float, nullable=True)
    destination_icao = Column(String(4), nullable=True)
    clearance_text = Column(Text, nullable=True)

    # Lifecycle
    # APP = inbound on the ILS, before being switched to Tower
    # DEL → GND → TWR is the departure path.
    # APP → TWR → GND is the arrival path (reverse handoff after landing).
    dependency = Column(String(10), default="DEL", nullable=False)  # APP | DEL | GND | TWR
    taxi_route = Column(JSONB, nullable=True)  # populated by GND agent later

    cleared_at = Column(DateTime(timezone=True), default=_now, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)
