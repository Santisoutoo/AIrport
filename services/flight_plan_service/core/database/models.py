from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime

from .connection import Base


class FlightPlanModel(Base):
    """Flight Plan database model"""

    __tablename__ = "flight_plans"

    id = Column(Integer, primary_key=True, index=True)
    aircraft_registration = Column(String(10), unique=True, index=True, nullable=False)
    flight_rules = Column(String(1), nullable=False)  # I or V
    flight_type = Column(String(1), nullable=False)   # G, S, N, M
    aircraft_type = Column(String(10), nullable=False)
    equipment = Column(String(50))
    transponder = Column(String(20))
    departure_icao = Column(String(4), nullable=False, index=True)
    departure_time = Column(Integer)
    cruising_speed = Column(Integer)
    cruising_altitude = Column(Integer)
    route = Column(String(500))
    destination_icao = Column(String(4), nullable=False, index=True)
    total_eet = Column(String(4))
    alternate_icao = Column(String(4))
    second_alternate_icao = Column(String(4))
    other_info = Column(String(500))
    endurance = Column(String(4))
    people_on_board = Column(String(10))
    pic_name = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<FlightPlan {self.aircraft_registration}: {self.departure_icao} -> {self.destination_icao}>"
