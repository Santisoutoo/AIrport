from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String

from .connection import Base


class ATISModel(Base):
    """ATIS database model for storing generated ATIS broadcasts"""

    __tablename__ = "atis_broadcasts"

    id = Column(Integer, primary_key=True, index=True)
    icao_code = Column(String(4), nullable=False, index=True)
    atis_letter = Column(String(1), nullable=False)
    observation_time = Column(DateTime, nullable=False)

    # Wind
    wind_direction = Column(Integer, nullable=False)
    wind_speed = Column(Integer, nullable=False)
    wind_gust = Column(Integer, nullable=True)
    wind_variable = Column(Boolean, default=False)
    wind_variable_from = Column(Integer, nullable=True)
    wind_variable_to = Column(Integer, nullable=True)

    # Visibility
    visibility_m = Column(Integer, nullable=False)

    # Weather
    weather = Column(String(50), nullable=True)
    weather_description = Column(String(200), nullable=True)

    # Clouds (stored as JSON array)
    clouds = Column(JSON, default=[])
    ceiling_ft = Column(Integer, nullable=True)
    cavok = Column(Boolean, default=False)

    # Temperature
    temperature_c = Column(Integer, nullable=False)
    dewpoint_c = Column(Integer, nullable=False)

    # Pressure
    qnh_hpa = Column(Integer, nullable=False)

    # Runway and approach
    departure_runway = Column(String(10), nullable=True)
    arrival_runway = Column(String(10), nullable=True)
    approach_type = Column(String(20), nullable=True)
    transition_level = Column(String(10), nullable=False)
    transition_altitude = Column(Integer, nullable=False)

    # ATIS text
    remarks = Column(String(500), nullable=True)
    raw_metar = Column(String(500), nullable=False)
    atis_text = Column(String(2000), nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<ATIS {self.icao_code} Information {self.atis_letter}>"
