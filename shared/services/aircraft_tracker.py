from XPPython3 import xp

from ..models.aircraft_state import AircraftState
from .aircraft_state_store import AircraftStateStore

_USER_DATAREFS = {
    "latitude":           "sim/flightmodel/position/latitude",
    "longitude":          "sim/flightmodel/position/longitude",
    "altitude_msl":       "sim/flightmodel/position/elevation",
    "heading":            "sim/flightmodel/position/true_psi",
    "pitch":              "sim/flightmodel/position/true_theta",
    "roll":               "sim/flightmodel/position/true_phi",
    "ground_speed":       "sim/flightmodel/position/groundspeed",
    "indicated_airspeed": "sim/flightmodel/position/indicated_airspeed",
    "vertical_speed":     "sim/flightmodel/position/vh_ind",
    "altitude_agl":       "sim/flightmodel/position/y_agl",
    "on_ground":          "sim/flightmodel/failures/onground_any",
}


class AircraftTracker:
    """
    Tracks aircraft positions at 2 Hz using X-Plane flight loops.
    """

    def __init__(self, store: AircraftStateStore):
        self._store = store
        self._flight_loop_id = None
        self._running = False

        # Session metadata
        self._session_id = ""
        self._user_registration = "USER"
        self._user_aircraft_type = "UNKN"
        self._user_callsign = "USER"

        # Cached dataref handles (resolved once on start)
        self._user_dref_handles = {}

        # AI aircraft registry: registration -> {datarefs, metadata}
        self._ai_aircraft = {}


    def set_session(self, session_id: str) -> None:
        self._session_id = session_id

    def set_user_info(
        self,
        registration: str = "USER",
        aircraft_type: str = "UNKN",
        callsign: str = "USER",
    ) -> None:
        self._user_registration = registration
        self._user_aircraft_type = aircraft_type
        self._user_callsign = callsign

    def register_ai_aircraft(
        self,
        registration: str,
        aircraft_type: str,
        callsign: str,
        multiplayer_index: int,
    ) -> None:
        """
        Register an AI aircraft for tracking.

        When AI aircraft start moving (future phase), call this method
        to add them to the tracking loop.

        Args:
            registration: Aircraft registration (e.g., EC-ABC).
            aircraft_type: ICAO type (e.g., A320).
            callsign: Flight callsign.
            multiplayer_index: X-Plane multiplayer slot (1-19).
        """
        prefix = f"sim/multiplayer/position/plane{multiplayer_index}"
        self._ai_aircraft[registration] = {
            "aircraft_type": aircraft_type,
            "callsign": callsign,
            "datarefs": {
                "latitude":  f"{prefix}_lat",
                "longitude": f"{prefix}_lon",
                "altitude_msl": f"{prefix}_el",
                "pitch":     f"{prefix}_the",
                "heading":   f"{prefix}_psi",
                "roll":      f"{prefix}_phi",
            },
            "dref_handles": {},
        }

    def unregister_ai_aircraft(self, registration: str) -> None:
        """Remove an AI aircraft from tracking."""
        self._ai_aircraft.pop(registration, None)
        self._store.remove_aircraft(registration)

    # -- Start / Stop ---------------------------------------------------------

    def start(self) -> None:
        """Start the 2 Hz tracking flight loop."""
        if self._running:
            return

        # Resolve user dataref handles
        for name, path in _USER_DATAREFS.items():
            dref = xp.findDataRef(path)
            if dref is not None:
                self._user_dref_handles[name] = dref
            else:
                xp.log(f"AIrport Tracker: dataref not found: {path}")

        # Resolve AI dataref handles
        for reg, info in self._ai_aircraft.items():
            for name, path in info["datarefs"].items():
                dref = xp.findDataRef(path)
                if dref is not None:
                    info["dref_handles"][name] = dref

        # Connect InfluxDB
        self._store.connect_influx()

        # Create flight loop at 2 Hz (interval = -2 means 2x per second)
        self._flight_loop_id = xp.createFlightLoop(self._flight_loop_cb, phase=1)
        xp.scheduleFlightLoop(self._flight_loop_id, interval=-2)
        self._running = True
        xp.log("AIrport Tracker: started at 2 Hz")

    def stop(self) -> None:
        """Stop the tracking flight loop and flush data."""
        if not self._running:
            return

        if self._flight_loop_id is not None:
            xp.destroyFlightLoop(self._flight_loop_id)
            self._flight_loop_id = None

        self._store.flush()
        self._running = False
        xp.log("AIrport Tracker: stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    # -- Flight loop callback -------------------------------------------------

    def _flight_loop_cb(self, sinceLast, elapsedTime, counter, refCon):
        """Called by X-Plane at 2 Hz. Returns -2 to keep 2 Hz schedule."""
        if not self._running:
            return 0  # stop

        self._capture_user_aircraft()
        self._capture_ai_aircraft()

        return -2  # reschedule at 2 Hz

    def _capture_user_aircraft(self) -> None:
        """Read user aircraft datarefs and store the state."""
        handles = self._user_dref_handles
        if not handles:
            return

        try:
            state = AircraftState(
                session_id=self._session_id,
                registration=self._user_registration,
                aircraft_type=self._user_aircraft_type,
                callsign=self._user_callsign,
                latitude=xp.getDataf(handles["latitude"]),
                longitude=xp.getDataf(handles["longitude"]),
                altitude_msl=xp.getDataf(handles["altitude_msl"]),
                altitude_agl=xp.getDataf(handles.get("altitude_agl", handles["altitude_msl"])),
                heading=xp.getDataf(handles["heading"]),
                pitch=xp.getDataf(handles["pitch"]),
                roll=xp.getDataf(handles["roll"]),
                ground_speed=xp.getDataf(handles["ground_speed"]),
                indicated_airspeed=xp.getDataf(handles["indicated_airspeed"]),
                vertical_speed=xp.getDataf(handles["vertical_speed"]),
                on_ground=bool(xp.getDatai(handles["on_ground"])),
                squawk=0,
                phase=self._determine_phase(
                    on_ground=bool(xp.getDatai(handles["on_ground"])),
                    ground_speed=xp.getDataf(handles["ground_speed"]),
                ),
            )
            self._store.update(state)
        except Exception as e:
            xp.log(f"AIrport Tracker: user capture error: {e}")

    def _capture_ai_aircraft(self) -> None:
        """Read AI aircraft datarefs and store their states."""
        for reg, info in self._ai_aircraft.items():
            handles = info["dref_handles"]
            if not handles:
                continue

            try:
                lat = xp.getDataf(handles.get("latitude"))
                lon = xp.getDataf(handles.get("longitude"))

                # Skip if position is 0,0 (aircraft not active)
                if lat == 0.0 and lon == 0.0:
                    continue

                gs = xp.getDataf(handles.get("ground_speed", 0))

                state = AircraftState(
                    session_id=self._session_id,
                    registration=reg,
                    aircraft_type=info["aircraft_type"],
                    callsign=info["callsign"],
                    latitude=lat,
                    longitude=lon,
                    altitude_msl=xp.getDataf(handles.get("altitude_msl", 0)),
                    altitude_agl=0.0,  # not available for multiplayer
                    heading=xp.getDataf(handles.get("heading", 0)),
                    pitch=xp.getDataf(handles.get("pitch", 0)),
                    roll=xp.getDataf(handles.get("roll", 0)),
                    ground_speed=gs,
                    indicated_airspeed=0.0,  # not available for multiplayer
                    vertical_speed=0.0,      # not available for multiplayer
                    on_ground=True,          # assume ground ops for now
                    squawk=0,
                    phase=self._determine_phase(on_ground=True, ground_speed=gs),
                )
                self._store.update(state)
            except Exception as e:
                xp.log(f"AIrport Tracker: AI capture error ({reg}): {e}")

    # -- Helpers --------------------------------------------------------------

    @staticmethod
    def _determine_phase(on_ground: bool, ground_speed: float) -> str:
        """
        Simple phase detection based on ground contact and speed.
        This will be refined as the simulation adds more behaviours.
        """
        if on_ground:
            if ground_speed < 0.5:
                return "parked"
            elif ground_speed < 30:
                return "taxi_out"
            else:
                return "takeoff"
        else:
            if ground_speed < 80:
                return "approach"
            return "approach"
