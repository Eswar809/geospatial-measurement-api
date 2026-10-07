"""Response schemas for the measurements endpoint."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MeasurementInfo(BaseModel):
    """Per-feature measurement values."""

    status: str = Field(examples=["MEASURED"])
    area_m2: float | None = None
    perimeter_m: float | None = None
    length_m: float | None = None
    measurement_crs: str | None = Field(default=None, examples=["EPSG:32643"])
    warnings: list[str] = Field(default_factory=list)


class FeatureMeasurement(BaseModel):
    """One feature with its source geometry and measurement."""

    index: int
    layer: str = Field(examples=["Parcels"])
    geometry_type: str = Field(examples=["Polygon"])
    crs: str = Field(examples=["EPSG:4326"])
    properties: dict = Field(default_factory=dict, examples=[{"Name": "Plot 1"}])
    geometry: dict | None = None
    measurement: MeasurementInfo


class Summary(BaseModel):
    """Whole-file aggregates computed with SQL over all features."""

    by_geometry_type: dict[str, int] = Field(default_factory=dict)
    by_measurement_status: dict[str, int] = Field(default_factory=dict)
    total_area_m2: float | None = None
    total_length_m: float | None = None


class Pagination(BaseModel):
    """Page cursor for the measurements list."""

    limit: int
    offset: int
    total: int


class MeasurementsResponse(BaseModel):
    """Paginated measurements with whole-file summary."""

    file_id: str
    summary: Summary
    pagination: Pagination
    features: list[FeatureMeasurement]
