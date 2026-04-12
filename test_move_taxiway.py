"""
Prueba de movimiento por calles de rodaje (taxiways).

Uso:
  uv run python test_move_taxiway.py [CALLSIGN] [DESTINO] [VIA] [SPEED_KTS]

Ejemplos:
  uv run python test_move_taxiway.py                        # auto: primer avion, destino 17, via T
  uv run python test_move_taxiway.py EC-IYV 17 T 5
  uv run python test_move_taxiway.py EC-IYV 35 Y 8
"""

import json
import sys
import time

import redis

sys.path.insert(0, 'plugins/GND')
from shared.services.airport_data_store import AirportDataStore
from shared.services.taxi_router import compute_taxi_route
from graph import AirportGraph


def list_known_aircraft(r: redis.Redis) -> list[str]:
    keys = r.keys("aircraft:state:*")
    return [k.split(":")[2] for k in keys if k.split(":")[2] != "USER"]


def main():
    args = sys.argv[1:]

    r = redis.Redis(host="localhost", port=6379, decode_responses=True)

    known = list_known_aircraft(r)
    if not known:
        print("ERROR: No hay aviones en Redis. Inicia una sesion en X-Plane primero.")
        sys.exit(1)

    print(f"Aviones en sesion: {known}")

    # Parametros
    callsign  = args[0] if len(args) > 0 else known[0]
    dest      = args[1] if len(args) > 1 else "17"
    via_str   = args[2] if len(args) > 2 else "T"
    speed_kts = float(args[3]) if len(args) > 3 else 5.0
    via       = [v.strip() for v in via_str.split(",")]

    # Posicion actual del avion
    state = r.hgetall(f"aircraft:state:{callsign}")
    if not state:
        print(f"ERROR: No se encontro estado para {callsign}")
        sys.exit(1)

    lat = float(state["latitude"])
    lon = float(state["longitude"])
    print(f"\n{callsign}  lat={lat:.6f}  lon={lon:.6f}  phase={state.get('phase','?')}")

    # Calcular ruta
    print(f"\nCalculando ruta: {callsign} -> {dest}  via {via}...")
    store = AirportDataStore()
    data = store.load()
    g = AirportGraph(data=data)
    result = g.find_route_from_position(start_lat=lat, start_lon=lon, end_token=dest, via=via)

    if not result.get("success"):
        print(f"ERROR en ruta: {result.get('error')}")
        sys.exit(1)

    waypoints = result["waypoints"]
    print(f"Ruta calculada:")
    print(f"  Calles: {result['taxiway_sequence']}")
    print(f"  Distancia: {result['total_distance_m']:.0f} m")
    print(f"  Waypoints: {len(waypoints)}")
    for i, wp in enumerate(waypoints):
        print(f"    {i}: lat={wp['lat']:.6f}  lon={wp['lon']:.6f}")

    # Estimar duracion total
    dist_m = result["total_distance_m"]
    speed_mps = speed_kts * 0.514444
    est_s = dist_m / speed_mps
    print(f"\nVelocidad: {speed_kts} kt  |  Duracion estimada: {est_s:.0f} s")

    # Enviar comando de waypoints a Redis
    cmd = {
        "mode":       "waypoints",
        "waypoints":  waypoints,
        "speed_kts":  speed_kts,
        "started_at": time.time(),
    }
    r.set(f"aircraft:{callsign}:move_cmd", json.dumps(cmd), ex=int(est_s) + 30)
    print(f"\nComando enviado. Observa {callsign} en X-Plane rodar por {via_str}.\n")

    # Monitorizar posicion
    end = time.time() + est_s + 5
    while time.time() < end:
        s = r.hgetall(f"aircraft:state:{callsign}")
        clat = s.get("latitude", "?")
        clon = s.get("longitude", "?")
        spd  = s.get("ground_speed", "?")
        phase = s.get("phase", "?")
        remaining = max(0.0, end - time.time() - 5)
        print(f"  [{remaining:5.0f}s]  lat={clat}  lon={clon}  spd={spd}kt  phase={phase}")
        time.sleep(2)

    s = r.hgetall(f"aircraft:state:{callsign}")
    print(f"\nPosicion final:  lat={s.get('latitude')}  lon={s.get('longitude')}  phase={s.get('phase')}")
    print("Prueba completada.")


if __name__ == "__main__":
    main()
