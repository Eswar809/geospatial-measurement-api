"""Map file extensions to reader functions.

Supporting a new format (e.g. GeoJSON, GPKG) means adding one reader
module and one entry here.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.services.readers.base import RawDataset
from app.services.readers.kml import read_kml
from app.services.readers.shapefile import read_shapefile

Reader = Callable[[Path], RawDataset]

READERS: dict[str, Reader] = {
    ".zip": read_shapefile,
    ".kml": read_kml,
}


def get_reader(ext: str) -> Reader:
    """Return the reader for a file extension.

    Args:
        ext: File extension with or without a leading dot.

    Raises:
        KeyError: If no reader is registered for the extension.
    """
    key = ext.lower() if ext.startswith(".") else f".{ext.lower()}"
    return READERS[key]
