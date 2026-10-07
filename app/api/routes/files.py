"""File endpoints: upload, file info, measurements.

Handlers stay thin: validate input, call the ingestion service, map ORM
rows to response schemas.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_settings
from app.config import Settings
from app.core.errors import NotFoundError, NotReadyError
from app.db.models import FeatureRecord, FileRecord
from app.schemas.file import FileInfo
from app.schemas.measurement import (
    FeatureMeasurement,
    MeasurementInfo,
    MeasurementsResponse,
    Pagination,
    Summary,
)
from app.services.ingestion import IngestionService

router = APIRouter()


def _to_file_info(record: FileRecord) -> FileInfo:
    return FileInfo(
        id=record.id,
        filename=record.filename,
        file_type=record.file_type,
        status=record.status,
        feature_count=record.feature_count,
        crs=record.crs,
        crs_assumed=record.crs_assumed,
        warnings=record.warnings or [],
        created_at=record.created_at,
    )


@router.post(
    "/api/files/",
    response_model=FileInfo,
    status_code=201,
    summary="Upload a zipped Shapefile or KML file",
    responses={
        201: {"description": "File accepted and processed"},
        400: {"description": "Empty file"},
        413: {"description": "File too large"},
        415: {"description": "Unsupported file type"},
        422: {"description": "Unreadable content"},
    },
)
def upload_file(
    response: Response,
    file: UploadFile,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Accept one ``.zip`` or ``.kml`` upload, process it, return file info."""
    file_id = uuid.uuid4().hex
    service = IngestionService(db, settings)
    record = service.process_upload(file_id, file.filename or "", file.file)
    response.headers["Location"] = f"/api/files/{record.id}/"
    return _to_file_info(record)


@router.get(
    "/api/files/{file_id}/",
    response_model=FileInfo,
    summary="Get file info",
    responses={404: {"description": "Unknown file id"}},
)
def get_file(file_id: str, db: Session = Depends(get_db)):
    """Return metadata for one uploaded file."""
    record = db.get(FileRecord, file_id)
    if record is None:
        raise NotFoundError(f"file {file_id} not found")
    return _to_file_info(record)


@router.get(
    "/api/files/{file_id}/measurements/",
    response_model=MeasurementsResponse,
    summary="Get paginated measurements for a file",
    responses={
        404: {"description": "Unknown file id"},
        409: {"description": "File processing did not complete"},
    },
)
def get_measurements(
    file_id: str,
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    include_geometry: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    """Return measured features with whole-file summary aggregates."""
    record = db.get(FileRecord, file_id)
    if record is None:
        raise NotFoundError(f"file {file_id} not found")
    if record.status != "COMPLETED":
        raise NotReadyError(f"file {file_id} status is {record.status}")

    total = (
        db.query(func.count(FeatureRecord.id))
        .filter(FeatureRecord.file_id == file_id)
        .scalar()
    )
    rows = (
        db.query(FeatureRecord)
        .filter(FeatureRecord.file_id == file_id)
        .order_by(FeatureRecord.feature_index)
        .offset(offset)
        .limit(limit)
        .all()
    )
    features = [
        FeatureMeasurement(
            index=row.feature_index,
            layer=row.layer,
            geometry_type=row.geometry_type,
            crs=row.crs,
            properties=row.properties or {},
            geometry=row.geometry if include_geometry else None,
            measurement=MeasurementInfo(
                status=row.measurement_status,
                area_m2=row.area_m2,
                perimeter_m=row.perimeter_m,
                length_m=row.length_m,
                measurement_crs=row.measurement_crs,
                warnings=row.warnings or [],
            ),
        )
        for row in rows
    ]
    return MeasurementsResponse(
        file_id=file_id,
        summary=_build_summary(db, file_id),
        pagination=Pagination(limit=limit, offset=offset, total=total),
        features=features,
    )


def _build_summary(db: Session, file_id: str) -> Summary:
    """Aggregate counts and totals over the whole file with SQL."""
    base = db.query(FeatureRecord).filter(FeatureRecord.file_id == file_id)
    by_type = {
        geometry_type: count
        for geometry_type, count in base.with_entities(
            FeatureRecord.geometry_type, func.count()
        )
        .group_by(FeatureRecord.geometry_type)
        .all()
    }
    by_status = {
        status: count
        for status, count in base.with_entities(
            FeatureRecord.measurement_status, func.count()
        )
        .group_by(FeatureRecord.measurement_status)
        .all()
    }
    total_area = base.with_entities(func.sum(FeatureRecord.area_m2)).scalar()
    total_length = base.with_entities(func.sum(FeatureRecord.length_m)).scalar()
    return Summary(
        by_geometry_type=by_type,
        by_measurement_status=by_status,
        total_area_m2=round(total_area, 4) if total_area is not None else None,
        total_length_m=round(total_length, 4) if total_length is not None else None,
    )
