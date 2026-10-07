"""ESRI Shapefile reader.

Reads the parts from a directory previously extracted with
``archive.safe_extract``. The directory must contain exactly one ``.shp``
plus its ``.shx`` and ``.dbf`` companions; ``.prj`` and ``.cpg`` are
optional.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyogrio
import pyproj
import shapely

from app.core.errors import (
    InvalidArchiveError,
    InvalidGeoDataError,
    UnsupportedCRSError,
)
from app.services.geo.serialize import json_safe
from app.services.readers.base import RawDataset, RawFeature

_WGS84 = pyproj.CRS.from_epsg(4326)


def read_shapefile(directory: Path, *, layer: str | None = None) -> RawDataset:
    """Read shapefile parts from an extracted directory.

    Args:
        directory: Directory holding the extracted parts (e.g. ``data.shp``).
        layer: Label attached to every feature. Defaults to the ``.shp``
            file stem. Callers (ingestion) may pass the upload's stem so
            responses carry a meaningful name instead of ``data``.

    Returns:
        A RawDataset in the source CRS.

    Raises:
        InvalidArchiveError: No ``.shp``, more than one ``.shp``, or a
            missing ``.shx``/``.dbf`` companion.
        InvalidGeoDataError: The ``.shp`` cannot be read or has no features.
        UnsupportedCRSError: No usable ``.prj`` and the coordinates are not
            valid longitude/latitude, or the CRS cannot be transformed to
            geographic coordinates.
    """
    shp = _find_single_shp(directory)
    _require_companions(directory, shp)
    try:
        gdf = pyogrio.read_dataframe(shp)
    except (
        pyogrio.errors.DataSourceError,
        pyogrio.errors.DataLayerError,
    ) as e:
        raise InvalidGeoDataError(f"could not read shapefile: {e}") from e
    if len(gdf) == 0:
        raise InvalidGeoDataError("shapefile contains no features")
    crs, crs_assumed, warnings = _resolve_crs(gdf)
    properties = json_safe(gdf.drop(columns=["geometry"]).to_dict("records"))
    features = [
        RawFeature(
            layer=layer or shp.stem,
            geometry=geom,
            properties=props,
        )
        for geom, props in zip(gdf.geometry, properties, strict=True)
    ]
    return RawDataset(
        crs=crs, features=features, crs_assumed=crs_assumed, warnings=warnings
    )


def _find_single_shp(directory: Path) -> Path:
    """Locate the one ``.shp`` part, case-insensitively."""
    matches = [
        f for f in directory.iterdir() if f.is_file() and f.suffix.lower() == ".shp"
    ]
    if not matches:
        raise InvalidArchiveError("archive contains no .shp file")
    if len(matches) > 1:
        raise InvalidArchiveError("archive contains more than one .shp file")
    return matches[0]


def _require_companions(directory: Path, shp: Path) -> None:
    """Require the ``.shx`` and ``.dbf`` companions of a ``.shp``."""
    names = {f.name.lower() for f in directory.iterdir() if f.is_file()}
    for suffix in (".shx", ".dbf"):
        if f"{shp.stem.lower()}{suffix}" not in names:
            raise InvalidArchiveError(f"shapefile is missing required {suffix} part")


def _resolve_crs(
    gdf,
) -> tuple[pyproj.CRS, bool, list[str]]:
    """Determine the source CRS, applying the assume-4326 policy.

    A missing or unreadable ``.prj`` surfaces as ``gdf.crs is None``. In
    that case assume EPSG:4326 only if every coordinate is a valid
    longitude/latitude value.
    """
    warnings: list[str] = []
    crs = gdf.crs
    if crs is None:
        if _all_lonlat(gdf.geometry):
            warnings.append(
                "missing or unreadable .prj; assuming EPSG:4326 because "
                "all coordinates are valid longitude/latitude"
            )
            return _WGS84, True, warnings
        raise UnsupportedCRSError(
            "missing or unreadable .prj and coordinates are not valid "
            "longitude/latitude; source CRS is unknown"
        )
    try:
        pyproj.Transformer.from_crs(crs, _WGS84, always_xy=True)
    except pyproj.exceptions.ProjError as e:
        raise UnsupportedCRSError(
            f"source CRS cannot be transformed to geographic coordinates: {e}"
        ) from e
    return crs, False, warnings


def _all_lonlat(geoms) -> bool:
    """Check every coordinate is a finite, valid longitude/latitude."""
    non_null = [g for g in geoms if g is not None]
    if not non_null:
        return True
    coords = shapely.get_coordinates(non_null)
    if coords.size == 0:
        return True
    lon_ok = np.all((coords[:, 0] >= -180) & (coords[:, 0] <= 180))
    lat_ok = np.all((coords[:, 1] >= -90) & (coords[:, 1] <= 90))
    return bool(lon_ok and lat_ok and np.all(np.isfinite(coords)))
