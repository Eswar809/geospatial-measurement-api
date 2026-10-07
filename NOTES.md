# NOTES.md — Surprises, Bug Fixes, and Learnings

This file tracks unexpected findings and fixes during development. It feeds the README "Learnings" section.

## Phase 0 — Bootstrap & Spike

- **uv install:** `pip install uv` worked cleanly. uv 0.12.23 installed.
- **Package install:** 44 packages resolved and installed in ~3.5 min. Key versions: geopandas 1.2.0, pyogrio 0.13.0, shapely 2.1.2, pyproj 3.8.0, fastapi 0.142.2, sqlalchemy 2.1.3.
- **GDAL drivers:** 64 drivers available. KML and ESRI Shapefile both readable. No manual driver enabling needed.
- **KML read:** pyogrio reads KML with CRS EPSG:4326 automatically. Columns include GDAL-specific fields (id, Name, description, timestamp, begin, end, altitudeMode, tessellate, extrude, visibility, drawOrder, icon, geometry).
- **pyproj:** EPSG:32643 resolves to "WGS 84 / UTM zone 43N". `is_projected` and `is_geographic` work as expected.
- **UTM logic:** Mumbai→32643, London→32630, Sydney→32756 all correct.
- **Shapefile zip:** Deferred to Phase 2 — need proper fixtures with .shp/.shx/.dbf/.prj files.

## Phase 1 — Geo Domain

- **utm_epsg_for lon normalization:** The naive `((lon + 180) % 360) - 180` maps both -180 and +180 to -180, which collapses zone 60's east edge into zone 1. Fix: only normalize out-of-range values, keep exact +/-180 as-is. -180 is the west edge of zone 1, +180 is the east edge of zone 60.
- **pd.NaT is a datetime subclass:** `isinstance(pd.NaT, datetime.datetime)` is True, so the datetime branch in `json_safe` caught NaT first and returned the string "NaT". Fix: explicit `value is pd.NaT` check BEFORE the datetime branch.
- **shapely.ops.transform vs pyproj:** `shapely.ops.transform(transformer.transform, geom)` silently failed with pyproj transformers in Shapely 2. Fix: walk the GeoJSON coordinates manually and call `transformer.transform(x, y)` on each pair.
- **shapely.get_coordinates returns 2D array:** `math.isfinite(c) for c in coords` fails — need `np.all(np.isfinite(coords))`.
- **shapely mapping returns tuples:** `mapping(geom)` returns nested tuples, not lists. Fix: recursive `_convert_coords` that converts tuples to lists.
- **UTM accuracy:** Mumbai test polygon in EPSG:3857 measures ~889k m² vs ~1M m² expected — Web Mercator inflates by 1/cos²(lat). This confirms why we always reproject to local UTM.
- **Lat boundary tests fixed:** 83.9°N is zone 31 (EPSG:32631), not 32660. -80° is zone 31 south (32731), UPS South starts below -80.
- **Build backend:** uv_build expected `src/` layout. Switched to hatchling with `packages = ["app"]`.
- **Ruff BLE001:** Narrowed `except Exception` to `pyproj.exceptions.ProjError` and `(ProjError, ValueError)` in measure.py.
