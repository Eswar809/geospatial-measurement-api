"""API tests: endpoints, status codes, pagination, error envelope."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db, get_settings
from app.config import Settings
from app.db.session import create_session_factory
from app.main import create_app

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


@pytest.fixture
def app_client(tmp_path):
    settings = Settings(
        DATABASE_URL=f"sqlite:///{tmp_path}/test.db",
        UPLOAD_DIR=str(tmp_path / "uploads"),
        LOG_LEVEL="WARNING",
    )
    factory = create_session_factory(settings.DATABASE_URL)
    app = create_app()

    def override_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)
    yield client, settings
    client.close()


def _upload(client, name, data):
    return client.post(
        "/api/files/",
        files={"file": (name, data, "application/octet-stream")},
    )


class TestUploadHappyPath:
    def test_kml(self, app_client):
        client, _ = app_client
        resp = _upload(client, "survey.kml", (SAMPLES / "survey.kml").read_bytes())
        assert resp.status_code == 201
        body = resp.json()
        assert resp.headers["Location"] == f"/api/files/{body['id']}/"
        assert body["filename"] == "survey.kml"
        assert body["file_type"] == "KML"
        assert body["status"] == "COMPLETED"
        assert body["feature_count"] == 5
        assert body["crs"] == "EPSG:4326"
        assert body["crs_assumed"] is False

    def test_shapefile_zip(self, app_client):
        client, _ = app_client
        data = (SAMPLES / "parcels_epsg32643.zip").read_bytes()
        resp = _upload(client, "parcels.zip", data)
        assert resp.status_code == 201
        body = resp.json()
        assert body["file_type"] == "SHAPEFILE"
        assert body["status"] == "COMPLETED"
        assert body["feature_count"] == 2
        assert body["crs"] == "EPSG:32643"


class TestUploadErrors:
    def test_unsupported_extension_415(self, app_client):
        client, _ = app_client
        resp = _upload(client, "data.txt", b"hello")
        assert resp.status_code == 415
        assert resp.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"

    def test_empty_file_400(self, app_client):
        client, _ = app_client
        resp = _upload(client, "empty.kml", b"")
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "EMPTY_FILE"

    def test_too_large_413(self, app_client):
        client, settings = app_client
        settings.MAX_UPLOAD_MB = 0
        data = (SAMPLES / "survey.kml").read_bytes()
        resp = _upload(client, "survey.kml", data)
        assert resp.status_code == 413
        assert resp.json()["error"]["code"] == "FILE_TOO_LARGE"

    def test_corrupt_zip_422_with_failed_record(self, app_client):
        client, _ = app_client
        resp = _upload(client, "bad.zip", b"not a zip at all")
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "INVALID_GEODATA"
        fid = body["error"]["details"]["file_id"]
        info = client.get(f"/api/files/{fid}/")
        assert info.status_code == 200
        assert info.json()["status"] == "FAILED"

    def test_malformed_kml_422(self, app_client):
        client, _ = app_client
        resp = _upload(client, "bad.kml", b"nope, not xml")
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "INVALID_GEODATA"

    def test_too_many_features_422(self, app_client):
        client, settings = app_client
        settings.MAX_FEATURES = 1
        data = (SAMPLES / "survey.kml").read_bytes()
        resp = _upload(client, "survey.kml", data)
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "INVALID_GEODATA"


class TestFileInfo:
    def test_get_file(self, app_client):
        client, _ = app_client
        fid = _upload(
            client, "survey.kml", (SAMPLES / "survey.kml").read_bytes()
        ).json()["id"]
        resp = client.get(f"/api/files/{fid}/")
        assert resp.status_code == 200
        assert resp.json()["id"] == fid

    def test_unknown_id_404(self, app_client):
        client, _ = app_client
        resp = client.get("/api/files/" + "0" * 32 + "/")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"]["code"] == "NOT_FOUND"
        assert body["error"]["message"]
        assert isinstance(body["error"]["details"], dict)

    def test_malformed_id_404(self, app_client):
        client, _ = app_client
        resp = client.get("/api/files/not-an-id/")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"


class TestMeasurements:
    def _upload_kml(self, client):
        return _upload(
            client, "survey.kml", (SAMPLES / "survey.kml").read_bytes()
        ).json()["id"]

    def test_happy_path(self, app_client):
        client, _ = app_client
        fid = self._upload_kml(client)
        resp = client.get(f"/api/files/{fid}/measurements/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["file_id"] == fid
        assert body["pagination"] == {"limit": 500, "offset": 0, "total": 5}
        assert len(body["features"]) == 5
        summary = body["summary"]
        assert sum(summary["by_measurement_status"].values()) == 5
        assert summary["by_geometry_type"]["Polygon"] == 1
        assert summary["total_area_m2"] and summary["total_area_m2"] > 0
        # GDAL lists the parent "Parcels" folder before the nested
        # "North block" layer, so index 0 is the access road line.
        first = body["features"][0]
        assert first["index"] == 0
        assert first["measurement"]["status"] == "MEASURED"
        assert first["measurement"]["measurement_crs"] == "EPSG:32643"
        assert first["geometry"]["type"] == "LineString"
        polygon = next(f for f in body["features"] if f["geometry_type"] == "Polygon")
        assert polygon["measurement"]["status"] == "MEASURED"
        assert polygon["measurement"]["area_m2"] > 0

    def test_pagination(self, app_client):
        client, _ = app_client
        fid = self._upload_kml(client)
        resp = client.get(f"/api/files/{fid}/measurements/?limit=2&offset=1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["pagination"] == {"limit": 2, "offset": 1, "total": 5}
        assert [f["index"] for f in body["features"]] == [1, 2]

    def test_include_geometry_false(self, app_client):
        client, _ = app_client
        fid = self._upload_kml(client)
        resp = client.get(f"/api/files/{fid}/measurements/?include_geometry=false")
        assert resp.status_code == 200
        assert all(f["geometry"] is None for f in resp.json()["features"])

    def test_failed_file_409(self, app_client):
        client, _ = app_client
        resp = _upload(client, "bad.zip", b"not a zip at all")
        fid = resp.json()["error"]["details"]["file_id"]
        resp = client.get(f"/api/files/{fid}/measurements/")
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "NOT_READY"

    def test_unknown_id_404(self, app_client):
        client, _ = app_client
        resp = client.get("/api/files/" + "0" * 32 + "/measurements/")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"


class TestPathsAndDocs:
    def test_trailing_slash_paths(self, app_client):
        client, _ = app_client
        for path in (
            "/api/files/",
            "/api/files/" + "0" * 32 + "/",
            "/api/files/" + "0" * 32 + "/measurements/",
        ):
            resp = client.get(path) if path != "/api/files/" else None
            if resp is not None:
                assert resp.status_code == 404  # known path, unknown id

    def test_upload_without_trailing_slash(self, app_client):
        client, _ = app_client
        resp = client.post(
            "/api/files",
            files={"file": ("s.kml", (SAMPLES / "survey.kml").read_bytes())},
        )
        assert resp.status_code == 201  # redirect followed

    def test_openapi_lists_endpoints(self, app_client):
        client, _ = app_client
        paths = client.get("/openapi.json").json()["paths"]
        assert "/api/files/" in paths
        assert "/api/files/{file_id}/" in paths
        assert "/api/files/{file_id}/measurements/" in paths
