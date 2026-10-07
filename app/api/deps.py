"""Shared FastAPI dependencies: settings, session factory, DB session."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from app.config import Settings


def get_settings(request: Request) -> Settings:
    """Return the app-level settings (overridable in tests)."""
    return request.app.state.settings


def get_session_factory(request: Request):
    """Return the app-level SQLAlchemy session factory."""
    return request.app.state.session_factory


def get_db(request: Request) -> Iterator[Session]:
    """Yield a request-scoped DB session."""
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()
