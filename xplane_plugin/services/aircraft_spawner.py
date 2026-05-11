from XPPython3 import xp
from .aircraft_obj_mapper import get_obj_path

_FT_TO_M = 0.3048


class AircraftSpawner:
    """Loads .obj models and places them at stand positions or in the air."""

    def __init__(self):
        self._instances = []   # (instance, obj)
        self._registry = {}    # {instance, obj, latitude, longitude, true_hdg, aircraft_type}
        self._probe = None

    def spawn(self, assignments: list) -> int:
        """Spawn aircraft from a bulk list of assignments.

        Each assignment may include `on_ground` (default True) and
        `altitude_msl_ft` (default 0). When `on_ground=False`, the .obj is
        placed at the given MSL altitude without terrain probing.
        """
        count = 0
        for a in assignments:
            if self._spawn_one(a, fallback_index=count) is not None:
                count += 1
        xp.log(f"AIrport: Spawned {count} aircraft")
        return count

    def spawn_one(self, assignment: dict) -> str | None:
        """Spawn a single aircraft. Returns the registration on success.

        Used by dynamic spawn requests (e.g. arrival simulator).
        """
        return self._spawn_one(assignment, fallback_index=len(self._registry))

    def _spawn_one(self, a: dict, *, fallback_index: int) -> str | None:
        on_ground = bool(a.get("on_ground", True))

        callsign = a.get("callsign", "")
        airline_icao = callsign[:3] if len(callsign) >= 3 else None
        obj_path = get_obj_path(a["aircraft_type"], airline_icao)
        obj = xp.loadObject(obj_path)

        if obj is None:
            xp.log(f"AIrport: Could not load .obj: {obj_path}")
            return None

        altitude_msl_ft = float(a.get("altitude_msl_ft", 0.0))
        alt_m = altitude_msl_ft * _FT_TO_M

        # Convert lat/lon to X-Plane local coordinates
        x, y, z = xp.worldToLocal(
            lat=a["latitude"],
            lon=a["longitude"],
            alt=alt_m,
        )

        if on_ground:
            # Probe terrain to anchor the model on the surface
            if self._probe is None:
                self._probe = xp.createProbe()
            info = xp.probeTerrainXYZ(self._probe, x, y, z)
            if info.result == 0:
                y = info.locationY

        # position tuple: (x, y, z, pitch, heading, roll)
        position = (x, y, z, 0, a["true_hdg"], 0)

        instance = xp.createInstance(obj, [])
        xp.instanceSetPosition(instance, position, [])

        self._instances.append((instance, obj))

        reg = a.get("aircraft_registration", f"AI-{fallback_index}")
        self._registry[reg] = {
            "instance": instance,
            "obj": obj,
            "latitude": a["latitude"],
            "longitude": a["longitude"],
            "true_hdg": a["true_hdg"],
            "altitude_msl_ft": altitude_msl_ft,
            "on_ground": on_ground,
            "aircraft_type": a["aircraft_type"],
            "callsign": a.get("callsign", reg),
        }
        return reg

    def clear(self):
        """Destroy all spawned aircraft instances."""
        for instance, _ in self._instances:
            xp.destroyInstance(instance)
        self._instances.clear()
        self._registry.clear()
        xp.log("AIrport: Cleared all spawned aircraft")

    @property
    def registry(self) -> dict:
        """Return the registration → aircraft info mapping."""
        return self._registry

    @property
    def count(self) -> int:
        """Number of currently spawned aircraft."""
        return len(self._instances)
