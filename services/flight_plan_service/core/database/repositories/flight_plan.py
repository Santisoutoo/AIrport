from sqlalchemy.orm import Session

from core.database.models import FlightPlanModel
from models.schemas import FlightPlanResponse


class FlightPlanRepository:
    """Repository for FlightPlan CRUD operations"""

    def __init__(self, db: Session):
        self.db = db

    def create(self, flight_plan: FlightPlanResponse) -> FlightPlanModel:
        """Create a new flight plan"""
        db_flight_plan = FlightPlanModel(
            aircraft_registration=flight_plan.aircraft_registration,
            flight_rules=flight_plan.flight_rules,
            flight_type=flight_plan.flight_type,
            aircraft_type=flight_plan.aircraft_type,
            wake_turbulence_category=flight_plan.wake_turbulence_category,
            equipment=flight_plan.equipment,
            transponder=flight_plan.transponder,
            departure_icao=flight_plan.departure_ICAO,
            departure_time=flight_plan.departure_time,
            cruising_speed=flight_plan.cruising_speed,
            cruising_altitude=flight_plan.cruising_altitude,
            route=flight_plan.route,
            destination_icao=flight_plan.destination_ICAO,
            total_eet=flight_plan.total_EET,
            alternate_icao=flight_plan.alternate_ICAO,
            second_alternate_icao=flight_plan.second_alternate_ICAO,
            other_info=flight_plan.other_info,
            endurance=flight_plan.endurance,
            people_on_board=flight_plan.people_on_board,
            remarks=flight_plan.remarks,
            pic_name=flight_plan.PIC_name,
            callsign=flight_plan.callsign,
        )
        self.db.add(db_flight_plan)
        self.db.commit()
        self.db.refresh(db_flight_plan)
        return db_flight_plan

    def get_by_registration(self, registration: str) -> FlightPlanModel | None:
        """Get flight plan by aircraft registration"""
        return (
            self.db.query(FlightPlanModel).filter(FlightPlanModel.aircraft_registration == registration.upper()).first()
        )

    def get_all(self) -> list[FlightPlanModel]:
        """Get all flight plans"""
        return self.db.query(FlightPlanModel).order_by(FlightPlanModel.created_at.desc()).all()

    def count(self) -> int:
        """Get total count of flight plans"""
        return self.db.query(FlightPlanModel).count()

    def delete(self, registration: str) -> bool:
        """Delete flight plan by registration"""
        flight_plan = self.get_by_registration(registration)
        if flight_plan:
            self.db.delete(flight_plan)
            self.db.commit()
            return True
        return False

    def delete_all(self) -> int:
        """Delete all flight plans, returns count of deleted"""
        count = self.db.query(FlightPlanModel).count()
        self.db.query(FlightPlanModel).delete()
        self.db.commit()
        return count

    @staticmethod
    def to_response(model: FlightPlanModel) -> FlightPlanResponse:
        """Convert database model to response schema"""
        return FlightPlanResponse(
            aircraft_registration=model.aircraft_registration,
            flight_rules=model.flight_rules,
            flight_type=model.flight_type,
            aircraft_type=model.aircraft_type,
            wake_turbulence_category=model.wake_turbulence_category or "",
            equipment=model.equipment,
            transponder=model.transponder,
            departure_ICAO=model.departure_icao,
            departure_time=model.departure_time,
            cruising_speed=model.cruising_speed,
            cruising_altitude=model.cruising_altitude,
            route=model.route,
            destination_ICAO=model.destination_icao,
            total_EET=model.total_eet,
            alternate_ICAO=model.alternate_icao,
            second_alternate_ICAO=model.second_alternate_icao,
            other_info=model.other_info,
            endurance=model.endurance,
            people_on_board=model.people_on_board,
            remarks=model.remarks or "",
            PIC_name=model.pic_name,
            callsign=model.callsign or "",
        )
