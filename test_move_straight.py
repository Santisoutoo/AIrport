"""
Smoke test: mueve un avion en linea recta via Redis.

Requisitos:
  - X-Plane 12 corriendo con el plugin PI_AIrport cargado
  - Una sesion activa (iniciada desde el HMI o manualmente)
  - Redis accesible en localhost:6379

Uso:
  uv run python test_move_straight.py [CALLSIGN] [HEADING] [SPEED_KTS] [DURATION_S]

Ejemplos:
  uv run python test_move_straight.py              # usa valores por defecto
  uv run python test_move_straight.py IBE001 90 5 20
"""

import json
import sys
import time

import redis


def list_known_aircraft(r: redis.Redis) -> list[str]:
    keys = r.keys("aircraft:state:*")
    return [k.split(":")[2] for k in keys if k.split(":")[2] != "USER"]


def main():
    args = sys.argv[1:]

    r = redis.Redis(host="localhost", port=6379, decode_responses=True)

    # Detectar aviones conocidos
    known = list_known_aircraft(r)
    if not known:
        print("ERROR: No se encontraron aviones en Redis.")
        print("       Asegurate de que X-Plane esta corriendo y la sesion esta activa.")
        sys.exit(1)

    print(f"Aviones detectados en Redis: {known}")

    # Parametros
    callsign   = args[0] if len(args) > 0 else known[0]
    heading    = float(args[1]) if len(args) > 1 else 90.0
    speed_kts  = float(args[2]) if len(args) > 2 else 5.0
    duration_s = float(args[3]) if len(args) > 3 else 20.0

    print(f"\nMoviendo: {callsign}")
    print(f"  Rumbo:     {heading}°  (0=Norte, 90=Este, 180=Sur, 270=Oeste)")
    print(f"  Velocidad: {speed_kts} kt")
    print(f"  Duracion:  {duration_s} s")
    distancia_m = speed_kts * 0.514444 * duration_s
    print(f"  Distancia: ~{distancia_m:.0f} metros")

    # Leer posicion actual
    state = r.hgetall(f"aircraft:state:{callsign}")
    if state:
        print(f"\nPosicion inicial:")
        print(f"  lat={state.get('latitude', '?')}  lon={state.get('longitude', '?')}")

    # Enviar comando
    cmd = {
        "heading":    heading,
        "speed_kts":  speed_kts,
        "duration_s": duration_s,
        "started_at": time.time(),
    }
    r.set(f"aircraft:{callsign}:move_cmd", json.dumps(cmd), ex=int(duration_s) + 15)
    print(f"\nComando enviado a Redis: aircraft:{callsign}:move_cmd")
    print("Observa el avion en X-Plane. Actualizando posicion cada 2s...\n")

    # Monitorizar posicion durante el movimiento
    end = time.time() + duration_s + 2
    while time.time() < end:
        s = r.hgetall(f"aircraft:state:{callsign}")
        lat = s.get("latitude", "?")
        lon = s.get("longitude", "?")
        spd = s.get("ground_speed", "?")
        phase = s.get("phase", "?")
        remaining = max(0.0, end - time.time() - 2)
        print(f"  [{remaining:5.1f}s restantes]  lat={lat}  lon={lon}  spd={spd}kt  phase={phase}")
        time.sleep(2)

    # Estado final
    state = r.hgetall(f"aircraft:state:{callsign}")
    print(f"\nPosicion final:")
    print(f"  lat={state.get('latitude', '?')}  lon={state.get('longitude', '?')}")
    print(f"  phase={state.get('phase', '?')}")
    print("\nPrueba completada.")


if __name__ == "__main__":
    main()
