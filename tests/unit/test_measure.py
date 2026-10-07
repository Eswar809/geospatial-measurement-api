"""Unit tests for geometry measurement."""

import pytest
from pyproj import CRS
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon

from app.services.geo.crs import TransformerCache
from app.services.geo.measure import measure_geometry


@pytest.fixture
def wgs84_cache():
    return TransformerCache(CRS.from_epsg(4326))


class TestMeasureGeometry:
    def test_point_not_applicable(self, wgs84_cache):
        m = measure_geometry(Point(72.87, 19.07), CRS.from_epsg(4326), wgs84_cache)
        assert m.status == "NOT_APPLICABLE"
        assert m.area_m2 is None

    def test_multipoint_not_applicable(self, wgs84_cache):
        from shapely.geometry import MultiPoint

        m = measure_geometry(
            MultiPoint([(72.87, 19.07), (72.88, 19.08)]),
            CRS.from_epsg(4326),
            wgs84_cache,
        )
        assert m.status == "NOT_APPLICABLE"

    def test_empty_unsupported(self, wgs84_cache):
        m = measure_geometry(Polygon(), CRS.from_epsg(4326), wgs84_cache)
        assert m.status == "UNSUPPORTED"
        assert "empty" in m.error_message.lower()

    def test_none_unsupported(self, wgs84_cache):
        m = measure_geometry(None, CRS.from_epsg(4326), wgs84_cache)
        assert m.status == "UNSUPPORTED"

    def test_geometry_collection_unsupported(self, wgs84_cache):
        from shapely.geometry import GeometryCollection

        gc = GeometryCollection(
            [Point(72.87, 19.07), LineString([(72.87, 19.07), (72.88, 19.08)])]
        )
        m = measure_geometry(gc, CRS.from_epsg(4326), wgs84_cache)
        assert m.status == "UNSUPPORTED"

    def test_polygon_area(self, wgs84_cache):
        # Small square ~0.01 deg at equator
        poly = Polygon(
            [
                (72.87, 19.07),
                (72.88, 19.07),
                (72.88, 19.08),
                (72.87, 19.08),
                (72.87, 19.07),
            ]
        )
        m = measure_geometry(poly, CRS.from_epsg(4326), wgs84_cache)
        assert m.status == "MEASURED"
        assert m.area_m2 is not None
        assert m.area_m2 > 0
        assert m.perimeter_m is not None
        assert m.perimeter_m > 0
        assert m.measurement_crs == "EPSG:32643"

    def test_polygon_with_hole(self, wgs84_cache):
        exterior = [
            (72.87, 19.07),
            (72.89, 19.07),
            (72.89, 19.09),
            (72.87, 19.09),
            (72.87, 19.07),
        ]
        hole = [
            (72.875, 19.075),
            (72.885, 19.075),
            (72.885, 19.085),
            (72.875, 19.085),
            (72.875, 19.075),
        ]
        poly = Polygon(exterior, [hole])
        m = measure_geometry(poly, CRS.from_epsg(4326), wgs84_cache)
        assert m.status == "MEASURED"
        assert m.area_m2 is not None
        # Area should be less than the full square
        full = Polygon(exterior)
        full_m = measure_geometry(full, CRS.from_epsg(4326), wgs84_cache)
        assert m.area_m2 < full_m.area_m2

    def test_multipolygon_sum(self, wgs84_cache):
        p1 = Polygon(
            [
                (72.87, 19.07),
                (72.88, 19.07),
                (72.88, 19.08),
                (72.87, 19.08),
                (72.87, 19.07),
            ]
        )
        p2 = Polygon(
            [
                (72.89, 19.07),
                (72.90, 19.07),
                (72.90, 19.08),
                (72.89, 19.08),
                (72.89, 19.07),
            ]
        )
        mp = MultiPolygon([p1, p2])
        m = measure_geometry(mp, CRS.from_epsg(4326), wgs84_cache)
        assert m.status == "MEASURED"
        assert m.area_m2 is not None
        # Should be roughly sum of both
        m1 = measure_geometry(p1, CRS.from_epsg(4326), wgs84_cache)
        m2 = measure_geometry(p2, CRS.from_epsg(4326), wgs84_cache)
        assert abs(m.area_m2 - (m1.area_m2 + m2.area_m2)) < 1.0

    def test_linestring_length(self, wgs84_cache):
        line = LineString([(72.87, 19.07), (72.88, 19.08)])
        m = measure_geometry(line, CRS.from_epsg(4326), wgs84_cache)
        assert m.status == "MEASURED"
        assert m.length_m is not None
        assert m.length_m > 0
        assert m.area_m2 is None

    def test_multilinestring_length(self, wgs84_cache):
        ml = MultiLineString(
            [
                [(72.87, 19.07), (72.88, 19.08)],
                [(72.89, 19.07), (72.90, 19.08)],
            ]
        )
        m = measure_geometry(ml, CRS.from_epsg(4326), wgs84_cache)
        assert m.status == "MEASURED"
        assert m.length_m is not None

    def test_bowtie_repaired(self, wgs84_cache):
        # Bow-tie polygon (self-intersecting)
        bowtie = Polygon(
            [
                (72.87, 19.07),
                (72.89, 19.09),
                (72.89, 19.07),
                (72.87, 19.09),
                (72.87, 19.07),
            ]
        )
        m = measure_geometry(bowtie, CRS.from_epsg(4326), wgs84_cache)
        assert m.status == "MEASURED"
        assert any("repaired" in w.lower() for w in m.warnings)

    def test_3d_forced_2d(self, wgs84_cache):
        poly_3d = Polygon(
            [
                (72.87, 19.07, 100),
                (72.88, 19.07, 200),
                (72.88, 19.08, 300),
                (72.87, 19.08, 400),
                (72.87, 19.07, 100),
            ]
        )
        m = measure_geometry(poly_3d, CRS.from_epsg(4326), wgs84_cache)
        assert m.status == "MEASURED"
        assert m.area_m2 is not None

    def test_equator_vs_60n_ratio(self, wgs84_cache):
        """Area ratio at equator vs 60N should be ~0.5, proving no degree math."""
        # Same degree-size square at equator
        poly_eq = Polygon(
            [(72.87, 0), (72.88, 0), (72.88, 0.01), (72.87, 0.01), (72.87, 0)]
        )
        m_eq = measure_geometry(poly_eq, CRS.from_epsg(4326), wgs84_cache)

        # Same degree-size square at 60N
        poly_60 = Polygon(
            [(72.87, 60), (72.88, 60), (72.88, 60.01), (72.87, 60.01), (72.87, 60)]
        )
        m_60 = measure_geometry(poly_60, CRS.from_epsg(4326), wgs84_cache)

        ratio = m_60.area_m2 / m_eq.area_m2
        # cos(60)^2 = 0.25, so ratio should be ~0.5 (UTM scale factor compensates partially)
        assert 0.3 < ratio < 0.7

    def test_projected_source_crs(self):
        """Projected source (3857) should give same area as 4326 version."""
        cache_3857 = TransformerCache(CRS.from_epsg(3857))
        # Small square in 3857 near Mumbai
        poly_3857 = Polygon(
            [
                (8112000, 2155000),
                (8113000, 2155000),
                (8113000, 2156000),
                (8112000, 2156000),
                (8112000, 2155000),
            ]
        )
        m_3857 = measure_geometry(poly_3857, CRS.from_epsg(3857), cache_3857)
        assert m_3857.status == "MEASURED"
        assert m_3857.area_m2 is not None
        # 3857 inflates at Mumbai latitude (~19°N), so area is less than 1km^2
        assert 800000 < m_3857.area_m2 < 1000000

    def test_multi_zone_warning(self, wgs84_cache):
        # Polygon spanning >6 degrees
        poly = Polygon([(72, 19), (79, 19), (79, 20), (72, 20), (72, 19)])
        m = measure_geometry(poly, CRS.from_epsg(4326), wgs84_cache)
        assert m.status == "MEASURED"
        assert any("multiple UTM zones" in w for w in m.warnings)

    def test_antimeridian_warning(self, wgs84_cache):
        # Polygon spanning >180 degrees
        poly = Polygon([(170, 19), (-170, 19), (-170, 20), (170, 20), (170, 19)])
        m = measure_geometry(poly, CRS.from_epsg(4326), wgs84_cache)
        assert m.status == "MEASURED"
        assert any("antimeridian" in w for w in m.warnings)


