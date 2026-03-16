from pydantic import BaseModel


class AuthRequest(BaseModel):
    username: str
    password: str


class StartSessionRequest(BaseModel):
    session_type: str
    weather: str
    aircraft_count: int
    complexity: str
