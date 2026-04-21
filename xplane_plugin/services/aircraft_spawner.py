from XPPython3 import xp
from .aircraft_obj_mapper import get_obj_path


class AircraftSpawner:
    """Loads .obj models and places them at stand positions."""

    def __init__(self):
        self._instances = []   # (instance, obj)
        self._registry = {}    # {instance, obj, latitude, longitude, true_hdg, aircraft_type}
        self._probe = None

    def spawn(self, assignments: list) -> int:
        """
        Spawn static aircraft at their assigned stands.
        """
        # Probe gives the elevation of the current airfield
        # It is done to know the altitude of the .obj in the scenary
        if self._probe is None:
            self._probe = xp.createProbe()

        count = 0

        for a in assignments:
            obj_path = get_obj_path(a["aircraft_type"])
            obj = xp.loadObject(obj_path)

            if obj is None:
                xp.log(f"AIrport: Could not load .obj: {obj_path}")
                continue

            # Convert lat/lon to X-Plane local coordinates
            x, y, z = xp.worldToLocal(
                lat=a["latitude"],
                lon=a["longitude"],
                alt=0,
            )

            # Probe terrain to get correct ground elevation
            info = xp.probeTerrainXYZ(self._probe, x, y, z)
            if info.result == 0:
                y = info.locationY

            # position tuple: (x, y, z, pitch, heading, roll)
            position = (x, y, z, 0, a["true_hdg"], 0)

            instance = xp.createInstance(obj, [])
            xp.instanceSetPosition(instance, position, [])

            self._instances.append((instance, obj))

            # Track by registration for future position queries
            reg = a.get("aircraft_registration", f"AI-{count}")
            self._registry[reg] = {
                "instance": instance,
                "obj": obj,
                "latitude": a["latitude"],
                "longitude": a["longitude"],
                "true_hdg": a["true_hdg"],
                "aircraft_type": a["aircraft_type"],
                "callsign": a.get("callsign", reg),
            }

            count += 1

        xp.log(f"AIrport: Spawned {count} aircraft")
        return count

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
