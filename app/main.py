"""FastAPI application factory with the shared error envelope."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import files
from app.config import get_settings
from app.core.errors import AppError
from app.db.session import create_session_factory

logger = logging.getLogger(__name__)


def _envelope(code: str, message: str, details: dict | None = None) -> dict:
    """Build the single error envelope used by every failure."""
    return {"error": {"code": code, "message": message, "details": details or {}}}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables and shared objects once at startup."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    app.state.settings = settings
    app.state.session_factory = create_session_factory(settings.DATABASE_URL)
    yield


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    app = FastAPI(
        title="Geospatial Measurement API",
        description=(
            "Upload zipped Shapefiles or KML files; get area/length "
            "measurements in projected CRS over REST."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=_envelope(
                "INVALID_GEODATA",
                "request validation failed",
                {"errors": jsonable_encoder(exc.errors())},
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        logger.exception("unhandled error")
        return JSONResponse(
            status_code=500,
            content=_envelope("INTERNAL_ERROR", "internal server error"),
        )

    @app.get("/health", summary="Liveness probe", tags=["ops"])
    def health():
        """Liveness probe."""
        return {"status": "ok"}

    app.include_router(files.router)
    return app


app = create_app()
