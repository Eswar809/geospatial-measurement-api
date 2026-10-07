"""Unit tests for CRS utilities."""

import pytest
from pyproj import CRS

from app.services.geo.crs import (
    TransformerCache,
    describe_crs,
    is_geographic,
    utm_epsg_for,
)


class TestUtmEpsgFor:
    """Test UTM zone selection."""

    def test_london(self):
        assert utm_epsg_for(-0.12, 51.50) == 32630

    def test_mumbai(self):
        assert utm_epsg_for(72.87, 19.07) == 32643

    def test_sydney(self):
        assert utm_epsg_for(151.20, -33.86) == 32756

    def test_equator(self):
        assert utm_epsg_for(0, 0) == 32631

    def test_north_pole_ups(self):
        assert utm_epsg_for(0, 85) == 32661

    def test_south_pole_ups(self):
        assert utm_epsg_for(0, -85) == 32761

    def test_lon_180(self):
        assert utm_epsg_for(180, 0) == 32660

    def test_lon_minus_180(self):
        # -180 is the west edge of zone 1
        assert utm_epsg_for(-180, 0) == 32601

    def test_lon_179_9(self):
        assert utm_epsg_for(179.9, 0) == 32660

    def test_lon_minus_179_9(self):
        assert utm_epsg_for(-179.9, 0) == 32601

    @pytest.mark.parametrize("zone", range(1, 61))
    def test_all_zones_northern(self, zone):
        lon = (zone - 1) * 6 - 180 + 3  # center of zone
        assert utm_epsg_for(lon, 10) == 32600 + zone

    @pytest.mark.parametrize("zone", range(1, 61))
    def test_all_zones_southern(self, zone):
        lon = (zone - 1) * 6 - 180 + 3
        assert utm_epsg_for(lon, -10) == 32700 + zone

    def test_lat_84_boundary(self):
        assert utm_epsg_for(0, 84) == 32661

    def test_lat_83_9(self):
        assert utm_epsg_for(0, 83.9) == 32631

    def test_lat_minus_80_boundary(self):
        assert utm_epsg_for(0, -80) == 32731

    def test_lat_minus_79_9(self):
        assert utm_epsg_for(0, -79.9) == 32731


class TestDescribeCrs:
    def test_describe_epsg4326(self):
        crs = CRS.from_epsg(4326)
        result = describe_crs(crs)
        assert result["epsg"] == 4326
        assert "WGS 84" in result["name"]
        assert result["is_geographic"] is True
        assert "GEOGCS" in result["wkt"] or "WGS" in result["wkt"]

    def test_describe_epsg32643(self):
        crs = CRS.from_epsg(32643)
        result = describe_crs(crs)
        assert result["epsg"] == 32643
        assert result["is_geographic"] is False


class TestIsGeographic:
    def test_geographic(self):
        assert is_geographic(CRS.from_epsg(4326)) is True

    def test_projected(self):
        assert is_geographic(CRS.from_epsg(32643)) is False


class TestTransformerCache:
    def test_get_transformer(self):
        cache = TransformerCache(CRS.from_epsg(4326))
        t1 = cache.get(32643)
        t2 = cache.get(32643)
        assert t1 is t2  # cached

    def test_different_transformers(self):
        cache = TransformerCache(CRS.from_epsg(4326))
        t1 = cache.get(32643)
        t2 = cache.get(32756)
        assert t1 is not t2

    def test_transform_correctness(self):
        cache = TransformerCache(CRS.from_epsg(4326))
        transformer = cache.get(32643)
        x, y = transformer.transform(72.87, 19.07)
        assert x > 0  # UTM easting
        assert y > 0  # UTM northing in northern hemisphere
