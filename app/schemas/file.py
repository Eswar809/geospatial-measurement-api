"""Response schemas for file endpoints."""

from __future__ import annotations

import datetime

from pydantic import BaseModel, Field


class FileInfo(BaseModel):
    """File metadata returned by upload and file-info endpoints."""

    id: str = Field(examples=["5f0c1c9e8a7b4d3c9b2e6a1d4f7c8b90"])
    filename: str = Field(examples=["survey.kml"])
    file_type: str = Field(examples=["KML"])
    status: str = Field(examples=["COMPLETED"])
    feature_count: int | None = Field(default=None, examples=[120])
    crs: str | None = Field(default=None, examples=["EPSG:4326"])
    crs_assumed: bool = False
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime.datetime

    model_config = {"from_attributes": True}
