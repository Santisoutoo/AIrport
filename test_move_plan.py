"""Smoke test del plan de taxi completo (delay + pushback + waypoints).

Calcula la ruta A* desde la posición actual del avión, construye un plan
v2 con pushback y waypoints y lo publica en Redis. El plugin debe
consumirlo, esperar el delay, hacer pushback y rodar por los waypoints.

Uso:
  uv run python test_move_plan.py [CALLSIGN] [DESTINO] [VIA] [DIRECTION] [DELAY]

Ejemplos:
  uv run python test_move_plan.py
  uv run python test_move_plan.py EC-IYV 17 T north 5
  uv run python test_move_plan.py EC-IYV 35 Y,H south 8
"""

import json
import sys
import threading
import time
import uuid

import redis

sys.path.insert(0, "plugins/GND")
from shared.services.airport_data_store import AirportDataStore
from shared.services.taxi_router.pushback import plan_pushback_leg
from shared.services.taxi_router.readback_parser import parse_pushback_direction
from graph import AirportGraph


def _list_aircraft(r: redis.Redis) -> list[str]:
    keys = r.keys("aircraft:state:*")
    return [k.split(":")[2] for k in keys if k.split(":")[2] != "USER"]


def _subscribe_events(r: redis.Redis, callsign: str, stop_event: threading.Event):
    pubsub = r.pubsub()
    pubsub.subscribe(f"aircraft:{callsign}:move_events")
    for msg in pubsub.listen():
        if stop_event.is_set():
            break
        if msg.get("type") != "message":
            continue
        try:
            payload = json.loads(msg["data"])
            print(f"  [event] {payload['event']}  (ts={payload['ts']:.1f})")
        except Exception:
            pass


def main():
    args = sys.argv[1:]
    r = redis.Redis(host="localhost", port=6379, decode_responses=True)

    known = _list_aircraft(r)
    if not known:
        print("ERROR: No hay aviones en Redis. Inicia una sesion en X-Plane primero.")
        sys.exit(1)

    callsign = args[0] if len(args) > 0 else known[0]
    dest = args[1] if len(args) > 1 else "17"
    via = [v.strip() for v in (args[2] if len(args) > 2 else "T").split(",")]
    direction_text = args[3] if len(args) > 3 else "face north"
    delay = float(args[4]) if len(args) > 4 else 5.0
    speed_kts = 8.0

    state = r.hgetall(f"aircraft:state:{callsign}")
    if not state:
        print(f"ERROR: no hay estado para {callsign}")
        sys.exit(1)

    lat = float(state["latitude"])
    lon = float(state["longitude"])
    hdg = float(state.get("heading", 0.0))
    print(f"\n{callsign}  lat={lat:.6f}  lon={lon:.6f}  hdg={hdg:.1f}")

    store = AirportDataStore()
    data = store.load()
    if data is None:
        print("ERROR: grafo del aeropuerto no cargado en Redis")
        sys.exit(1)

    g = AirportGraph(data=data)
    print(f"\nCalculando ruta: {callsign} -> {dest}  via {via}")
    route = g.find_route_from_position(
        start_lat=lat, start_lon=lon, end_token=dest, via=via,
    )
    if not route.get("success"):
        print(f"ERROR en ruta: {route.get('error')}")
        sys.exit(1)

    waypoints = route["waypoints"]
    if not waypoints:
        print("ERROR: ruta vacia")
        sys.exit(1)
    print(f"  calles: {route['taxiway_sequence']}")
    print(f"  distancia: {route['total_distance_m']:.0f} m  |  waypoints: {len(waypoints)}")

    direction_deg = parse_pushback_direction(direction_text)
    print(f"  pushback: {direction_text!r} -> {direction_deg}")

    pushback = plan_pushback_leg(
        stand_lat=lat, stand_lon=lon, stand_heading_deg=hdg,
        first_wp_lat=waypoints[0]["lat"], first_wp_lon=waypoints[0]["lon"],
        direction_deg=direction_deg,
    )

    plan = {
        "version": 2,
        "plan_id": str(uuid.uuid4()),
        "started_at": time.time(),
        "delay_before_start_s": delay,
        "legs": [
            pushback.to_dict(),
            {
                "mode": "waypoints",
                "waypoints": waypoints,
                "taxiway_sequence": route["taxiway_sequence"],
                "speed_kts": speed_kts,
                "stop_at_end": True,
            },
        ],
    }

    ttl = int(delay + 30 + route["total_distance_m"] / (speed_kts * 0.514444))
    r.set(f"aircraft:{callsign}:move_cmd", json.dumps(plan), ex=ttl)
    print(f"\nPlan {plan['plan_id']} publicado (ttl={ttl}s).")
    print(f"Observa {callsign} en X-Plane: espera {delay:.1f}s, pushback, taxi.\n")

    stop_event = threading.Event()
    t = threading.Thread(
        target=_subscribe_events, args=(r, callsign, stop_event), daemon=True,
    )
    t.start()

    end = time.time() + ttl + 5
    try:
        while time.time() < end:
            s = r.hgetall(f"aircraft:state:{callsign}")
            remaining = max(0.0, end - time.time() - 5)
            print(
                f"  [{remaining:5.0f}s] "
                f"lat={s.get('latitude', '?')}  lon={s.get('longitude', '?')}  "
                f"spd={s.get('ground_speed', '?')}kt  phase={s.get('phase', '?')}"
            )
            time.sleep(2)
    finally:
        stop_event.set()

    s = r.hgetall(f"aircraft:state:{callsign}")
    print(
        f"\nFinal  lat={s.get('latitude')}  lon={s.get('longitude')}  "
        f"phase={s.get('phase')}"
    )


if __name__ == "__main__":
    main()
