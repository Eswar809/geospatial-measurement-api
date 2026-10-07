"""Database engine and session factory."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base


def create_session_factory(database_url: str) -> sessionmaker:
    """Build an engine and return a session factory bound to it.

    Args:
        database_url: SQLAlchemy URL. SQLite gets ``check_same_thread=False``
            because FastAPI serves requests from a threadpool.
    """
    connect_args = {"check_same_thread": False} if "sqlite" in database_url else {}
    engine = create_engine(database_url, connect_args=connect_args)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
