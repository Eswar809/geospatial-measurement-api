"""Geometry and value serialization utilities."""

from __future__ import annotations

import datetime
import math
from typing import Any

import numpy as np
from shapely.geometry import mapping


def _tuples_to_lists(obj):
    """Recursively convert tuples to lists for JSON serialization."""
    if isinstance(obj, tuple):
        return [_tuples_to_lists(v) for v in obj]
    if isinstance(obj, list):
        return [_tuples_to_lists(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _tuples_to_lists(v) for k, v in obj.items()}
    return obj


def _convert_coords(obj):
    """Recursively convert coordinate tuples to lists."""
    if isinstance(obj, tuple):
        # Check if this is a coordinate pair (2 floats)
        if len(obj) == 2 and all(isinstance(v, (int, float)) for v in obj):
            return list(obj)
        return [_convert_coords(v) for v in obj]
    if isinstance(obj, list):
        return [_convert_coords(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _convert_coords(v) for k, v in obj.items()}
    return obj


def geometry_to_geojson(geom) -> dict:
    """Convert a shapely geometry to a GeoJSON dict.

    Args:
        geom: A shapely geometry object.

    Returns:
        A GeoJSON dict with type and coordinates.
    """
    if geom is None:
        return {}
    result = mapping(geom)
    return _convert_coords(result)


def json_safe(value: Any) -> Any:
    """Convert a value to a JSON-safe type.

    Handles numpy scalars, NaN/NaT, datetime, bytes, and nested structures.

    Args:
        value: Any value that might not be JSON-serializable.

    Returns:
        A JSON-safe version of the value.
    """
    if value is None:
        return None

    # numpy scalars
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        value = float(value)
    if isinstance(value, np.ndarray):
        return [json_safe(v) for v in value.tolist()]

    # float NaN/Inf
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value

    # NaT check must come before datetime: pd.NaT is a datetime subclass.
    try:
        import pandas as pd

        if value is pd.NaT:
            return None
    except ImportError:
        pass

    # datetime
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()

    # bytes
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.hex()

    # dict
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}

    # list/tuple
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]

    return value
