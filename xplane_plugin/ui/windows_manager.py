import os
import traceback
import webbrowser
from typing import Optional, Any

# El plugin corre en el host (no en Docker) — forzar Redis a localhost
os.environ["REDIS_HOST"] = "localhost"
os.environ["REDIS_PORT"] = "6379"

from XPPython3 import xp
from XPPython3.xp_typing import XPLMCommandRef

from ..services.airport_service import AirportService
from ..services.hmi_service import HmiService

SETUP_URL = "http://localhost:8005/setup"


class WindowManager:
    """Gestiona la comunicacion con X-Plane y el polling de comandos via Redis."""

    def __init__(self):
        self.cmd: Optional[XPLMCommandRef] = None
        self.cmdRef = None
        self.icao_loop_id = None
        self.cmd_loop_id = None

        # Instancias activas de sesion (creadas en el hilo X-Plane)
        self._aircraft_spawner = None
        self._tracker = None
        self._state_store = None
        self._store = None

    def register_plugin(self) -> tuple[str, str, str]:
        """Registra el comando de menu y arranca los flight loops."""
        self.cmd = xp.createCommand(
            'xppython3/airport/openUI',
            'Open AIrport Interface'
        )
        xp.registerCommandHandler(self.cmd, self._commandHandler, 1, self.cmdRef)
        xp.appendMenuItemWithCommand(xp.findPluginsMenu(), 'AIrport', self.cmd)

        # Limpiar estado Redis al arrancar para que el HMI redirija a /setup
        self._reset_redis()

        # Loop 30s: sincroniza ICAO con HMI service
        self.icao_loop_id = xp.createFlightLoop(self._sync_airport_callback, phase=1)
        xp.scheduleFlightLoop(self.icao_loop_id, interval=30.0)

        # Loop 2s: polling de comandos Redis (session start/stop)
        self.cmd_loop_id = xp.createFlightLoop(self._poll_redis, phase=1)
        xp.scheduleFlightLoop(self.cmd_loop_id, interval=2.0)

        return 'PI_AIrport_v1.0', 'com.airport.atc', 'AIrport ATC Simulator'

    def _reset_redis(self):
        try:
            import redis
            r = redis.from_url("redis://localhost:6379", decode_responses=True)
            r.delete("airport:session_request")
        except Exception as e:
            xp.log(f"AIrport: Redis reset warning: {e}")

    # ------------------------------------------------------------------
    # Command handler: abre el navegador en la pagina de setup del HMI
    # ------------------------------------------------------------------

    def _commandHandler(self, cmdRef: XPLMCommandRef, phase: int, refCon: Any) -> int:
        if phase == xp.CommandBegin:
            webbrowser.open(SETUP_URL)
        return 1

    # ------------------------------------------------------------------
    # Flight loop 30s: sincroniza ICAO
    # ------------------------------------------------------------------

    def _sync_airport_callback(self, sinceLast, elapsedTime, counter, refCon):
        icao = AirportService.get_icao()
        if icao:
            HmiService.send_airport(icao)
        return 30.0

    # ------------------------------------------------------------------
    # Flight loop 2s: polling Redis para ejecutar comandos de sesion
    # ------------------------------------------------------------------

    def _poll_redis(self, sinceLast, elapsedTime, counter, refCon):
        try:
            import redis
            r = redis.from_url("redis://localhost:6379", decode_responses=True)
            data = r.hgetall("airport:session_request")
            status = data.get("status", "")

            if status == "pending":
                self._execute_start_from_redis(r, data)
            elif status == "stop_pending":
                self._execute_stop_session()
                r.delete("airport:session_request")
        except ImportError:
            xp.log("AIrport: redis package not installed — pip install redis")
        except Exception as e:
            xp.log(f"AIrport: Redis poll error: {e}")
        return 2.0

    def _execute_start_from_redis(self, r, data: dict):
        """Ejecuta el inicio de sesion leyendo los parametros de Redis."""
        from ..services.aircraft_spawner import AircraftSpawner
        from ..services.flight_plan_service import FlightPlanService
        from ...shared.services.aircraft_tracker import AircraftTracker
        from ...shared.services.aircraft_state_store import AircraftStateStore
        from ...shared.services.airport_data_store import AirportDataStore
        from ...shared.services.stand_assigner import StandAssigner
        from ...shared.models.aircraft_state import AircraftState

        icao = data.get("icao", "")
        aircraft_count = int(data.get("aircraft_count", 5))

        # Marcar como en progreso para no procesar dos veces
        r.hset("airport:session_request", "status", "starting")

        try:
            # Cargar datos del aeropuerto
            if not AirportService.load_airport_data(icao):
                xp.log(f"AIrport: Failed to load airport data for {icao}")
                r.hset("airport:session_request", "status", "error")
                return

            # Generar planes de vuelo
            fp_service = FlightPlanService()
            if not fp_service.health_check():
                xp.log("AIrport: Flight plan service unavailable")
                r.hset("airport:session_request", "status", "error")
                return

            fp_service.clear_all()
            success, result = fp_service.generate_multiple(aircraft_count)
            if not success:
                xp.log(f"AIrport: Failed to generate flight plans: {result}")
                r.hset("airport:session_request", "status", "error")
                return

            # Asignar stands
            store = AirportDataStore()
            stand_assigner = StandAssigner()
            stands = store.get_stands_with_occupancy()
            assignments = stand_assigner.assign(result, stands)

            if not assignments:
                xp.log("AIrport: No compatible stands available")
                r.hset("airport:session_request", "status", "error")
                return

            for a in assignments:
                store.set_stand_occupied(a["stand_id"], True)

            session_id = store.start_session(icao, aircraft_count)

            # Operaciones X-Plane (solo posibles en este hilo)
            self._state_store = AircraftStateStore()
            self._store = store
            self._aircraft_spawner = AircraftSpawner()
            self._tracker = AircraftTracker(self._state_store)

            self._aircraft_spawner.spawn(assignments)
            xp.log(f"AIrport: Spawned {self._aircraft_spawner.count} aircraft")

            self._tracker.set_session(session_id)
            self._tracker.set_user_info(registration="USER", aircraft_type="UNKN", callsign="USER")

            for reg, info in self._aircraft_spawner.registry.items():
                state = AircraftState(
                    session_id=session_id,
                    registration=reg,
                    aircraft_type=info["aircraft_type"],
                    callsign=reg,
                    latitude=info["latitude"],
                    longitude=info["longitude"],
                    altitude_msl=0.0,
                    altitude_agl=0.0,
                    heading=info["true_hdg"],
                    pitch=0.0,
                    roll=0.0,
                    ground_speed=0.0,
                    indicated_airspeed=0.0,
                    vertical_speed=0.0,
                    on_ground=True,
                    squawk=0,
                    phase="parked",
                )
                self._state_store.update(state)

            self._tracker.start()
            xp.log(f"AIrport: Session {session_id} started — tracker at 2Hz")

            # Confirmar al HMI que la sesion esta activa
            r.hset("airport:session_request", mapping={
                "status": "active",
                "session_id": session_id,
            })

        except Exception as e:
            xp.log(f"AIrport: Session start error: {e}")
            xp.log(traceback.format_exc())
            r.hset("airport:session_request", "status", "error")

    def _execute_stop_session(self):
        """Para el tracker y limpia la sesion activa."""
        if self._tracker:
            self._tracker.stop()
            self._tracker = None

        if self._state_store:
            self._state_store.clear_all()
            self._state_store = None

        if self._aircraft_spawner:
            self._aircraft_spawner.clear()
            self._aircraft_spawner = None

        if self._store:
            self._store.end_session()
            self._store = None

        xp.log("AIrport: Session stopped")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self):
        if self.icao_loop_id:
            xp.destroyFlightLoop(self.icao_loop_id)
            self.icao_loop_id = None
        if self.cmd_loop_id:
            xp.destroyFlightLoop(self.cmd_loop_id)
            self.cmd_loop_id = None
        if self.cmd:
            xp.unregisterCommandHandler(self.cmd, self._commandHandler, 1, self.cmdRef)
        xp.clearAllMenuItems(xp.findPluginsMenu())
        self._execute_stop_session()
        AirportService.reset()
