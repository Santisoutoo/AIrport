"""Defaults for the taxi router. Override via env vars when needed."""

import os


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


DELAY_MIN_S: float = _float("TAXI_ROUTER_DELAY_MIN_S", 4.0)
DELAY_MAX_S: float = _float("TAXI_ROUTER_DELAY_MAX_S", 20.0)

PUSHBACK_SPEED_KTS: float = _float("TAXI_ROUTER_PUSHBACK_SPEED_KTS", 2.0)
TAXI_SPEED_KTS: float = _float("TAXI_ROUTER_TAXI_SPEED_KTS", 8.0)

PUSHBACK_MIN_DIST_M: float = _float("TAXI_ROUTER_PUSHBACK_MIN_DIST_M", 15.0)
PUSHBACK_MAX_DIST_M: float = _float("TAXI_ROUTER_PUSHBACK_MAX_DIST_M", 40.0)

MOVE_CMD_KEY = "aircraft:{registration}:move_cmd"
MOVE_EVENTS_CHANNEL = "aircraft:{registration}:move_events"
HMI_CHAT_CHANNEL = "hmi:chat"
LAST_ERROR_KEY = "aircraft:{registration}:last_error"
LAST_ERROR_TTL_S = 300
