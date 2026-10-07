"""Unit tests for serialization utilities."""

import datetime

import numpy as np
import pytest
from shapely.geometry import LineString, Point, Polygon

from app.services.geo.serialize import geometry_to_geojson, json_safe


class TestGeometryToGeojson:
    def test_point(self):
        result = geometry_to_geojson(Point(72.87, 19.07))
        assert result["type"] == "Point"
        assert result["coordinates"] == [72.87, 19.07]

    def test_polygon(self):
        poly = Polygon([(72.87, 19.07), (72.88, 19.07), (72.88, 19.08), (72.87, 19.07)])
        result = geometry_to_geojson(poly)
        assert result["type"] == "Polygon"
        assert len(result["coordinates"]) == 1  # exterior ring
        assert len(result["coordinates"][0]) >= 4  # at least 4 points

    def test_linestring(self):
        line = LineString([(72.87, 19.07), (72.88, 19.08)])
        result = geometry_to_geojson(line)
        assert result["type"] == "LineString"
        assert len(result["coordinates"]) == 2

    def test_none(self):
        result = geometry_to_geojson(None)
        assert result == {}


class TestJsonSafe:
    def test_numpy_int(self):
        assert json_safe(np.int64(42)) == 42
        assert isinstance(json_safe(np.int64(42)), int)

    def test_numpy_float(self):
        result = json_safe(np.float64(3.14))
        assert isinstance(result, float)
        assert abs(result - 3.14) < 0.001

    def test_numpy_array(self):
        result = json_safe(np.array([1, 2, 3]))
        assert result == [1, 2, 3]

    def test_nan_to_none(self):
        assert json_safe(float("nan")) is None

    def test_inf_to_none(self):
        assert json_safe(float("inf")) is None
        assert json_safe(float("-inf")) is None

    def test_datetime(self):
        dt = datetime.datetime(2026, 10, 7, 10, 30, 0, tzinfo=datetime.UTC)
        result = json_safe(dt)
        assert "2026-10-07" in result

    def test_date(self):
        d = datetime.date(2026, 10, 7)
        result = json_safe(d)
        assert "2026-10-07" in result

    def test_bytes(self):
        result = json_safe(b"hello")
        assert result == "hello"

    def test_bytes_non_utf8(self):
        result = json_safe(b"\xff\xfe")
        assert isinstance(result, str)  # hex fallback

    def test_none(self):
        assert json_safe(None) is None

    def test_dict(self):
        result = json_safe({"a": np.int64(1), "b": float("nan")})
        assert result == {"a": 1, "b": None}

    def test_list(self):
        result = json_safe([np.int64(1), float("inf"), "hello"])
        assert result == [1, None, "hello"]

    def test_nested(self):
        result = json_safe({"a": [np.float64(1.5), {"b": np.int64(2)}]})
        assert result == {"a": [1.5, {"b": 2}]}

    def test_pandas_nat(self):
        pd = pytest.importorskip("pandas")
        assert json_safe(pd.NaT) is None

    def test_pandas_timestamp(self):
        pd = pytest.importorskip("pandas")
        ts = pd.Timestamp("2026-10-07 10:30:00")
        result = json_safe(ts)
        assert "2026-10-07" in result
