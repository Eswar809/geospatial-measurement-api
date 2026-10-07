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
