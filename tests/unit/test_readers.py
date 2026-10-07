"""Reader tests with fixtures generated at runtime."""

import zipfile

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from app.core.errors import (
    InvalidArchiveError,
    InvalidGeoDataError,
    UnsupportedCRSError,
)
from app.services.readers.kml import read_kml
from app.services.readers.registry import get_reader
from app.services.readers.shapefile import read_shapefile

MUMBAI_POLY = Polygon([(72.87, 19.07), (72.88, 19.07), (72.88, 19.08), (72.87, 19.07)])


def _write_shapefile_zip(zip_path, gdf, stem="parcels"):
    """Write a GeoDataFrame as shapefile parts, then zip them."""
    work = zip_path.parent / f"_{zip_path.stem}_parts"
    work.mkdir(exist_ok=True)
    try:
        gdf.to_file(work / f"{stem}.shp")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for part in sorted(work.glob(f"{stem}.*")):
                zf.write(part, part.name)
    finally:
        for leftover in work.iterdir():
            leftover.unlink()
        work.rmdir()
    return zip_path


def _extract_here(zip_path, dest):
    import zipfile

    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    return dest


class TestShapefileReader:
    def test_epsg4326(self, tmp_path):
        gdf = gpd.GeoDataFrame({"name": ["A"]}, geometry=[MUMBAI_POLY], crs="EPSG:4326")
        _write_shapefile_zip(tmp_path / "p.zip", gdf)
        ds = read_shapefile(_extract_here(tmp_path / "p.zip", tmp_path / "ex"))
        assert ds.crs.to_epsg() == 4326
        assert ds.crs_assumed is False
        assert len(ds.features) == 1
        assert ds.features[0].properties["name"] == "A"

    def test_projected_3857(self, tmp_path):
        gdf = gpd.GeoDataFrame({"n": [1]}, geometry=[MUMBAI_POLY], crs="EPSG:4326")
        projected = gdf.to_crs("EPSG:3857")
        _write_shapefile_zip(tmp_path / "p.zip", projected)
        ds = read_shapefile(_extract_here(tmp_path / "p.zip", tmp_path / "ex"))
        assert ds.crs.to_epsg() == 3857
        assert ds.crs_assumed is False

    def test_projected_utm(self, tmp_path):
        gdf = gpd.GeoDataFrame({"n": [1]}, geometry=[MUMBAI_POLY], crs="EPSG:4326")
        projected = gdf.to_crs("EPSG:32643")
        _write_shapefile_zip(tmp_path / "p.zip", projected)
        ds = read_shapefile(_extract_here(tmp_path / "p.zip", tmp_path / "ex"))
        assert ds.crs.to_epsg() == 32643

    def test_missing_prj_assumes_4326(self, tmp_path):
        gdf = gpd.GeoDataFrame({"name": ["A"]}, geometry=[MUMBAI_POLY], crs="EPSG:4326")
        _write_shapefile_zip(tmp_path / "p.zip", gdf)
        for prj in (tmp_path / "ex").glob("*.prj"):
            prj.unlink()
        ex = _extract_here(tmp_path / "p.zip", tmp_path / "ex2")
        for prj in ex.glob("*.prj"):
            prj.unlink()
        ds = read_shapefile(ex)
        assert ds.crs.to_epsg() == 4326
        assert ds.crs_assumed is True
        assert ds.warnings

    def test_missing_prj_non_lonlat_rejected(self, tmp_path):
        gdf = gpd.GeoDataFrame({"n": [1]}, geometry=[MUMBAI_POLY], crs="EPSG:4326")
        projected = gdf.to_crs("EPSG:3857")
        _write_shapefile_zip(tmp_path / "p.zip", projected)
        ex = _extract_here(tmp_path / "p.zip", tmp_path / "ex")
        for prj in ex.glob("*.prj"):
            prj.unlink()
        with pytest.raises(UnsupportedCRSError):
            read_shapefile(ex)

    def test_missing_shx_rejected(self, tmp_path):
        gdf = gpd.GeoDataFrame({"n": [1]}, geometry=[MUMBAI_POLY], crs="EPSG:4326")
        _write_shapefile_zip(tmp_path / "p.zip", gdf)
        ex = _extract_here(tmp_path / "p.zip", tmp_path / "ex")
        for shx in ex.glob("*.shx"):
            shx.unlink()
        with pytest.raises(InvalidArchiveError, match="shx"):
            read_shapefile(ex)

    def test_missing_dbf_rejected(self, tmp_path):
        gdf = gpd.GeoDataFrame({"n": [1]}, geometry=[MUMBAI_POLY], crs="EPSG:4326")
        _write_shapefile_zip(tmp_path / "p.zip", gdf)
        ex = _extract_here(tmp_path / "p.zip", tmp_path / "ex")
        for dbf in ex.glob("*.dbf"):
            dbf.unlink()
        with pytest.raises(InvalidArchiveError, match="dbf"):
            read_shapefile(ex)

    def test_non_ascii_and_date_attributes(self, tmp_path):
        import datetime

        gdf = gpd.GeoDataFrame(
            {
                "city": ["Mumbaï–मुंबई"],
                "surveyed": [datetime.date(2026, 10, 7)],
                "empty": [None],
            },
            geometry=[MUMBAI_POLY],
            crs="EPSG:4326",
        )
        _write_shapefile_zip(tmp_path / "p.zip", gdf)
        ds = read_shapefile(_extract_here(tmp_path / "p.zip", tmp_path / "ex"))
        props = ds.features[0].properties
        assert props.get("city")
        assert props["surveyed"] == "2026-10-07"
        assert props["empty"] is None


