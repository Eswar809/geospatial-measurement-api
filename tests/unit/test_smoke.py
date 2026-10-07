"""Slow smoke test: 5,000 features process in a few seconds."""
import io
import uuid
import zipfile

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from app.config import Settings
from app.db.session import create_session_factory
from app.services.ingestion import IngestionService

pytestmark = pytest.mark.slow


def _big_zip(path, n=5000):
    work = path.parent / "_big_parts"
    work.mkdir(exist_ok=True)
    try:
        polys = [
            Polygon(
                [
                    (72.0 + (i % 100) * 0.001, 19.0 + (i // 100) * 0.001),
                    (72.0 + (i % 100) * 0.001 + 0.0005, 19.0 + (i // 100) * 0.001),
                    (
                        72.0 + (i % 100) * 0.001 + 0.0005,
                        19.0 + (i // 100) * 0.001 + 0.0005,
                    ),
                    (72.0 + (i % 100) * 0.001, 19.0 + (i // 100) * 0.001 + 0.0005),
                ]
            )
            for i in range(n)
        ]
        gdf = gpd.GeoDataFrame({"i": range(n)}, geometry=polys, crs="EPSG:4326")
        gdf.to_file(work / "big.shp")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for part in sorted(work.glob("big.*")):
                zf.write(part, part.name)
    finally:
        for leftover in work.iterdir():
            leftover.unlink()
        work.rmdir()
    return path


def test_5000_features_fast(tmp_path):
    import time

    settings = Settings(
        DATABASE_URL="sqlite:///:memory:",
        UPLOAD_DIR=str(tmp_path / "uploads"),
    )
    db = create_session_factory(settings.DATABASE_URL)()
    svc = IngestionService(db, settings)
    zip_path = _big_zip(tmp_path / "big.zip")
    started = time.monotonic()
    record = svc.process_upload(
        uuid.uuid4().hex, "big.zip", io.BytesIO(zip_path.read_bytes())
    )
    duration = time.monotonic() - started
    assert record.status == "COMPLETED"
    assert record.feature_count == 5000
    assert duration < 60, f"took {duration:.1f}s"
    db.close()
