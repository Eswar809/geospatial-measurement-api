"""KML reader: every layer (Folder), flattened with layer names.

The KML spec fixes the CRS to EPSG:4326, so it is set when the driver
reports none. Geometries are returned as read (including altitude);
the measurement step forces 2D itself.
"""

from __future__ import annotations

from pathlib import Path

import pyogrio
import pyproj

from app.core.errors import InvalidGeoDataError
from app.services.geo.serialize import json_safe
from app.services.readers.base import RawDataset, RawFeature

_KML_CRS = pyproj.CRS.from_epsg(4326)


def read_kml(path: Path) -> RawDataset:
    """Read all KML layers into one flat feature list.

    Args:
        path: Path to the ``.kml`` file.

    Returns:
        A RawDataset in EPSG:4326. Geometry-less Placemarks are kept as
        features with ``geometry=None`` so the feature count matches the
        Placemark count.

    Raises:
        InvalidGeoDataError: Empty file, entity declarations (XXE
            defense), unreadable content, or zero features.
    """
    if path.stat().st_size == 0:
        raise InvalidGeoDataError("KML file is empty")
    if _has_entity_declaration(path):
        raise InvalidGeoDataError("KML files with entity declarations are not allowed")
    try:
        layers = pyogrio.list_layers(path)
    except (
        pyogrio.errors.DataSourceError,
        pyogrio.errors.DataLayerError,
    ) as e:
        raise InvalidGeoDataError(f"could not read KML file: {e}") from e
    features: list[RawFeature] = []
    for name, _geom_type in layers:
        layer_name = str(name)
        try:
            gdf = pyogrio.read_dataframe(path, layer=layer_name)
        except (
            pyogrio.errors.DataSourceError,
            pyogrio.errors.DataLayerError,
        ) as e:
            raise InvalidGeoDataError(
                f"could not read KML layer {layer_name!r}: {e}"
            ) from e
        if len(gdf) == 0:
            continue
        properties = json_safe(gdf.drop(columns=["geometry"]).to_dict("records"))
        features.extend(
            RawFeature(layer=layer_name, geometry=geom, properties=props)
            for geom, props in zip(gdf.geometry, properties, strict=True)
        )
    if not features:
        raise InvalidGeoDataError("KML file contains no features")
    return RawDataset(crs=_KML_CRS, features=features)


def _has_entity_declaration(path: Path) -> bool:
    """Scan for ``<!ENTITY`` without loading the whole file into memory."""
    needle = b"<!ENTITY"
    overlap = len(needle)
    previous = b""
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            if needle in (previous + chunk).upper():
                return True
            previous = chunk[-overlap:]
    return False
