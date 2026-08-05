import os

import redis as redis_lib
from fastapi import APIRouter
from pydantic import BaseModel

from api.auth import get_db, hash_password, verify_password
from api.models import AuthRequest, StartSessionRequest
from api.routes import current_airport

router = APIRouter(prefix="/api/v1/plugin", tags=["plugin"])

_r = redis_lib.from_url(os.getenv("REDIS_URL", "redis://redis:6379"))
_ASR_REDIS_KEY = "airport:asr_config"


# ---- DB migration (runs once at startup, idempotent) ----


def _migrate():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS openai_api_key TEXT NOT NULL DEFAULT ''")
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass


_migrate()


# ---- Auth


@router.post("/login")
def login(req: AuthRequest):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT password_hash, openai_api_key FROM users WHERE username = %s",
            (req.username,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
    except Exception as e:
        return {"success": False, "message": f"Database error: {e}"}

    if not row:
        return {"success": False, "message": "Invalid username or password"}

    if verify_password(req.password, row[0]):
        api_key = row[1] or ""
        # Push api_key into ASR Redis config so the ASR service uses it immediately
        if api_key:
            _r.hset(_ASR_REDIS_KEY, "api_key", api_key)
        return {"success": True, "username": req.username, "api_key": api_key}
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

    _r.hset(
        "airport:session_request",
        mapping={
            "type": req.session_type,
            "weather": req.weather,
            "aircraft_count": str(req.aircraft_count),
            "complexity": req.complexity,
            "icao": icao,
            "status": "pending",
            "session_id": "",
        },
    )
    return {"success": True}


@router.post("/session/stop")
def stop_session():
    # Snapshot the outgoing session_id so the HMI can request a debrief
    # before the plugin clears the hash.
    try:
        sid_raw = _r.hget("airport:session_request", "session_id")
        if isinstance(sid_raw, bytes):
            sid = sid_raw.decode()
        else:
            sid = sid_raw or ""
    except Exception:
        sid = ""
    icao = current_airport.get("icao", "")
    _r.hset("airport:session_request", "status", "stop_pending")
    return {"success": True, "session_id": sid or None, "icao": icao}


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


# ---- User settings


class ApiKeyRequest(BaseModel):
    api_key: str


@router.get("/user/{username}/api-key")
def get_user_api_key(username: str):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT openai_api_key FROM users WHERE username = %s", (username,))
        row = cur.fetchone()
        cur.close()
        conn.close()
    except Exception as e:
        return {"success": False, "message": f"Database error: {e}"}
    if not row:
        return {"success": False, "message": "User not found"}
    return {"success": True, "api_key": row[0] or ""}


@router.post("/user/{username}/api-key")
def set_user_api_key(username: str, req: ApiKeyRequest):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET openai_api_key = %s WHERE username = %s",
            (req.api_key, username),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        return {"success": False, "message": f"Database error: {e}"}
    # Keep Redis in sync so the ASR service picks it up immediately
    _r.hset(_ASR_REDIS_KEY, "api_key", req.api_key)
    return {"success": True}
