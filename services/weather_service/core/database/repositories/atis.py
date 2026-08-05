from datetime import datetime, timedelta

from core.database.models import ATISModel
from models.schemas import ATISResponse, CloudLayer
from sqlalchemy.orm import Session


class ATISRepository:
    """ATIS CRUD operations"""

    def __init__(self, db: Session):
        self.db = db

    def create(self, atis: ATISResponse) -> ATISModel:
        """Create a new ATIS record"""
        db_atis = ATISModel(
            icao_code=atis.icao_code,
            atis_letter=atis.atis_letter,
            observation_time=atis.observation_time,
            wind_direction=atis.wind_direction,
            wind_speed=atis.wind_speed,
            wind_gust=atis.wind_gust,
            wind_variable=atis.wind_variable,
            wind_variable_from=atis.wind_variable_from,
            wind_variable_to=atis.wind_variable_to,
            visibility_m=atis.visibility_m,
            weather=atis.weather,
            weather_description=atis.weather_description,
            clouds=[{"coverage": c.coverage, "base_ft": c.base_ft} for c in atis.clouds],
            ceiling_ft=atis.ceiling_ft,
            cavok=atis.cavok,
            temperature_c=atis.temperature_c,
            dewpoint_c=atis.dewpoint_c,
            qnh_hpa=atis.qnh_hpa,
            departure_runway=atis.departure_runway,
            arrival_runway=atis.arrival_runway,
            approach_type=atis.approach_type,
            transition_level=atis.transition_level,
            transition_altitude=atis.transition_altitude,
            remarks=atis.remarks,
            raw_metar=atis.raw_metar,
            atis_text=atis.atis_text,
        )
        self.db.add(db_atis)
        self.db.commit()
        self.db.refresh(db_atis)
        return db_atis

    def get_latest_by_icao(self, icao_code: str) -> ATISModel | None:
        """Get the most recent ATIS for an airport"""
        return (
            self.db.query(ATISModel)
            .filter(ATISModel.icao_code == icao_code.upper())
            .order_by(ATISModel.created_at.desc())
            .first()
        )

    def get_by_icao_and_letter(self, icao_code: str, letter: str) -> ATISModel | None:
        """Get ATIS by airport and letter identifier"""
        return (
            self.db.query(ATISModel)
            .filter(ATISModel.icao_code == icao_code.upper(), ATISModel.atis_letter == letter.upper())
            .order_by(ATISModel.created_at.desc())
            .first()
        )

    def get_all_by_icao(self, icao_code: str, limit: int = 10) -> list[ATISModel]:
        """Get all ATIS records for an airport"""
        return (
            self.db.query(ATISModel)
            .filter(ATISModel.icao_code == icao_code.upper())
            .order_by(ATISModel.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_recent(self, hours: int = 24) -> list[ATISModel]:
        """Get all ATIS records from the last N hours"""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return (
            self.db.query(ATISModel).filter(ATISModel.created_at >= cutoff).order_by(ATISModel.created_at.desc()).all()
        )

    def count(self) -> int:
        """Get total count of ATIS records"""
        return self.db.query(ATISModel).count()

    def count_by_icao(self, icao_code: str) -> int:
        """Get count of ATIS records for an airport"""
        return self.db.query(ATISModel).filter(ATISModel.icao_code == icao_code.upper()).count()

    def delete_by_icao(self, icao_code: str) -> int:
        """Delete all ATIS records for an airport"""
        count = self.db.query(ATISModel).filter(ATISModel.icao_code == icao_code.upper()).count()
        self.db.query(ATISModel).filter(ATISModel.icao_code == icao_code.upper()).delete()
        self.db.commit()
        return count

    def delete_old(self, hours: int = 48) -> int:
        """Delete ATIS records older than N hours"""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        count = self.db.query(ATISModel).filter(ATISModel.created_at < cutoff).count()
        self.db.query(ATISModel).filter(ATISModel.created_at < cutoff).delete()
        self.db.commit()
        return count

    def delete_all(self) -> int:
        """Delete all ATIS records"""
        count = self.db.query(ATISModel).count()
        self.db.query(ATISModel).delete()
        self.db.commit()
        return count

    @staticmethod
    def to_response(model: ATISModel) -> ATISResponse:
        """Convert database model to response schema"""
        clouds = [CloudLayer(coverage=c["coverage"], base_ft=c["base_ft"]) for c in (model.clouds or [])]

        return ATISResponse(
            icao_code=model.icao_code,
            atis_letter=model.atis_letter,
            observation_time=model.observation_time,
            wind_direction=model.wind_direction,
            wind_speed=model.wind_speed,
            wind_gust=model.wind_gust,
            wind_variable=model.wind_variable,
            wind_variable_from=model.wind_variable_from,
            wind_variable_to=model.wind_variable_to,
            visibility_m=model.visibility_m,
            weather=model.weather,
            weather_description=model.weather_description,
            clouds=clouds,
            ceiling_ft=model.ceiling_ft,
            cavok=model.cavok,
            temperature_c=model.temperature_c,
            dewpoint_c=model.dewpoint_c,
            qnh_hpa=model.qnh_hpa,
            departure_runway=model.departure_runway,
            arrival_runway=model.arrival_runway,
            approach_type=model.approach_type,
            transition_level=model.transition_level,
            transition_altitude=model.transition_altitude,
            remarks=model.remarks,
            raw_metar=model.raw_metar,
            atis_text=model.atis_text,
        )
