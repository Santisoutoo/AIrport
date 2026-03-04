import os

import redis as redis_lib
from fastapi import APIRouter

from api.auth import get_db, hash_password, verify_password
from api.models import AuthRequest, StartSessionRequest
from api.routes import current_airport

router = APIRouter(prefix="/api/v1/plugin", tags=["plugin"])

_r = redis_lib.from_url(os.getenv("REDIS_URL", "redis://redis:6379"))


# ---- Auth

@router.post("/login")
def login(req: AuthRequest):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT password_hash FROM users WHERE username = %s", (req.username,))
        row = cur.fetchone()
        cur.close()
        conn.close()
    except Exception as e:
        return {"success": False, "message": f"Database error: {e}"}

    if not row:
        return {"success": False, "message": "Invalid username or password"}

    if verify_password(req.password, row[0]):
        return {"success": True, "username": req.username}
    return {"success": False, "message": "Invalid username or password"}


@router.post("/register")
def register(req: AuthRequest):
    if len(req.password) < 6:
        return {"success": False, "message": "Password must be at least 6 characters"}
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM users WHERE username = %s", (req.username,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return {"success": False, "message": "Username already exists"}
        cur.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
            (req.username, hash_password(req.password)),
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "message": "Account created successfully"}
    except Exception as e:
        return {"success": False, "message": f"Database error: {e}"}


# ---- Session

@router.post("/session/start")
def start_session(req: StartSessionRequest):
    if not 1 <= req.aircraft_count <= 50:
        return {"success": False, "message": "Aircraft count must be between 1 and 50"}

    icao = current_airport.get("icao", "")
    if not icao:
        return {"success": False, "message": "Airport not detected yet. Wait for X-Plane to connect."}

    _r.hset("airport:session_request", mapping={
        "type": req.session_type,
        "weather": req.weather,
        "aircraft_count": str(req.aircraft_count),
        "complexity": req.complexity,
        "icao": icao,
        "status": "pending",
        "session_id": "",
    })
    return {"success": True}


@router.post("/session/stop")
def stop_session():
    _r.hset("airport:session_request", "status", "stop_pending")
    return {"success": True}


@router.get("/session/status")
def session_status():
    try:
        data = _r.hgetall("airport:session_request")
        if not data:
            return {"status": "idle", "session_id": None, "icao": current_airport.get("icao")}
        return {
            "status": data.get(b"status", b"idle").decode(),
            "session_id": data.get(b"session_id", b"").decode() or None,
            "icao": current_airport.get("icao"),
        }
    except Exception:
        return {"status": "idle", "session_id": None, "icao": current_airport.get("icao")}
