"""Service tests: ingestion pipeline on in-memory SQLite."""

import io
import uuid
from pathlib import Path

import pytest

from app.config import Settings
from app.core.errors import (
    EmptyFileError,
    FileTooLargeError,
    InvalidGeoDataError,
    UnsupportedFileTypeError,
)
from app.db.models import FeatureRecord, FileRecord
from app.db.session import create_session_factory
from app.services import ingestion as ingestion_mod
from app.services.ingestion import IngestionService

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


@pytest.fixture
def settings(tmp_path):
    return Settings(
        DATABASE_URL="sqlite:///:memory:",
        UPLOAD_DIR=str(tmp_path / "uploads"),
        MAX_UPLOAD_MB=50,
        MAX_UNCOMPRESSED_MB=250,
        MAX_ZIP_ENTRIES=50,
        MAX_FEATURES=100000,
        LOG_LEVEL="INFO",
    )


@pytest.fixture
def db(settings):
    session = create_session_factory(settings.DATABASE_URL)()
    yield session
    session.close()


@pytest.fixture
def svc(db, settings):
    return IngestionService(db, settings)


def _fid():
    return uuid.uuid4().hex


class TestKmlHappyPath:
    def test_completed(self, svc, db):
        data = (SAMPLES / "survey.kml").read_bytes()
        record = svc.process_upload(_fid(), "survey.kml", io.BytesIO(data))
        assert record.status == "COMPLETED"
        assert record.feature_count == 5
        assert record.crs == "EPSG:4326"
        assert record.crs_assumed is False

        rows = (
            db.query(FeatureRecord)
            .filter_by(file_id=record.id)
            .order_by(FeatureRecord.feature_index)
            .all()
        )
        assert [r.feature_index for r in rows] == [0, 1, 2, 3, 4]
        by_status = {}
        for r in rows:
            by_status.setdefault(r.measurement_status, []).append(r)
        assert len(by_status["MEASURED"]) == 2  # polygon + line
        assert len(by_status["NOT_APPLICABLE"]) == 1  # point
        assert len(by_status["UNSUPPORTED"]) == 2  # collection + null geometry
        polygon = next(r for r in rows if r.geometry_type == "Polygon")
        assert polygon.area_m2 and polygon.area_m2 > 0
        assert polygon.measurement_crs == "EPSG:32643"


class TestShapefileHappyPath:
    def test_completed(self, svc, db):
        data = (SAMPLES / "parcels_epsg32643.zip").read_bytes()
        record = svc.process_upload(_fid(), "parcels.zip", io.BytesIO(data))
        assert record.status == "COMPLETED"
        assert record.feature_count == 2
        assert record.crs == "EPSG:32643"
        rows = db.query(FeatureRecord).filter_by(file_id=record.id).all()
        assert all(r.measurement_status == "MEASURED" for r in rows)
        assert all(r.measurement_crs == "EPSG:32643" for r in rows)


class TestValidationErrors:
    def test_unsupported_extension_persists_nothing(self, svc, db):
        with pytest.raises(UnsupportedFileTypeError):
            svc.process_upload(_fid(), "data.txt", io.BytesIO(b"hello"))
        assert db.query(FileRecord).count() == 0

    def test_empty_file_persists_nothing(self, svc, db):
        with pytest.raises(EmptyFileError):
            svc.process_upload(_fid(), "empty.kml", io.BytesIO(b""))
        assert db.query(FileRecord).count() == 0

    def test_too_large_persists_nothing(self, svc, db, settings):
        settings.MAX_UPLOAD_MB = 0
        with pytest.raises(FileTooLargeError):
            svc.process_upload(
                _fid(), "survey.kml", io.BytesIO((SAMPLES / "survey.kml").read_bytes())
            )
        assert db.query(FileRecord).count() == 0


class TestFailedRecords:
    def test_corrupt_zip_marks_failed_with_rollback(self, svc, db):
        fid = _fid()
        with pytest.raises(InvalidGeoDataError) as excinfo:
            svc.process_upload(fid, "bad.zip", io.BytesIO(b"not a zip at all"))
        assert excinfo.value.details["file_id"] == fid
        record = db.query(FileRecord).filter_by(id=fid).one()
        assert record.status == "FAILED"
        assert record.error_code == "INVALID_GEODATA"
        assert record.error_message
        assert (
            "tmp" not in record.error_message and "uploads" not in record.error_message
        )
        assert db.query(FeatureRecord).filter_by(file_id=fid).count() == 0

    def test_too_many_features_marks_failed(self, svc, db, settings):
        settings.MAX_FEATURES = 1
        fid = _fid()
        with pytest.raises(InvalidGeoDataError, match="too many features"):
            svc.process_upload(
                fid, "survey.kml", io.BytesIO((SAMPLES / "survey.kml").read_bytes())
            )
        record = db.query(FileRecord).filter_by(id=fid).one()
        assert record.status == "FAILED"
        assert db.query(FeatureRecord).filter_by(file_id=fid).count() == 0


class TestPartialFeatureErrors:
    def test_one_bad_feature_does_not_fail_file(self, svc, db, monkeypatch):
        real = ingestion_mod.measure_geometry
        calls = 0

        def flaky(geom, src_crs, cache):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("boom")
            return real(geom, src_crs, cache)

        monkeypatch.setattr(ingestion_mod, "measure_geometry", flaky)
        data = (SAMPLES / "parcels_epsg32643.zip").read_bytes()
        record = svc.process_upload(_fid(), "parcels.zip", io.BytesIO(data))
        assert record.status == "COMPLETED"
        rows = (
            db.query(FeatureRecord)
            .filter_by(file_id=record.id)
            .order_by(FeatureRecord.feature_index)
            .all()
        )
        assert [r.measurement_status for r in rows] == ["MEASURED", "ERROR"]
        assert rows[1].error_message == "boom"
