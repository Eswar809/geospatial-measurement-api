"""IngestionService: orchestrates upload to measured, persisted features.

Pipeline: validate extension, stream to disk, insert a PROCESSING record,
sniff content, read the dataset, cap the feature count, measure each
feature independently, bulk-insert, and mark COMPLETED — all explicitly
in the same transaction. Any failure rolls features back and marks the
record FAILED with a safe message (no filesystem paths).
"""

from __future__ import annotations

import datetime
import logging
import tempfile
import time
from pathlib import Path
from typing import BinaryIO

import pyproj
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.errors import (
    AppError,
    InvalidGeoDataError,
    UnsupportedFileTypeError,
)
from app.db.models import FeatureRecord, FileRecord
from app.services.archive import safe_extract
from app.services.geo.crs import TransformerCache
from app.services.geo.measure import Measurement, measure_geometry
from app.services.geo.serialize import geometry_to_geojson, json_safe
from app.services.readers.base import RawDataset
from app.services.readers.kml import read_kml
from app.services.readers.shapefile import read_shapefile
from app.services.storage import save_upload

logger = logging.getLogger(__name__)

_ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
_MB = 1024 * 1024


class IngestionService:
    """Runs the whole file pipeline against one DB session."""

    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def process_upload(
        self, file_id: str, filename: str, file_obj: BinaryIO
    ) -> FileRecord:
        """Process one upload from bytes to a COMPLETED or FAILED record.

        Args:
            file_id: Pre-generated uuid4 hex id for the file.
            filename: Client filename (basename kept as metadata only).
            file_obj: Binary file-like object with the upload bytes.

        Returns:
            The COMPLETED FileRecord.

        Raises:
            AppError: On any failure. The FAILED record already exists and
                ``error.details["file_id"]`` points to it. Extension, empty,
                and too-large errors raise before any record is created.
        """
        started = time.monotonic()
        safe_name = Path(filename).name
        ext = Path(safe_name).suffix.lower()
        if ext not in (".zip", ".kml"):
            raise UnsupportedFileTypeError(
                f"unsupported file type {Path(filename).suffix or '(none)'}; "
                "upload a .zip shapefile or .kml file"
            )
        file_type = "SHAPEFILE" if ext == ".zip" else "KML"
        stored, size = save_upload(
            file_obj,
            file_id=file_id,
            ext=ext,
            upload_dir=Path(self.settings.UPLOAD_DIR),
            max_bytes=self.settings.MAX_UPLOAD_MB * _MB,
        )
        record = FileRecord(
            id=file_id,
            filename=safe_name,
            file_type=file_type,
            size_bytes=size,
            status="PROCESSING",
            warnings=[],
        )
        self.db.add(record)
        self.db.commit()
        try:
            self._check_magic(stored, ext)
            dataset = self._read_dataset(stored, ext)
            if len(dataset.features) > self.settings.MAX_FEATURES:
                raise InvalidGeoDataError(
                    f"too many features ({len(dataset.features)} "
                    f"> {self.settings.MAX_FEATURES})"
                )
            self._persist_completed(record, dataset)
        except AppError as e:
            e.details.setdefault("file_id", file_id)
            self._mark_failed(record, e.code, e.message)
            raise
        except Exception:
            logger.exception("unexpected ingestion failure", extra={"file_id": file_id})
            err = AppError("internal processing error")
            err.details["file_id"] = file_id
            self._mark_failed(record, err.code, err.message)
            raise err from None
        duration = time.monotonic() - started
        logger.info(
            "ingested file",
            extra={
                "file_id": file_id,
                "features": record.feature_count,
                "duration_s": round(duration, 2),
            },
        )
        return record

    def _check_magic(self, stored: Path, ext: str) -> None:
        """Sniff stored bytes; never trust the Content-Type or extension."""
        with stored.open("rb") as f:
            head = f.read(32)
        if ext == ".zip":
            if not head.startswith(_ZIP_MAGIC):
                raise InvalidGeoDataError(
                    "file content does not look like a zip archive"
                )
        else:
            text = head.lstrip(b"\xef\xbb\xbf \t\r\n")
            if not text.startswith(b"<"):
                raise InvalidGeoDataError("file content does not look like KML/XML")

    def _read_dataset(self, stored: Path, ext: str) -> RawDataset:
        """Read the stored file into a RawDataset."""
        if ext == ".kml":
            return read_kml(stored)
        with tempfile.TemporaryDirectory(prefix="shp_") as tmp:
            safe_extract(
                stored,
                Path(tmp),
                max_entries=self.settings.MAX_ZIP_ENTRIES,
                max_bytes=self.settings.MAX_UNCOMPRESSED_MB * _MB,
            )
            return read_shapefile(Path(tmp))

    def _persist_completed(self, record: FileRecord, dataset: RawDataset) -> None:
        """Measure every feature and commit features plus COMPLETED status."""
        cache = TransformerCache(dataset.crs)
        crs_label = _crs_label(dataset.crs)
        mappings = []
        for index, feat in enumerate(dataset.features):
            measurement = self._safe_measure(feat.geometry, dataset.crs, cache)
            mappings.append(
                {
                    "file_id": record.id,
                    "feature_index": index,
                    "layer": feat.layer,
                    "geometry_type": (
                        feat.geometry.geom_type
                        if feat.geometry is not None
                        else "Unknown"
                    ),
                    "geometry": (
                        geometry_to_geojson(feat.geometry)
                        if feat.geometry is not None
                        else None
                    ),
                    "crs": crs_label,
                    "properties": json_safe(feat.properties),
                    "measurement_status": measurement.status,
                    "area_m2": measurement.area_m2,
                    "perimeter_m": measurement.perimeter_m,
                    "length_m": measurement.length_m,
                    "measurement_crs": measurement.measurement_crs,
                    "warnings": measurement.warnings,
                    "error_message": measurement.error_message,
                }
            )
        for offset in range(0, len(mappings), 1000):
            self.db.bulk_insert_mappings(
                FeatureRecord, mappings[offset : offset + 1000]
            )
        record.status = "COMPLETED"
        record.feature_count = len(mappings)
        record.crs = crs_label
        record.crs_wkt = dataset.crs.to_wkt()
        record.crs_assumed = dataset.crs_assumed
        record.warnings = list(dataset.warnings)
        record.completed_at = datetime.datetime.now(datetime.UTC)
        self.db.commit()

    @staticmethod
    def _safe_measure(
        geom, src_crs: pyproj.CRS, cache: TransformerCache
    ) -> Measurement:
        """Measure one feature; an exception becomes ERROR, never a file failure."""
        try:
            return measure_geometry(geom, src_crs, cache)
        except Exception as e:  # noqa: BLE001 - any per-feature failure is ERROR by design
            logger.warning("per-feature measurement failed: %s", e)
            return Measurement(status="ERROR", error_message=str(e)[:500])

    def _mark_failed(self, record: FileRecord, code: str, message: str) -> None:
        """Roll back features and persist the FAILED status."""
        self.db.rollback()
        fresh = self.db.get(FileRecord, record.id)
        fresh.status = "FAILED"
        fresh.error_code = code
        fresh.error_message = message
        fresh.completed_at = datetime.datetime.now(datetime.UTC)
        self.db.commit()


def _crs_label(crs: pyproj.CRS) -> str:
    """Report a CRS as EPSG:xxxx, falling back to its name."""
    epsg = crs.to_epsg()
    return f"EPSG:{epsg}" if epsg else (crs.name or "unknown")