KML_NESTED = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Folder>
      <name>Parcels</name>
      <Folder>
        <name>North block</name>
        <Placemark>
          <name>Plot 1</name>
          <Polygon>
            <outerBoundaryIs><LinearRing><coordinates>72.87,19.07 72.88,19.07 72.88,19.08 72.87,19.07</coordinates></LinearRing></outerBoundaryIs>
            <innerBoundaryIs><LinearRing><coordinates>72.872,19.072 72.878,19.072 72.878,19.078 72.872,19.072</coordinates></LinearRing></innerBoundaryIs>
          </Polygon>
        </Placemark>
      </Folder>
      <Placemark>
        <name>Access road</name>
        <LineString><coordinates>72.87,19.07 72.885,19.075 72.89,19.08</coordinates></LineString>
      </Placemark>
      <Placemark>
        <name>Survey point</name>
        <Point><coordinates>72.9,19.1,50</coordinates></Point>
      </Placemark>
      <Placemark>
        <name>Mixed marker</name>
        <MultiGeometry>
          <Point><coordinates>72.91,19.11,20</coordinates></Point>
          <Polygon>
            <outerBoundaryIs><LinearRing><coordinates>72.905,19.105 72.915,19.105 72.915,19.115 72.905,19.105</coordinates></LinearRing></outerBoundaryIs>
          </Polygon>
        </MultiGeometry>
      </Placemark>
      <Placemark>
        <name>Note only</name>
        <description>no geometry here</description>
      </Placemark>
    </Folder>
  </Document>
</kml>
"""


class TestKmlReader:
    def test_nested_folders_flattened(self, tmp_path):
        path = tmp_path / "n.kml"
        path.write_text(KML_NESTED, encoding="utf-8")
        ds = read_kml(path)
        assert ds.crs.to_epsg() == 4326
        # 5 Placemarks, one per feature: GDAL keeps the geometry-less one.
        assert len(ds.features) == 5
        by_name = {f.properties.get("Name"): f for f in ds.features}
        assert set(by_name) == {
            "Plot 1",
            "Access road",
            "Survey point",
            "Mixed marker",
            "Note only",
        }
        assert by_name["Plot 1"].geometry.geom_type == "Polygon"
        assert len(by_name["Plot 1"].geometry.interiors) == 1
        assert by_name["Access road"].geometry.geom_type == "LineString"
        assert by_name["Survey point"].geometry.has_z
        assert by_name["Mixed marker"].geometry.geom_type == "GeometryCollection"
        assert by_name["Note only"].geometry is None

    def test_entity_rejected(self, tmp_path):
        path = tmp_path / "evil.kml"
        path.write_text(
            '<!DOCTYPE kml [<!ENTITY x "y">]>'
            '<kml xmlns="http://www.opengis.net/kml/2.2"></kml>',
            encoding="utf-8",
        )
        with pytest.raises(InvalidGeoDataError, match="[Ee]ntity"):
            read_kml(path)

    def test_malformed_rejected(self, tmp_path):
        path = tmp_path / "bad.kml"
        path.write_text("not xml at all <<<<", encoding="utf-8")
        with pytest.raises(InvalidGeoDataError):
            read_kml(path)

    def test_empty_rejected(self, tmp_path):
        path = tmp_path / "empty.kml"
        path.write_bytes(b"")
        with pytest.raises(InvalidGeoDataError, match="[Ee]mpty"):
            read_kml(path)

    def test_zero_features_rejected(self, tmp_path):
        path = tmp_path / "nofeat.kml"
        path.write_text(
            '<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2">'
            "<Document></Document></kml>",
            encoding="utf-8",
        )
        with pytest.raises(InvalidGeoDataError, match="no features"):
            read_kml(path)


class TestRegistry:
    def test_get_reader_zip(self):
        assert get_reader(".zip") is not None
        assert get_reader("zip") is not None

    def test_get_reader_kml(self):
        assert get_reader(".kml") is not None

    def test_unknown_raises(self):
        with pytest.raises(KeyError):
            get_reader(".gpkg")
