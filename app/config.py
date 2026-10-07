"""Application settings via pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, overridable via environment or .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "sqlite:///./data/geospatial.db"
    UPLOAD_DIR: str = "./data/uploads"
    MAX_UPLOAD_MB: int = 50
    MAX_UNCOMPRESSED_MB: int = 250
    MAX_ZIP_ENTRIES: int = 50
    MAX_FEATURES: int = 100000
    LOG_LEVEL: str = "INFO"


def get_settings() -> Settings:
    """Return a fresh Settings instance (override point for tests)."""
    return Settings()
