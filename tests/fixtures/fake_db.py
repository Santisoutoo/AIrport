"""SQLite in-memory fixtures replacing PostgreSQL for repository/runner tests.

The orchestrator service uses PostgreSQL in production. For unit tests we
spin up a fresh SQLite ``:memory:`` engine per test, build the schema from
the real ``Base.metadata`` (the JSONB column is patched to JSON in the root
conftest), and yield a ``Session`` bound to that engine.
"""

from __future__ import annotations

from typing import Callable

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def db_engine():
    """Per-test SQLite engine.

    ``StaticPool`` + ``check_same_thread=False`` is required so the
    ``:memory:`` database survives across the multiple connections opened by
    FastAPI dependency injection during a single TestClient request.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine) -> Session:
    """Yield a SQLAlchemy session with the AircraftClearance table created."""
    # Imported lazily so the JSONB patch in tests/conftest.py is already in
    # effect (must run before ``db.models`` is imported the first time).
    from db import models  # noqa: F401 - registers the table on Base.metadata
    from db.connection import Base

    Base.metadata.create_all(bind=db_engine)
    SessionLocal = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def clearance_repo(db_session):
    """Wired ClearanceRepository over the per-test session."""
    from db.repository import ClearanceRepository

    return ClearanceRepository(db_session)


@pytest.fixture
def clearance_factory(clearance_repo) -> Callable:
    """Callable factory that creates AircraftClearance rows with sane defaults."""

    def _make(
        registration: str = "EC-MIG",
        session_id: str = "test-session",
        squawk: int = 2000,
        initial_altitude: int = 6000,
        instrumental_departure: str = "VAR1A",
        runway_in_use: str = "17",
        altimeter: float = 1013.0,
        destination_icao: str = "LEPA",
        clearance_text: str = "Cleared to LEPA via VAR1A, FL060, squawk 2000.",
        dependency: str = "DEL",
    ):
        return clearance_repo.upsert(
            registration=registration,
            session_id=session_id,
            squawk=squawk,
            initial_altitude=initial_altitude,
            instrumental_departure=instrumental_departure,
            runway_in_use=runway_in_use,
            altimeter=altimeter,
            destination_icao=destination_icao,
            clearance_text=clearance_text,
            dependency=dependency,
        )

    return _make
