"""Generate committed sample files used in README examples.

Outputs:
    samples/survey.kml — polygon with a hole, a line, a point, a
        point-plus-polygon MultiGeometry, and one geometry-less Placemark,
        organized in nested folders.
    samples/parcels_epsg32643.zip — two polygons in a projected CRS
        (EPSG:32643), with .shp/.shx/.dbf/.prj parts.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"

SURVEY_KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Survey</name>
    <Folder>
      <name>Parcels</name>
      <Folder>
        <name>North block</name>
        <Placemark>
          <name>Plot 1</name>
          <description>polygon with a hole</description>
          <Polygon>
            <outerBoundaryIs><LinearRing><coordinates>72.87,19.07,5 72.88,19.07,5 72.88,19.08,5 72.87,19.08,5 72.87,19.07,5</coordinates></LinearRing></outerBoundaryIs>
            <innerBoundaryIs><LinearRing><coordinates>72.872,19.072,5 72.878,19.072,5 72.878,19.078,5 72.872,19.072,5</coordinates></LinearRing></innerBoundaryIs>
          </Polygon>
        </Placemark>
      </Folder>
      <Placemark>
        <name>Access road</name>
        <LineString><coordinates>72.87,19.07,0 72.885,19.075,0 72.89,19.08,0</coordinates></LineString>
      </Placemark>
    </Folder>
    <Folder>
      <name>Markers</name>
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


def write_survey_kml() -> Path:
    """Write the sample KML file."""
    target = SAMPLES / "survey.kml"
    target.write_text(SURVEY_KML, encoding="utf-8")
    return target


def write_parcels_zip() -> Path:
    """Write two parcels in EPSG:32643 as a shapefile zip."""
    work = SAMPLES / "_parcels_tmp"
    work.mkdir(parents=True, exist_ok=True)
    try:
        gdf = gpd.GeoDataFrame(
            {"name": ["Parcel A", "Parcel B"], "area_ha": [1.2, 2.5]},
            geometry=[
                Polygon(
                    [
                        (698000, 2110000),
                        (698100, 2110000),
                        (698100, 2110100),
                        (698000, 2110100),
                    ]
                ),
                Polygon(
                    [
                        (698200, 2110200),
                        (698350, 2110200),
                        (698350, 2110300),
                        (698200, 2110300),
                    ]
                ),
            ],
            crs="EPSG:32643",
        )
        gdf.to_file(work / "parcels.shp")
        target = SAMPLES / "parcels_epsg32643.zip"
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
            for part in sorted(work.glob("parcels.*")):
                zf.write(part, part.name)
        return target
    finally:
        for leftover in work.iterdir():
            leftover.unlink()
        work.rmdir()


def main() -> None:
    SAMPLES.mkdir(parents=True, exist_ok=True)
    print(write_survey_kml())
    print(write_parcels_zip())


if __name__ == "__main__":
    main()
