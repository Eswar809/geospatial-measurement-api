"""CRS utilities: UTM zone selection, CRS description, transformer caching."""

from __future__ import annotations

import pyproj


def utm_epsg_for(lon: float, lat: float) -> int:
    """Return EPSG code for the appropriate UTM zone or UPS at the poles.

    Args:
        lon: Longitude in degrees.
        lat: Latitude in degrees.

    Returns:
        EPSG code (326xx for northern UTM, 327xx for southern UTM,
        32661 for UPS North, 32761 for UPS South).
    """
    # Normalize out-of-range values to [-180, 180].
    # Keep exact +/-180 as-is: -180 is zone 1's west edge,
    # +180 is zone 60's east edge.
    if lon < -180 or lon > 180:
        lon = ((lon + 180) % 360) - 180
    if lat >= 84:
        return 32661  # UPS North
    if lat < -80:
        return 32761  # UPS South
    zone = int((lon + 180) // 6) + 1
    zone = min(max(zone, 1), 60)  # clamp to valid range
    return (32600 if lat >= 0 else 32700) + zone


def describe_crs(crs: pyproj.CRS) -> dict:
    """Return a dict describing a CRS.

    Args:
        crs: A pyproj.CRS object.

    Returns:
        Dict with keys: epsg, name, wkt, is_geographic.
    """
    epsg = crs.to_epsg()
    return {
        "epsg": epsg,
        "name": crs.name,
        "wkt": crs.to_wkt(),
        "is_geographic": crs.is_geographic,
    }


def is_geographic(crs: pyproj.CRS) -> bool:
    """Check if a CRS uses angular (degree) units.

    Args:
        crs: A pyproj.CRS object.

    Returns:
        True if the CRS is geographic (degrees), False if projected.
    """
    return crs.is_geographic


class TransformerCache:
    """Per-ingestion cache of pyproj.Transformer objects.

    Transformer thread-safety has varied across pyproj versions,
    so we cache one transformer per destination CRS within a single
    ingestion run rather than using a module-level lru_cache.
    """

    def __init__(self, src_crs: pyproj.CRS) -> None:
        self.src_crs = src_crs
        self._cache: dict[int, pyproj.Transformer] = {}

    def get(self, dst_epsg: int) -> pyproj.Transformer:
        """Get a transformer from the source CRS to the given EPSG code.

        Args:
            dst_epsg: Destination EPSG code.

        Returns:
            A cached pyproj.Transformer.
        """
        if dst_epsg not in self._cache:
            self._cache[dst_epsg] = pyproj.Transformer.from_crs(
                self.src_crs, pyproj.CRS.from_epsg(dst_epsg), always_xy=True
            )
        return self._cache[dst_epsg]
