import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def _build_db_url() -> str:
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "airport")
    user = os.getenv("POSTGRES_USER", "airport_user")
    password = os.getenv("POSTGRES_PASSWORD", "password")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


engine = create_engine(_build_db_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    # Imported for its side effect: registers AircraftClearance on
    # Base.metadata so create_all() below actually creates the table.
    from db.models import AircraftClearance  # noqa: F401

    Base.metadata.create_all(bind=engine)
