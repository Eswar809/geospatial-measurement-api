"""Geometry measurement in projected CRS."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pyproj
import shapely
from shapely.geometry import mapping, shape
from shapely.validation import make_valid

from app.services.geo.crs import TransformerCache, utm_epsg_for


@dataclass
class Measurement:
    """Result of measuring a single geometry."""

    status: str  # MEASURED, NOT_APPLICABLE, UNSUPPORTED, ERROR
    area_m2: float | None = None
    perimeter_m: float | None = None
    length_m: float | None = None
    measurement_crs: str | None = None
    warnings: list[str] = field(default_factory=list)
    error_message: str | None = None


def _force_2d(geom):
    """Force geometry to 2D, dropping Z coordinates."""
    if geom is None:
        return None
    return shapely.force_2d(geom)


def _get_bbox_center_lonlat(geom, src_crs, transformer_cache):
    """Get the bbox center in lon/lat for UTM zone selection."""
    minx, miny, maxx, maxy = geom.bounds
    cx = (minx + maxx) / 2
    cy = (miny + maxy) / 2

    if src_crs.is_geographic:
        return cx, cy

    # Transform center to geographic
    transformer = transformer_cache.get(4326)
    lon, lat = transformer.transform(cx, cy)
    return lon, lat


def _check_lon_span(geom, src_crs, transformer_cache) -> list[str]:
    """Check if geometry spans multiple UTM zones or crosses antimeridian."""
    warnings = []
    minx, miny, maxx, maxy = geom.bounds

    if src_crs.is_geographic:
        lon_span = maxx - minx
    else:
        transformer = transformer_cache.get(4326)
        corners = [
            transformer.transform(minx, miny),
            transformer.transform(minx, maxy),
            transformer.transform(maxx, miny),
            transformer.transform(maxx, maxy),
        ]
        lons = [c[0] for c in corners]
        lon_span = max(lons) - min(lons)

    if lon_span > 180:
        warnings.append("possible antimeridian crossing")
    elif lon_span > 6:
        warnings.append("spans multiple UTM zones, accuracy reduced")

    return warnings


def measure_geometry(
    geom,
    src_crs: pyproj.CRS,
    transformer_cache: TransformerCache,
) -> Measurement:
    """Measure a shapely geometry in the appropriate UTM zone.

    Args:
        geom: A shapely geometry object.
        src_crs: The CRS of the geometry.
        transformer_cache: Cache for coordinate transformers.

    Returns:
        A Measurement dataclass with status, values, and warnings.
    """
    # 1. Empty or None geometry
    if geom is None or geom.is_empty:
        return Measurement(
            status="UNSUPPORTED",
            error_message="empty or missing geometry",
        )

    # 2. Point/MultiPoint -> NOT_APPLICABLE
    if geom.geom_type in ("Point", "MultiPoint"):
        return Measurement(status="NOT_APPLICABLE")

    # 3. Force 2D
    geom = _force_2d(geom)

    # 4. Check validity and repair if needed
    warnings = []
    if not geom.is_valid:
        geom = make_valid(geom)
        # Keep only polygonal parts if it became a collection
        if geom.geom_type == "GeometryCollection":
            polys = [
                g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon")
            ]
            lines = [
                g
                for g in geom.geoms
                if g.geom_type in ("LineString", "MultiLineString")
            ]
            if polys:
                geom = shapely.union_all(polys) if len(polys) > 1 else polys[0]
            elif lines:
                geom = shapely.union_all(lines) if len(lines) > 1 else lines[0]
            else:
                return Measurement(
                    status="UNSUPPORTED",
                    error_message="geometry could not be repaired to a measurable type",
                )
        warnings.append("geometry was invalid and has been repaired")

    # 5. Determine measurement type
    is_polygonal = geom.geom_type in ("Polygon", "MultiPolygon")
    is_linear = geom.geom_type in ("LineString", "MultiLineString")

    if not is_polygonal and not is_linear:
        return Measurement(
            status="UNSUPPORTED",
            error_message=f"unsupported geometry type: {geom.geom_type}",
        )

    # 6. Get bbox center and select UTM zone
    try:
        lon, lat = _get_bbox_center_lonlat(geom, src_crs, transformer_cache)
        dst_epsg = utm_epsg_for(lon, lat)
    except pyproj.exceptions.ProjError as e:
        return Measurement(
            status="ERROR",
            error_message=f"failed to determine UTM zone: {e}",
        )

    # 7. Check for multi-zone span
    warnings.extend(_check_lon_span(geom, src_crs, transformer_cache))

    # 8. Transform to UTM
    try:
        transformer = transformer_cache.get(dst_epsg)
        # Use pyproj transformer directly on coordinates
        geojson = mapping(geom)
        coords = geojson["coordinates"]

        def transform_coords(c):
            if isinstance(c[0], (int, float)):
                x, y = transformer.transform(c[0], c[1])
                return [x, y]
            return [transform_coords(sub) for sub in c]

        geojson["coordinates"] = transform_coords(coords)
        geom_utm = shape(geojson)
    except (pyproj.exceptions.ProjError, ValueError) as e:
        return Measurement(
            status="ERROR",
            error_message=f"failed to transform to EPSG:{dst_epsg}: {e}",
        )

    # 9. Check for non-finite coordinates
    coords = shapely.get_coordinates(geom_utm)
    if not np.all(np.isfinite(coords)):
        return Measurement(
            status="ERROR",
            error_message="non-finite coordinates after transform",
        )

    # 10. Measure
    measurement_crs = f"EPSG:{dst_epsg}"
    if is_polygonal:
        return Measurement(
            status="MEASURED",
            area_m2=round(geom_utm.area, 4),
            perimeter_m=round(geom_utm.length, 4),
            measurement_crs=measurement_crs,
            warnings=warnings,
        )
    else:
        return Measurement(
            status="MEASURED",
            length_m=round(geom_utm.length, 4),
            measurement_crs=measurement_crs,
            warnings=warnings,
        )