class TestGeodesicCrossCheck:
    """Cross-check UTM measurements against geodesic calculations."""

    def test_polygon_area_vs_geod(self, wgs84_cache):
        from pyproj import Geod

        geod = Geod(ellps="WGS84")
        poly = Polygon(
            [
                (72.87, 19.07),
                (72.88, 19.07),
                (72.88, 19.08),
                (72.87, 19.08),
                (72.87, 19.07),
            ]
        )
        m = measure_geometry(poly, CRS.from_epsg(4326), wgs84_cache)

        # Geodesic area
        coords = list(poly.exterior.coords)
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        geod_area, _ = geod.polygon_area_perimeter(lons, lats)
        geod_area = abs(geod_area)

        # Within 0.5%
        assert abs(m.area_m2 - geod_area) / geod_area < 0.005

    def test_line_length_vs_geod(self, wgs84_cache):
        from pyproj import Geod

        geod = Geod(ellps="WGS84")
        line = LineString([(72.87, 19.07), (72.88, 19.08)])
        m = measure_geometry(line, CRS.from_epsg(4326), wgs84_cache)

        # Geodesic length
        coords = list(line.coords)
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        geod_length = geod.line_length(lons, lats)

        # Within 0.5%
        assert abs(m.length_m - geod_length) / geod_length < 0.005
