"""Reader interface: raw dataset containers returned by format readers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pyproj


@dataclass
class RawFeature:
    """One unmeasured feature as read from the source file."""

    layer: str
    geometry: Any
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawDataset:
    """All features from a source file, plus the source CRS."""

    crs: pyproj.CRS
    features: list[RawFeature] = field(default_factory=list)
    crs_assumed: bool = False
    warnings: list[str] = field(default_factory=list)
